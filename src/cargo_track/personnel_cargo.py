"""A SELECT-only snapshot of the existing cargo ledger."""
from __future__ import annotations

import sqlite3
import copy
from pathlib import Path, PureWindowsPath

from .personnel_import import PersonnelError, digest
from .coordination import workspace_files


def location_signature(location):
    return digest({f: location.get(f) for f in ("id", "kind", "name", "created_utc")})


def dependency_spec(snapshot, personnel, cargo_ids):
    locations={s['vessel_id'] for s in snapshot['stops']}
    locations.update(r.get(side+'_id') for r in personnel for side in ('from','to'))
    wanted=set(int(v) for v in cargo_ids)
    locations.update(r[side+'_location_id'] for r in snapshot['cargo'] if r['no'] in wanted for side in ('from','to'))
    locations.update(r['id'] for r in snapshot['locations'] if r['kind']=='SHORE')
    return {'voyage_id':snapshot['voyage_id'], 'location_ids':sorted(locations-{None}),'cargo_ids':sorted(wanted)}


def dependency_hash(snapshot, dependencies):
    wanted=set(dependencies['cargo_ids'])
    return digest({'identity':snapshot.get('ledger_identity'), 'generation':snapshot.get('source_generation',0),
        'voyage_id':snapshot['voyage_id'], 'voyage_name':snapshot['voyage_name'], 'archived':snapshot['archived'],
        'current_stop_id':snapshot['current_stop_id'] if dependencies.get('mode') in {'Complete','Remaining'} else None,
        'stops':snapshot.get('reference_stops',snapshot['stops']),
        'locations':[r for r in snapshot['locations'] if r['id'] in dependencies['location_ids']],
        'cargo':[r for r in snapshot['cargo'] if r['no'] in wanted],
        'settings':{k:snapshot['settings'].get(k,'') for k in ('port_name','transfer_vessel_name')}})


def source_matches(plan, snapshot):
    if plan.get('source_dependencies'):
        return dependency_hash(snapshot,plan['source_dependencies'])==plan.get('dependency_hash')
    return snapshot['source_hash']==plan['source_hash']


def crew_source_matches(plan, snapshot):
    """Cargo execution cannot invalidate an otherwise unchanged Final crew route."""
    if source_matches(plan, snapshot):
        return True
    if (plan.get('mode') != 'Final' or plan.get('source_identity') != snapshot.get('ledger_identity')
        or plan.get('source_generation', 0) != snapshot.get('source_generation', 0)
        or plan.get('voyage_id') != snapshot.get('voyage_id')):
        return False
    dependencies = plan.get('personnel_dependencies')
    if dependencies:
        return dependency_hash(snapshot, dependencies) == plan.get('personnel_dependency_hash')
    # Older snapshots have only a combined Cargo/Personnel fingerprint. Accept
    # them only when the complete intervening command history proves that the
    # route, fleet and settings have not changed. Never guess from ship names.
    previous, current = plan.get('source_revision'), snapshot['revision']
    if type(previous) is not int or current <= previous:
        return False
    allowed = ('create_transfer','edit_transfer','pick_up','deliver','correct_transfer',
               'void_transfer','restore_transfer','normalize_text_case','choose_stop','clear_current_stop')
    db = sqlite3.connect(Path(snapshot['source_path']).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        if db.execute('SELECT data_revision FROM app_state WHERE id=1').fetchone()[0] != current:
            return False
        row = db.execute('''SELECT count(*),count(DISTINCT revision),min(revision),max(revision),
            sum(CASE WHEN operation IN (''' + ','.join('?' for _ in allowed) + ''') THEN 0 ELSE 1 END)
            FROM command_receipts WHERE revision>? AND revision<=?''', (*allowed, previous, current)).fetchone()
        return row == (current-previous, current-previous, previous+1, current, 0)
    finally:
        db.close()


def read_cargo(path, *, selected_cargo=None, active_only=False):
    # Saved snapshots are data, not authority to contact a remote file server.
    # Check the lexical Windows path before resolve()/is_file() can access it.
    if PureWindowsPath(str(path)).drive.startswith('\\\\'):
        raise PersonnelError("Use a local Cargo database copy. Network and device paths are not supported for plan sources.")
    path = Path(path).resolve()
    if PureWindowsPath(str(path)).drive.startswith('\\\\'):
        raise PersonnelError("Use a local Cargo database copy. Network and device paths are not supported for plan sources.")
    if not path.is_file():
        raise PersonnelError("The Cargo ledger is unavailable. Open MarineOps first.")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        state = dict(conn.execute("SELECT * FROM app_state WHERE id=1").fetchone())
        locations = [dict(r) for r in conn.execute("SELECT * FROM locations ORDER BY name_key")]
        voyage = conn.execute("SELECT * FROM voyages WHERE id=?", (state["current_voyage_id"],)).fetchone()
        stops = [dict(r) for r in conn.execute("SELECT * FROM voyage_stops WHERE voyage_id=? AND removed=0 ORDER BY position,id",
                                             (state["current_voyage_id"],))]
        where,parameters='',[]
        if selected_cargo is not None:
            parameters=sorted(set(int(n) for n in selected_cargo))
            where=' WHERE t.no IN ('+','.join('?' for _ in parameters)+')' if parameters else ' WHERE 0'
        elif active_only:
            where=" WHERE t.is_void=0 AND t.status!='Done'"
        cargo = [dict(r) for r in conn.execute("SELECT t.*,c.cargo_tag FROM transfer_legs t JOIN cargo c ON c.id=t.cargo_id"+where+" ORDER BY t.no",parameters)]
        # Read evidence only for the selected/live rows, rather than all historical events.
        ids=[r['no'] for r in cargo]
        id_filter=' AND entity_id IN ('+','.join('?' for _ in ids)+')' if ids else ' AND 0'
        pickups = {str(r["entity_id"]): r["occurred_utc"] for r in conn.execute(
            "SELECT entity_id,occurred_utc FROM audit_events WHERE entity_type='transfer' AND (event_type='PICKUP' OR "
            "(event_type='TRANSFER_CORRECTED' AND json_extract(data_json,'$.after.status')='On Board' "
            "AND json_extract(data_json,'$.before.status')!='On Board'))"+id_filter+" ORDER BY id",ids)}
        for row in cargo:
            row["pickup_utc"] = pickups.get(str(row["no"]), "")
        settings = dict(conn.execute("SELECT key,value FROM settings"))
        has_identity=conn.execute("SELECT 1 FROM sqlite_master WHERE name='ledger_meta'").fetchone()
        identity=conn.execute("SELECT identity FROM ledger_meta WHERE id=1").fetchone()[0] if has_identity else str(path)
        conn.commit()
        snapshot = {"source_path": str(path),"ledger_identity":identity,"source_generation":workspace_files.generation(path),
                    "revision": state["data_revision"], "current_stop_id": state["current_stop_id"],
                    "voyage_id": state["current_voyage_id"], "voyage_name": voyage["name"] if voyage else "",
                    "archived": bool(voyage["archived"]) if voyage else False,
                    "voyage_created_utc": voyage["created_utc"] if voyage else "",
                    "stops": stops,"reference_stops":copy.deepcopy(stops), "locations": locations, "cargo": cargo, "settings": settings}
        snapshot["source_hash"] = digest(snapshot)
        return snapshot
    except sqlite3.Error as exc:
        raise PersonnelError("Could not read the Cargo ledger. Refresh after Cargo finishes saving.") from exc
    finally:
        conn.close()

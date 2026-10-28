"""Read-only dashboard projections; visits and saved plans retain their identities."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .coordination import workspace_files
from .personnel_cargo import read_cargo, crew_source_matches
from .personnel_import import digest
from .personnel_routes import leg_order
from .plan_store import version_summaries, version_payload


class DashboardDataError(ValueError):
    pass


def read_only(path):
    path = Path(path).resolve()
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    return connection


def read_cargo_summary(path):
    """One SQLite read transaction supplies the route, totals and current actions."""
    path = Path(path).resolve()
    generation = workspace_files.generation(path)
    db = read_only(path)
    try:
        db.execute('BEGIN')
        state = dict(db.execute('SELECT * FROM app_state WHERE id=1').fetchone())
        identity = db.execute('SELECT identity FROM ledger_meta WHERE id=1').fetchone()[0]
        voyage = db.execute('SELECT * FROM voyages WHERE id=?', (state['current_voyage_id'],)).fetchone()
        stops = [dict(r) for r in db.execute(
            'SELECT * FROM voyage_stops WHERE voyage_id=? AND removed=0 ORDER BY position,id',
            (state['current_voyage_id'],))]
        current = next((s for s in stops if s['id'] == state['current_stop_id']), None)
        settings = dict(db.execute('SELECT key,value FROM settings'))
        counts = {'Waiting': 0, 'On Board': 0, 'Done': 0}
        if voyage:
            # Reconstruct the backlog at departure from immutable status events.
            # This keeps old completed records out even after a later correction.
            started = voyage['created_utc']
            boundary = db.execute("SELECT min(id) FROM audit_events WHERE entity_type='voyage' AND entity_id=? AND event_type IN ('VOYAGE_CREATED','VOYAGE_COPIED')", (voyage['id'],)).fetchone()[0]
            counts.update({r['status']: r['n'] for r in db.execute("""
                SELECT t.status,count(*) n FROM transfer_legs t
                WHERE t.is_void=0 AND (CASE WHEN ? IS NOT NULL AND EXISTS(
                    SELECT 1 FROM audit_events a WHERE a.entity_type='transfer' AND a.entity_id=t.no AND a.event_type='TRANSFER_CREATED')
                    THEN EXISTS(SELECT 1 FROM audit_events a WHERE a.entity_type='transfer' AND a.entity_id=t.no AND a.event_type='TRANSFER_CREATED' AND a.id>?)
                    ELSE t.created_utc>=? END OR COALESCE(
                    (SELECT json_extract(e.data_json,'$.after.status') FROM audit_events e
                     WHERE e.entity_type='transfer' AND e.entity_id=t.no AND
                       CASE WHEN ? IS NOT NULL THEN e.id<? ELSE e.occurred_utc<? END
                       AND json_extract(e.data_json,'$.after.status') IN ('Waiting','On Board','Done')
                     ORDER BY e.id DESC LIMIT 1),
                    CASE WHEN t.completed_utc<? THEN 'Done' ELSE 'Waiting' END)!='Done')
                GROUP BY t.status
                """, (boundary, boundary, started, boundary, boundary, started, started))})
        rows, pickups, deliveries = [], 0, 0
        if current:
            vessel = current['vessel_id']
            pickups = db.execute("SELECT count(*) FROM transfer_legs WHERE is_void=0 AND status='Waiting' AND from_location_id=?", (vessel,)).fetchone()[0]
            deliveries = db.execute("SELECT count(*) FROM transfer_legs WHERE is_void=0 AND status='On Board' AND to_location_id=?", (vessel,)).fetchone()[0]
            rows = [dict(r) for r in db.execute("""
                SELECT t.no,c.cargo_tag,t.description,t.status,t.version,
                  CASE WHEN src.kind='SHORE' THEN src.name ELSE t.from_name_snapshot END from_name,
                  CASE WHEN dst.kind='SHORE' THEN dst.name ELSE t.to_name_snapshot END to_name,
                  CASE WHEN t.status='Waiting' THEN 'Pick up' ELSE 'Deliver' END action
                FROM transfer_legs t JOIN cargo c ON c.id=t.cargo_id
                  JOIN locations src ON src.id=t.from_location_id JOIN locations dst ON dst.id=t.to_location_id
                WHERE t.is_void=0 AND ((t.status='Waiting' AND t.from_location_id=?)
                  OR (t.status='On Board' AND t.to_location_id=?)) ORDER BY t.no LIMIT 200
                """, (vessel, vessel))]
        db.commit()
        return {'path': str(path), 'identity': identity, 'generation': generation,
                'revision': state['data_revision'], 'voyage_id': state['current_voyage_id'],
                'voyage_name': voyage['name'] if voyage else '', 'current_stop_id': state['current_stop_id'],
                'current_stop': current, 'stops': stops, 'settings': settings, 'counts': counts,
                'total': sum(counts.values()), 'pickups': pickups, 'deliveries': deliveries, 'cargo_rows': rows}
    finally:
        db.close()


def crew_at_visit(plan, stop_id):
    """Joining the stop vessel is Drop; leaving it is Pick up, never reversed."""
    stop = next((s for s in plan.get('stops', [])
                 if not isinstance(s.get('id'), bool) and s.get('id') == stop_id), None)
    if stop is None:
        return None
    rows = []
    for movement, group in (('Boarding', 'drop_passengers'), ('Leaving', 'pick_passengers')):
        seen = set()
        for task in stop.get(group, []):
            identity = task.get('person_id') or task['id']
            if identity in seen:
                continue
            seen.add(identity)
            rows.append({'id': identity, 'task_id': task['id'], 'name': task['name'],
                         'position': task.get('position', ''), 'movement': movement,
                         'leg': leg_order(task)})
    return rows


def personnel_progress(plan, visit_id):
    """Count transfer legs once, completing a leg only before its drop visit."""
    stops = plan.get('stops', [])
    current = next((i for i, s in enumerate(stops) if s['id'] == visit_id), None)
    if current is None:
        return None
    tasks = {}
    for index, stop in enumerate(stops):
        for group in ('pick_passengers', 'drop_passengers'):
            for task in stop.get(group, []):
                identifier = task.get('task_key') or 'Passengers:' + str(task['id'])
                entry = tasks.setdefault(identifier, {'drop': None})
                if group == 'drop_passengers':
                    entry['drop'] = index
    # Included unresolved tasks remain pending in a saved Draft.
    for identifier in plan.get('selected_tasks', plan.get('included', [])):
        if identifier.startswith('Passengers:'):
            tasks.setdefault(identifier, {'drop': None})
    completed = sum(t['drop'] is not None and t['drop'] < current for t in tasks.values())
    return {'Completed': completed, 'Pending': len(tasks) - completed}


def read_personnel_summary(path, cargo, selected_id=None, preferred_list=None, selected_visit=None):
    result = {'choices': [], 'selected_id': None, 'rows': [], 'boarding': None, 'leaving': None,
              'visit_choices': [], 'visit_id': None,
              'list_name': '', 'plan_label': '', 'status': 'empty',
              'message': 'Open Personnel to generate and save a berthing plan.'}
    path = Path(path).resolve()
    if not path.is_file():
        return result
    if path.with_name(path.name + '.recovery-required.json').exists():
        result.update(status='error', message='Personnel recovery is required. Open Personnel for the preserved recovery information.')
        return result
    db = read_only(path)
    try:
        db.execute('BEGIN')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'module_meta', 'berth_versions', 'personnel_plans', 'passengers', 'module_settings'} <= tables:
            raise DashboardDataError('This is not a supported personnel database.')
        meta = db.execute('SELECT * FROM module_meta WHERE id=1').fetchone()
        if not meta or meta['version'] != 1:
            raise DashboardDataError('Unsupported personnel database version.')
        names = {r['id']: r['name'] for r in db.execute('SELECT id,name FROM personnel_plans')}
        plans = version_summaries(db)
        matching = []
        resolved_sources = {}
        cargo_path = Path(cargo['path']).resolve()
        for plan in plans:
            if not isinstance(plan, dict):
                raise DashboardDataError('A saved personnel plan is unreadable. Review it in Personnel.')
            source_path = plan.get('source_path')
            if plan.get('voyage_id') == cargo['voyage_id'] and source_path:
                if source_path not in resolved_sources:
                    resolved_sources[source_path] = Path(source_path).resolve()
                if resolved_sources[source_path] == cargo_path:
                    matching.append(plan)
        result['choices'] = [{'id': p['id'], 'label': f"{p['date']} / {names.get(p.get('personnel_plan_id'), 'Crew list')} / {p.get('status', 'Draft')} v{p['version']}"}
                             for p in matching]
        plan = next((p for p in matching if p['id'] == selected_id), None)
        # Family versions are monotonic even if the Windows clock moves back.
        # Preserve the history choices while automatic mode selects current snapshots.
        latest = {}
        for candidate in matching:
            family = candidate['family_id']
            if family not in latest or candidate['version'] > latest[family]['version']:
                latest[family] = candidate
        current = [p for p in matching if latest[p['family_id']]['id'] == p['id']]
        if plan is None:
            plan = next((p for p in current if preferred_list and p.get('personnel_plan_id') == preferred_list), None)
        if plan is None and current:
            plan = current[0]
        if plan is None:
            db.commit()
            return result
        plan = version_payload(db, plan['id'])
        if not isinstance(plan, dict):
            raise DashboardDataError('The selected personnel plan is unreadable. Review it in Personnel.')
        result.update(selected_id=plan['id'], list_name=names.get(plan.get('personnel_plan_id'), 'Crew list'),
                      plan_label=f"{plan.get('status', 'Draft')} v{plan['version']} / {plan['date']}")
        plan_id = plan.get('personnel_plan_id')
        live_context = {'path': str(path), 'identity': meta['identity'], 'generation': workspace_files.generation(path),
                        'plan_id': plan_id, 'plan_transfer_vessel': dict(db.execute('SELECT key,value FROM module_settings')).get('transfer_vessel_name', ''),
                        'scope': digest([dict(r) for r in db.execute('SELECT id,version,status FROM passengers WHERE plan_id=? ORDER BY id', (plan_id,))])}
        context_matches = not plan.get('personnel_context') or plan['personnel_context'] == live_context
        if not plan.get('personnel_context'):
            versions = plan.get('personnel_versions', {})
            live = [dict(r) for r in db.execute('SELECT id,version,status FROM passengers WHERE plan_id=?', (plan_id,))]
            context_matches = all(r['id'] in versions and r['version'] == versions[r['id']] for r in live if r['status'] != 'Cancelled')
        db.commit()
    finally:
        db.close()
    dependencies = plan.get('source_dependencies')
    source = read_cargo(cargo['path'], selected_cargo=dependencies.get('cargo_ids', []) if dependencies else None)
    if (source['revision'] != cargo['revision'] or source['current_stop_id'] != cargo['current_stop_id']
            or source['source_generation'] != cargo['generation']):
        raise DashboardDataError('Cargo changed while the overview was loading. Refresh the Dashboard.')
    can_refresh = (not selected_id and plan.get('mode') == 'Final' and
                   plan.get('personnel_context', {}).get('identity') == live_context['identity'] and
                   plan.get('personnel_context', {}).get('generation') == live_context['generation'])
    if (not context_matches and not can_refresh) or not crew_source_matches(plan, source):
        result.update(status='stale', message='This saved plan has changed sources. Open Personnel to regenerate and review it.')
        return result
    # Cargo verification can take time. Recheck the roster after it, so a save,
    # restore or history removal during loading cannot publish old names/counts.
    current_db=read_only(path)
    try:
        current_db.execute('BEGIN')
        current_meta=current_db.execute('SELECT identity FROM module_meta WHERE id=1').fetchone()[0]
        current_settings=dict(current_db.execute('SELECT key,value FROM module_settings'))
        current_context={'path':str(path),'identity':current_meta,'generation':workspace_files.generation(path),
                         'plan_id':plan_id,'plan_transfer_vessel':current_settings.get('transfer_vessel_name',''),
                         'scope':digest([dict(r) for r in current_db.execute('SELECT id,version,status FROM passengers WHERE plan_id=? ORDER BY id',(plan_id,))])}
        hidden='removed_berth_history' in tables and current_db.execute('SELECT 1 FROM removed_berth_history WHERE version_id=?',(plan['id'],)).fetchone() is not None
        if not context_matches and can_refresh and current_context == live_context and not hidden:
            from .personnel_service import PersonnelService
            from .crew_plan_sync import refresh_crew_plan
            view = PersonnelService.read_view(current_db, path)
            plan = refresh_crew_plan(plan, view.planning_source(source), view.crew_records(plan_id, source), current_context)
            result['plan_label'] += ' / current crew'
        current_db.commit()
    finally:
        current_db.close()
    if current_context!=live_context or hidden:
        result.update(status='stale',message='Personnel changed while loading. Refresh the Dashboard and review the saved plan.')
        return result
    if cargo['current_stop_id'] is None:
        result.update(message='Select a current visit to see its planned personnel.')
        return result
    vessel_id = cargo['current_stop']['vessel_id']
    visits = [s for s in plan.get('stops', []) if s.get('vessel_id') == vessel_id]
    result['visit_choices'] = [{'id': s['id'], 'label': f"Plan visit {i + 1} / {s['name']}"}
                               for i, s in enumerate(plan['stops']) if s.get('vessel_id') == vessel_id]
    visit_id = selected_visit if any(s['id'] == selected_visit for s in visits) else None
    if visit_id is None and any(s['id'] == cargo['current_stop_id'] for s in visits):
        visit_id = cargo['current_stop_id']
    if visit_id is None and len(visits) == 1:
        visit_id = visits[0]['id']
    if visit_id is None and len(visits) > 1:
        result.update(status='choose_visit', message='This vessel has multiple personnel calls. Choose the actual plan visit below.')
        return result
    rows = crew_at_visit(plan, visit_id)
    if rows is None:
        result.update(message='The current Cargo visit is not in this personnel plan. Review the plan route in Personnel.')
        return result
    result.update(status='ready', rows=rows, boarding=sum(r['movement'] == 'Boarding' for r in rows),
                  progress=personnel_progress(plan, visit_id),
                  visit_id=visit_id,
                  leaving=sum(r['movement'] == 'Leaving' for r in rows),
                  message='Planned movements at this exact visit.' + (' Review issues remain in this Draft.' if plan.get('issues') else ''))
    return result


def read_dashboard(cargo_path, personnel_path, selected_id=None, preferred_list=None, selected_visit=None):
    cargo = read_cargo_summary(cargo_path)
    try:
        personnel = read_personnel_summary(personnel_path, cargo, selected_id, preferred_list, selected_visit)
    except (sqlite3.Error, ValueError, KeyError, TypeError, OSError) as exc:
        personnel = {'choices': [], 'selected_id': None, 'rows': [], 'boarding': None, 'leaving': None,
                     'list_name': '', 'plan_label': '', 'status': 'error',
                     'message': 'Personnel summary could not load: ' + str(exc)}
    if workspace_files.generation(cargo_path) != cargo['generation']:
        raise DashboardDataError('The Cargo database was replaced while loading. Refresh the Dashboard.')
    return {'cargo': cargo, 'personnel': personnel}

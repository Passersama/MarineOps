"""Read immutable plan metadata first; decode only requested snapshots."""
import json
from .personnel_import import PersonnelError, iso_date
from .source_paths import source_path_key, SourcePathError


def validate_plan_shape(value):
    """The same readable snapshot contract applies to writes and backup restore."""
    if (not isinstance(value, dict) or not {'stops','date','mode','issues'} <= value.keys()
        or not isinstance(value['stops'],list) or not isinstance(value['issues'],list)
        or any(not isinstance(p,dict) or not isinstance(p.get('message'),str) for p in value['issues'])
        or not iso_date(value['date']) or value['mode'] not in {'Final','Complete','Remaining'}
        or any(not isinstance(s,dict) or not {'id','number','name','vessel_id'} <= s.keys()
               or any(not isinstance(s.get(g),list) for g in
                      ('drop_passengers','pick_passengers','drop_materials','pick_materials'))
               for s in value['stops'])):
        raise PersonnelError('This plan has an invalid berthing snapshot. Review or regenerate it before saving.')
    try:
        for field in ('source_path', 'personnel_source_path'):
            if value.get(field) is not None:
                source_path_key(value[field])
    except SourcePathError as exc:
        raise PersonnelError(str(exc)) from exc


def visible_clause(db, alias='b', include_removed=False):
    managed = db.execute("SELECT 1 FROM sqlite_master WHERE name='removed_berth_history'").fetchone()
    return '1' if include_removed or not managed else (
        f'NOT EXISTS (SELECT 1 FROM removed_berth_history r WHERE r.version_id={alias}.id)')


def version_summaries(db, include_removed=False):
    return [dict(row) for row in db.execute(f"""
        SELECT b.id,b.family_id,b.version,b.status,b.created_utc,
          json_extract(b.payload,'$.date') date,
          json_extract(b.payload,'$.mode') mode,
          json_extract(b.payload,'$.voyage_id') voyage_id,
          json_extract(b.payload,'$.voyage_name') voyage_name,
          json_extract(b.payload,'$.source_path') source_path,
          json_extract(b.payload,'$.personnel_plan_id') personnel_plan_id
        FROM berth_versions b WHERE {visible_clause(db, include_removed=include_removed)}
        ORDER BY b.created_utc DESC,b.version DESC,b.id
        """)]


def version_payload(db, identifier):
    row = db.execute(f'SELECT b.payload FROM berth_versions b WHERE b.id=? AND {visible_clause(db)}',
                     (identifier,)).fetchone()
    return json.loads(row[0]) if row else None


def latest_family_payloads(db, plan_ids):
    wanted = sorted(set(plan_ids))
    if not wanted:
        return []
    placeholders = ','.join('?' for _ in wanted)
    return [json.loads(row[0]) for row in db.execute(f"""
        SELECT b.payload FROM berth_versions b
        WHERE {visible_clause(db)} AND json_extract(b.payload,'$.personnel_plan_id') IN ({placeholders})
          AND NOT EXISTS (SELECT 1 FROM berth_versions later
            WHERE later.family_id=b.family_id AND later.version>b.version AND {visible_clause(db, 'later')})
        ORDER BY b.created_utc DESC,b.version DESC
        """, wanted)]


def latest_family_payload(db, family_id):
    row = db.execute(f"""SELECT b.payload FROM berth_versions b
        WHERE b.family_id=? AND {visible_clause(db)} ORDER BY b.version DESC LIMIT 1""", (family_id,)).fetchone()
    return json.loads(row[0]) if row else None

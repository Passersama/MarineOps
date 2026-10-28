"""Verify upgrade mapping using SELECT-only access; report no passenger names."""
import copy
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', nargs='?', default='artifacts/personnel-final')
parser.add_argument('--data-dir', required=True, type=Path)
parser.add_argument('--workbook', required=True, type=Path)
args = parser.parse_args()
output = ROOT / args.output
output.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'src'))
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_service import PersonnelService
from cargo_track.berth_plan import generate_plan
from cargo_track.personnel_import import read_personnel_excel

directory = args.data_dir.resolve()
paths = [directory / n for n in ('cargo-track.sqlite3', 'personnel-transfer.sqlite3')]
before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
source = read_cargo(paths[0])
service = object.__new__(PersonnelService)
service.path = paths[1]
service.db = sqlite3.connect(paths[1].as_uri() + '?mode=ro', uri=True)
service.db.row_factory = sqlite3.Row
service.db.execute('PRAGMA query_only=ON')
try:
    plan_id = service.db.execute('SELECT id FROM personnel_plans ORDER BY created_utc DESC LIMIT 1').fetchone()[0]
    crew = service.crew_records(plan_id, source)
    assert len(crew) == 5
    assert all(r['from_id'] and r['to_id'] for r in crew)
    source_hash = source['source_hash']
    modified = copy.deepcopy(source)
    used = {s['vessel_id'] for s in source['stops']}
    needed = {r[side + '_id'] for r in crew for side in ('from', 'to')}
    added = []
    for loc in source['locations']:
        if loc['kind'] == 'VESSEL' and loc['id'] in needed - used:
            modified['stops'].append({'id': 'plan:' + str(uuid4()), 'vessel_id': loc['id'], 'vessel_name_snapshot': loc['name']})
            added.append(loc['name'])
    final = generate_plan(modified, crew, [], '2026-10-06', service.settings()['port_name'], mode='Final')
    assert not final['issues'], final['issues']
    assert sum(len(s['pick_passengers']) for s in final['stops']) == 1
    assert sum(len(s['drop_passengers']) for s in final['stops']) == 5
    sample = args.workbook.resolve()
    sample_before = hashlib.sha256(sample.read_bytes()).hexdigest()
    records = read_personnel_excel(sample)['records']
    assert len(records) == 5 and all(r['date'] == '2026-10-06' for r in records)
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == sample_before
    assert read_cargo(paths[0])['source_hash'] == source_hash
finally:
    service.db.close()
assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
report = {'existing_crew_count': len(crew), 'all_vessels_matched': True, 'missing_vessels_added_to_plan': added,
          'final_pick_passengers': 1, 'final_drop_passengers': 5, 'source_workbook_dates_recognized': 5,
          'user_databases_unchanged': True, 'user_workbook_unchanged': True, 'access': 'SELECT only; no export of passenger names'}
(output / 'existing-crew-readonly.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))

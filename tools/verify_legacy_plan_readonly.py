"""Rebuild user legacy plans without modifying files or reporting crew names."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication, QWidget, QComboBox
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_ui import CrewPlanBuilder
from cargo_track.berth_plan import plan_review_groups
if len(sys.argv) != 2:raise SystemExit('Usage: verify_legacy_plan_readonly.py DATA_DIRECTORY')
directory = Path(sys.argv[1]).resolve()
paths = [directory / name for name in ('cargo-track.sqlite3', 'personnel-transfer.sqlite3')]
before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
service = object.__new__(PersonnelService)
service.path = paths[1]
service.db = sqlite3.connect(paths[1].as_uri() + '?mode=ro', uri=True)
service.db.row_factory = sqlite3.Row
service.db.execute('PRAGMA query_only=ON')
app = QApplication([])
class Owner(QWidget):
    def plan_date(self):
        dates = {r['date'] for r in service.crew_records(self.plan_combo.currentData(), source) if r.get('date')}
        return next(iter(dates)) if len(dates) == 1 else '2026-10-06'
source = read_cargo(paths[0])
reports = []
try:
    plans = [p for p in service.berth_versions() if p['mode'] != 'Final' and
             p['source_path'] == source['source_path'] and p['voyage_id'] == source['voyage_id']]
    assert plans, 'No matching legacy plan found'
    for plan in plans:
        owner = Owner()
        owner.service = service
        owner.host = type('Host', (), {'database_path': paths[0]})()
        owner.plan_combo = QComboBox(owner)
        owner.plan_combo.addItem('Existing crew list', plan.get('personnel_plan_id'))
        builder = CrewPlanBuilder(owner, base_plan=plan)
        final = builder.build()
        reports.append({'original_mode': plan['mode'], 'original_checks': len(plan['issues']),
            'original_review_entries': len(plan_review_groups(plan)), 'rebuilt_mode': final['mode'],
            'rebuilt_review_entries': len(plan_review_groups(final)),
            'rebuilt_checks': [{'kind': g['task'].split(':')[0], 'messages': g['messages']} for g in plan_review_groups(final)],
            'material_routes_needing_review': [{'material': r['description'], 'from': r['from_name_snapshot'], 'to': r['to_name_snapshot']}
                for r in source['cargo'] if 'Materials:' + str(r['no']) in {g['task'] for g in plan_review_groups(final)}],
            'pick_passengers': sum(len(s['pick_passengers']) for s in final['stops']),
            'drop_passengers': sum(len(s['drop_passengers']) for s in final['stops']),
            'selected_materials': sum(key.startswith('Materials:') for key in final['selected_tasks'])})
        builder.close()
        owner.close()
finally:
    service.db.close()
assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
report = {'user_files_unchanged': True, 'access': 'SELECT only', 'legacy_plans': reports}
(ROOT / 'artifacts/personnel-load-fix/legacy-user-readonly.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))

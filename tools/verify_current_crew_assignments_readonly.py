"""Diagnose the current saved crew list without writing databases or names."""
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import hashlib,json,os,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'output/crew-assignment-matching-20261021';OUT.mkdir(parents=True,exist_ok=True)
if len(sys.argv) != 2:raise SystemExit('Usage: verify_current_crew_assignments_readonly.py DATA_DIRECTORY')
data=Path(sys.argv[1]).resolve()
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_ui import CrewPlanBuilder
from PySide6.QtWidgets import QApplication,QWidget,QComboBox
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
paths=[data/name for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3')]
before={p.name:sha(p) for p in paths}
service=object.__new__(PersonnelService);service.path=paths[1].resolve()
service.db=sqlite3.connect(service.path.as_uri()+'?mode=ro',uri=True);service.db.row_factory=sqlite3.Row
service.db.execute('PRAGMA query_only=ON');assert service.db.execute('PRAGMA query_only').fetchone()[0]==1
app=QApplication.instance() or QApplication([])
owner=QWidget();owner.service=service;owner.host=SimpleNamespace(database_path=paths[0])
try:
    selected=service.db.execute('SELECT id,date FROM personnel_plans ORDER BY created_utc DESC LIMIT 1').fetchone()
    owner.plan_combo=QComboBox();owner.plan_combo.addItem('Current crew list',selected['id'])
    owner.plan_date=lambda:selected['date'];source=read_cargo(paths[0])
    crew=service.crew_records(selected['id'],source)
    editor=CrewPlanBuilder(owner,inline=True)
    try:
        assignments=sum(combo.currentData() in combo.feasible_options for combo in editor.assignments)
        review=sum(any('Review assignment'==control.currentText() for control in controls) for controls in editor.endpoint_controls)
        assert assignments==len(crew) and review==0
        assert all(r['direction'] in ('Sign-on','Sign-off') for r in crew)
        assert all(r['from_id'] and r['to_id'] for r in crew)
        draft=editor.build()
        report={'result':'PASS','access':'SQLite mode=ro; PRAGMA query_only=ON','crew_records':len(crew),
                'matched_vessels':len(crew),'valid_route_assignments':assignments,'review_assignments':review,
                'directions':dict(Counter(r['direction'] for r in crew)),
                'ship_short_names':{label:service.resolve_location(source,label)['name'] for label in ('DFKT 2','SPR','BVC','BGP INV')},
                'remaining_data_issues':dict(Counter(issue['message'] for issue in draft['issues'])),
                'cargo_unchanged':sha(paths[0])==before[paths[0].name],
                'personnel_unchanged':sha(paths[1])==before[paths[1].name]}
        assert report['cargo_unchanged'] and report['personnel_unchanged']
        (OUT/'current-crew-readonly.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:editor.deleteLater();app.processEvents()
finally:owner.deleteLater();app.processEvents();service.db.close()

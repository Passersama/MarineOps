"""Prepare copied fictional data using the public services, never user databases."""
from pathlib import Path
import json,sqlite3,sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.berth_plan import generate_plan
from cargo_track.dashboard_data import read_dashboard

target=Path(sys.argv[1]).resolve()
allowed=(ROOT/'artifacts/validation-1.2.1').resolve()
assert target.is_relative_to(allowed) and not target.exists(),target
source=Path(json.loads((ROOT/'output/dashboard-release-20261012/native-checks.json').read_text())['data_directory'])
assert source.is_relative_to((ROOT/'output/dashboard-release-20261012').resolve())
target.mkdir(parents=True)
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):
    with sqlite3.connect((source/name).as_uri()+'?mode=ro',uri=True) as original,sqlite3.connect(target/name) as copy:
        original.backup(copy)
cargo=ApplicationService(target/'cargo-track.sqlite3');cargo.open()
for stop in cargo.workspace_snapshot()['stops'][7:]:cargo.handle(Command(str(uuid4()),'remove_stop',{'stop_id':stop['id']}))
cargo.close()
personnel=PersonnelService(target/'personnel-transfer.sqlite3')
crew=personnel.plans()[0]['id'];records=personnel.passengers(crew)
personnel.remove_crew_entries({r['id']:r['version'] for r in records if r['name'].startswith('Large Roster ')})
first=next(r for r in records if r['name']=='Chen Wei');first['position']='Second Engineer'
personnel.edit_crew_entry(first['id'],first,first['version'])
source=personnel.planning_source(read_cargo(target/'cargo-track.sqlite3',active_only=True))
plan=generate_plan(source,personnel.crew_records(crew,source),[],'2026-10-12',personnel.port_name(source),mode='Final',personnel_plan_id=crew)
assert not plan['issues'],plan['issues']
plan.update(personnel_context=personnel.context(crew),personnel_source_path=str(personnel.path))
saved=personnel.save_berth(plan,True);personnel.close()
overview=read_dashboard(target/'cargo-track.sqlite3',target/'personnel-transfer.sqlite3',saved['id'])
assert overview['personnel']['status']=='ready'
assert (overview['personnel']['boarding'],overview['personnel']['leaving'])==(28,19)
print(json.dumps({'data':str(target),'boarding':28,'leaving':19,'fictional_data':True}))

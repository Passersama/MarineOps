"""Copy only the isolated legacy fixture and bind a fresh plan to its new path."""
from pathlib import Path
import json
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.berth_plan import generate_plan
from cargo_track.dashboard_data import read_dashboard

target=Path(sys.argv[1]).resolve();allowed=(ROOT/'artifacts/validation-1.2.1').resolve()
assert target.is_relative_to(allowed) and not target.exists()
source=Path(json.loads((ROOT/'output/personnel-leg-hotfix-20261012/native-checks.json').read_text(encoding='utf-8'))['data_directory'])
assert source.is_relative_to((ROOT/'output/personnel-leg-hotfix-20261012').resolve())
target.mkdir(parents=True)
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):
    with sqlite3.connect((source/name).as_uri()+'?mode=ro',uri=True) as original,sqlite3.connect(target/name) as destination:original.backup(destination)
service=PersonnelService(target/'personnel-transfer.sqlite3');roster=service.plans()[0]['id']
snapshot=service.planning_source(read_cargo(target/'cargo-track.sqlite3'))
people=service.crew_records(roster,snapshot)
plan=generate_plan(snapshot,people,[],'2026-10-12',service.port_name(snapshot),mode='Final',personnel_plan_id=roster)
assert not plan['issues'];plan.update(personnel_context=service.context(roster),personnel_source_path=str(service.path))
saved=service.save_berth(plan,True);service.close()
overview=read_dashboard(target/'cargo-track.sqlite3',target/'personnel-transfer.sqlite3',saved['id'])
assert overview['personnel']['status']=='ready'
assert (overview['personnel']['boarding'],overview['personnel']['leaving'])==(0,2)
print(json.dumps({'directory':str(target),'legacy_root_records':6,'total_legs':7,'boarding':0,'leaving':2,'fictional_data':True}))

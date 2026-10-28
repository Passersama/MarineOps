"""Build a freshly bound automatic plan in an isolated copy of fictional data."""
from pathlib import Path
import copy
import json
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.berth_optimizer import make_problem,solve,materialize
from cargo_track.berth_plan import cargo_tasks,generate_plan
from cargo_track.dashboard_data import read_dashboard

target=Path(sys.argv[1]).resolve();allowed=(ROOT/'artifacts/validation-1.2.1').resolve()
assert target.is_relative_to(allowed) and not target.exists()
source=Path(json.loads((ROOT/'output/berth-optimizer-release-20261012/native-checks.json').read_text(encoding='utf-8'))['data_directory'])
assert source.is_relative_to((ROOT/'output/berth-optimizer-release-20261012').resolve())
target.mkdir(parents=True)
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):
    with sqlite3.connect((source/name).as_uri()+'?mode=ro',uri=True) as original,sqlite3.connect(target/name) as destination:
        original.backup(destination)
service=PersonnelService(target/'personnel-transfer.sqlite3')
roster=service.plans()[0]['id'];snapshot=service.planning_source(read_cargo(target/'cargo-track.sqlite3',active_only=True))
people=service.crew_records(roster,snapshot);numbers=[r['no'] for r in snapshot['cargo']]
problem=make_problem(snapshot,people,cargo_tasks(snapshot,numbers))
result=solve(problem);assert result['status']=='OPTIMAL' and result['cost']==[5,0]
stops,assignments=materialize(result,snapshot,snapshot['stops']);snapshot['reference_stops']=copy.deepcopy(snapshot['stops']);snapshot['stops']=stops
plan=generate_plan(snapshot,people,numbers,'2026-10-12',service.port_name(snapshot),mode='Final',assignments=assignments,personnel_plan_id=roster,transport_contract=problem)
assert not plan['issues'],plan['issues']
plan.update(personnel_context=service.context(roster),personnel_source_path=str(service.path),optimization={k:result[k] for k in ('status','cost','lower_bound','problem_hash')})
saved=service.save_berth(plan,True);service.close()
overview=read_dashboard(target/'cargo-track.sqlite3',target/'personnel-transfer.sqlite3',saved['id'])
assert overview['personnel']['status']=='ready'
assert (overview['personnel']['boarding'],overview['personnel']['leaving'])==(2,1)
print(json.dumps({'directory':str(target),'minimum_calls':5,'boarding':2,'leaving':1,'fictional_data':True}))

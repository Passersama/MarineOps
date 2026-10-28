"""Create fictional linked personnel in a fresh isolated release-test directory."""
from pathlib import Path
import json
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cargo_track.service import ApplicationService
from cargo_track.domain import Command
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.berth_plan import generate_plan, export_plan
from cargo_track import __version__

target=Path(sys.argv[1]).resolve()
assert target.is_relative_to((ROOT/f'artifacts/validation-{__version__}').resolve()) and not target.exists()
target.mkdir(parents=True)
cargo=ApplicationService(target/'cargo-track.sqlite3');cargo.open()
def command(name,values):return cargo.handle(Command(str(uuid4()),name,values)).result
fleet={name:command('create_vessel',{'name':name})['id'] for name in ('Alpha','Beta','Gamma')}
command('create_voyage',{'name':'Fictional multi-leg validation'})
for name in ('Gamma','Alpha','Alpha','Beta','Beta','Gamma'):command('add_stop',{'vessel_id':fleet[name]})
cargo.close()
service=PersonnelService(target/'personnel-transfer.sqlite3')
try:
    roster=service.create_plan('Fictional linked crew','2026-10-25')
    source=service.planning_source(read_cargo(target/'cargo-track.sqlite3'))
    def record(a,b):return service.bind_record({'name':'Fictional Person','position':'Engineer',
        'date':'2026-10-25','direction':'Transfer','from_name':a,'to_name':b},source)
    root=service.add_passenger(roster,record('Gamma','Alpha'))
    first=service.add_passenger(roster,record('Alpha','Beta'))
    removed=service.add_next_leg(first,record('Beta','Gamma'),source,0)
    service.remove_crew_entries({removed:0})
    historical=service.passenger(removed)
    service.link_crew_legs([root,first],{root:0,first:0})
    service.add_next_leg(first,record('Beta','Gamma'),source,1)
    assert service.passenger(removed)==historical
    plan=generate_plan(source,service.crew_records(roster,source),[],'2026-10-25',service.port_name(source),
        mode='Final',personnel_plan_id=roster)
    assert not plan['issues'],plan['issues']
    plan['personnel_context']=service.context(roster)
    plan['personnel_source_path']=str(service.path)
    export_plan(service.save_berth(plan,True),target/'fixture.xlsx')
    (target/'fixture-metadata.json').write_text(json.dumps({'removed_leg_history_preserved':True,
        'legacy_removed_reference_differs_from_current_parent':historical['person_id']!=service.passenger(first)['person_id'],
        'active_legs':3,'removed_legs':1}),encoding='utf-8')
finally:service.close()

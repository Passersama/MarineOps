"""Create a fresh fictional release fixture; never opens production storage."""
from pathlib import Path
import argparse
import json
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.berth_plan import generate_plan


def create_fixture(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    cargo=ApplicationService(directory/'cargo-track.sqlite3');cargo.open()
    personnel=PersonnelService(directory/'personnel-transfer.sqlite3')
    def cmd(name,value):return cargo.handle(Command(str(uuid4()),name,value)).result
    try:
        a=cmd('create_vessel',{'name':'Fictional Alpha'})['id']
        b=cmd('create_vessel',{'name':'Fictional Bravo'})['id']
        cmd('create_voyage',{'name':'Fictional release route'})
        first=cmd('add_stop',{'vessel_id':a})['stop_id'];cmd('add_stop',{'vessel_id':b})
        cmd('choose_stop',{'stop_id':first})
        cmd('create_transfer',{'description':'Fictional GPS cable','from_location_id':a,'to_location_id':b})
        source=read_cargo(cargo.path)
        crew=personnel.create_plan('Fictional release crew','2026-10-29')
        record=personnel.bind_record({'name':'Alex Fictional','position':'Engineer','date':'2026-10-29',
            'direction':'Transfer','from_name':'Fictional Alpha','to_name':'Fictional Bravo'},source)
        personnel.add_passenger(crew,record)
        plan=generate_plan(source,personnel.crew_records(crew,source),[], '2026-10-29',personnel.port_name(source),
                           mode='Final',personnel_plan_id=crew)
        plan['personnel_context']=personnel.context(crew)
        personnel.save_berth(plan,True)
    finally:
        personnel.close();cargo.close()
    (directory/'fixture-metadata.json').write_text(json.dumps({'fictional_data':True,'active_crew':1,'cargo_records':1}),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    create_fixture(parser.parse_args().directory)

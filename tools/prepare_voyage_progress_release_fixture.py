"""Copy fictional multi-voyage data and bind a fresh current personnel plan."""
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
target=Path(sys.argv[1]).resolve();allowed=(ROOT/'artifacts/validation-1.2.1').resolve()
assert target.is_relative_to(allowed) and not target.exists()
source=Path(json.loads((ROOT/'output/voyage-progress-20261012/native-checks.json').read_text(encoding='utf-8'))['data_directory'])
assert source.is_relative_to((ROOT/'output/voyage-progress-20261012').resolve())
target.mkdir(parents=True)
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):
    with sqlite3.connect((source/name).as_uri()+'?mode=ro',uri=True) as original,sqlite3.connect(target/name) as destination:original.backup(destination)
cargo=ApplicationService(target/'cargo-track.sqlite3');cargo.open()
stops=sorted((s['id'] for s in cargo.workspace_snapshot()['stops']))
cargo.handle(Command(str(uuid4()),'reorder_stops',{'stop_ids':stops}));cargo.close()
service=PersonnelService(target/'personnel-transfer.sqlite3');roster=service.plans()[0]['id']
snapshot=service.planning_source(read_cargo(target/'cargo-track.sqlite3',active_only=True))
plan=generate_plan(snapshot,service.crew_records(roster,snapshot),[],'2026-10-12',service.port_name(snapshot),mode='Final',personnel_plan_id=roster)
assert not plan['issues'],plan['issues']
plan.update(personnel_context=service.context(roster),personnel_source_path=str(service.path));saved=service.save_berth(plan,True);service.close()
overview=read_dashboard(target/'cargo-track.sqlite3',target/'personnel-transfer.sqlite3',saved['id'])
assert overview['cargo']['counts']=={'Waiting':2,'On Board':1,'Done':1}
assert overview['personnel']['progress']=={'Completed':1,'Pending':3}
print(json.dumps({'directory':str(target),'fictional_data':True,'cargo':overview['cargo']['counts'],'personnel':overview['personnel']['progress']}))

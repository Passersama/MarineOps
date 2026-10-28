"""Reproduce false-positive health using a deliberately damaged fictional ledger."""
from pathlib import Path
import json,sys,time
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
baseline='--baseline' in sys.argv
sys.path.insert(0,str(ROOT/'output/dashboard-release-20261012/baseline/src' if baseline else ROOT/'src'))
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.worker import DatabaseWorker
out=ROOT/'output/dashboard-release-20261012';data=out/('health-fixture-'+str(time.time_ns()));data.mkdir()
service=ApplicationService(data/'cargo-track.sqlite3');service.open()
def command(name,payload):return service.handle(Command(str(uuid4()),name,payload)).result
vessel=command('create_vessel',{'name':'Fictional vessel'})['id']
command('create_voyage',{'name':'Fictional health probe'})
stop=command('add_stop',{'vessel_id':vessel})['stop_id']
service.db.execute('PRAGMA foreign_keys=OFF');service.db.execute('UPDATE voyage_stops SET vessel_id=999999 WHERE id=?',(stop,))
worker=DatabaseWorker(service.path);worker.service=service;responses=[]
worker.result.connect(lambda request,result:responses.append(result));worker.request('probe','_health',{})
report={'baseline':baseline,'intentionally_broken_foreign_key':True,'health':responses[0]['data']}
(out/('health-before.json' if baseline else 'health-after.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2));service.close()

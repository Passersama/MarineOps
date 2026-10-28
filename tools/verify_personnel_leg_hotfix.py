"""Reproduce a legacy roster mixed with new linked legs on the real Windows UI."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'output/personnel-leg-hotfix-20261012';OUT.mkdir(parents=True,exist_ok=True)
data=OUT/('fixture-'+str(time.time_ns()));data.mkdir()
os.environ['CARGO_TRACK_DATA_DIR']=str(data)
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from cargo_track.appearance import configure_application
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_ui import CrewPlanBuilder
from cargo_track.berth_plan import export_plan,plan_assignments
from cargo_track.workspace import WorkspaceWindow

cargo=ApplicationService(data/'cargo-track.sqlite3');cargo.open()
def command(name,args):return cargo.handle(Command(str(uuid4()),name,args)).result
fleet={n:command('create_vessel',{'name':n})['id'] for n in ('BGP Victor','HB6','BGP Innovator','DFKT2','BGP Spirit')}
command('create_voyage',{'name':'Legacy mixed-leg validation'})
visits=[command('add_stop',{'vessel_id':fleet[n]})['stop_id'] for n in ('BGP Victor','HB6','BGP Innovator','DFKT2','HB6','BGP Victor','BGP Innovator','BGP Spirit')]
command('choose_stop',{'stop_id':visits[0]});cargo.close()
service=PersonnelService(data/'personnel-transfer.sqlite3');service.set_setting('transfer_vessel_name','Plan Boat')
roster=service.create_plan('Legacy roster','2026-10-12');source=read_cargo(data/'cargo-track.sqlite3')
def record(name,a,b):return service.bind_record({'name':name,'position':'OBS','from_name':a,'to_name':b,'date':'2026-10-12'},source)
legacy=[]
for i,(a,b) in enumerate((('BGP Victor','HB6'),('BGP Victor','BGP Innovator'),('BGP Innovator','BGP Spirit'),('DFKT2','BGP Victor'),('Plan Boat','BGP Spirit'),('Plan Boat','BGP Spirit'))):
    identifier=service.add_passenger(roster,record('Legacy Fictional '+str(i+1),a,b));legacy.append(identifier)
    payload=json.loads(service.db.execute('SELECT payload FROM passengers WHERE id=?',(identifier,)).fetchone()[0])
    payload.pop('leg_index',None);payload.pop('person_id',None)
    service.db.execute('UPDATE passengers SET payload=? WHERE id=?',(json.dumps(payload),identifier))
first=legacy[0]
second=service.add_next_leg(first,record('Legacy Fictional 1','HB6','BGP Spirit'),source,0)
raw_before=dict(service.db.execute('SELECT id,payload FROM passengers'));service.close()
cargo_before=hashlib.sha256((data/'cargo-track.sqlite3').read_bytes()).hexdigest()
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Legacy leg hotfix validation');QApplication.setApplicationName('Isolated validation')
app=QApplication([]);QSettings().setValue('appearance/theme','dark');configure_application(app)
window=WorkspaceWindow(data/'cargo-track.sqlite3',data)
def wait(predicate):
    until=time.monotonic()+15
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Legacy mixed-leg UI did not finish')
def settle():
    for _ in range(12):app.processEvents();time.sleep(.01)
report={'fictional_data':True,'data_directory':str(data),'platform':app.platformName()}
try:
    window.show();window.resize(1366,768);wait(lambda:window.snapshot and not window._refresh_wait)
    window.open_personnel();wait(lambda:window.personnel_page and window.personnel_page.source and not window.personnel_page._jobs)
    page=window.personnel_page;page.plan_combo.setCurrentIndex(page.plan_combo.findData(roster));wait(lambda:not page._jobs)
    builder=CrewPlanBuilder(page);draft=builder.build();builder.deleteLater();assert not draft['issues']
    rows={t['id']:t for s in draft['stops'] for g in ('pick_passengers','drop_passengers') for t in s[g]}
    assert len(rows)==7 and all(type(t['leg_index']) is int for t in rows.values())
    page.draft=draft;page.show_plan(draft);settle()
    assert page.live_builder is not None and page.save_plan_button.isEnabled() and page.plan_export_button.isEnabled()
    page.grab().save(str(OUT/'legacy-draft-fixed.png'))
    report.update(six_people_seven_legs=True,eight_calls=True,draft_editor_and_save_enabled=True)
    # Earlier saved versions have blank strings in groups. Read without rewriting.
    old=json.loads(json.dumps(draft))
    for stop in old['stops']:
        for group in ('pick_passengers','drop_passengers'):
            for task in stop[group]:
                if task['id'] in legacy:task['leg_index']=''
    saved_old=page.service.save_berth(old,True);frozen=json.loads(json.dumps(saved_old))
    page.show_plan(saved_old);settle();assert page.snapshot_rows.rowCount()==7
    page.show_plan(draft);settle();page.save_version(True);wait(lambda:not page._write_pending)
    saved=page.service.berth_versions()[0];export_plan(saved,OUT/'legacy-mixed-plan.xlsx')
    page.show_plan(saved);settle();assert page.plan_export_button.isEnabled()
    assert plan_assignments(saved)['Passengers:'+second]['pick']==visits[4]
    assert next(p for p in page.service.berth_versions() if p['id']==saved_old['id'])==frozen
    with sqlite3.connect((data/'personnel-transfer.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        assert dict(db.execute('SELECT id,payload FROM passengers'))==raw_before
    report.update(old_snapshot_loads_unchanged=True,legacy_roster_payloads_unchanged=True,publish_and_excel=True,linked_later_pickup_preserved=True)
    assert hashlib.sha256((data/'cargo-track.sqlite3').read_bytes()).hexdigest()==cargo_before
    report.update(cargo_unchanged=True,result='PASS')
    (OUT/'native-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
finally:
    if window.personnel_page:window.personnel_page.view_state.dirty=False
    window.close();app.processEvents()

"""Exercise real Qt pages with isolated fictional crew, saved updates and Dashboard."""
from pathlib import Path
import hashlib
import json
import os
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cargo_track import __version__
OUT=ROOT/f'output/crew-sync-{__version__}'
DATA=OUT/('native-'+str(time.time_ns()))
DATA.mkdir(parents=True)
os.environ['CARGO_TRACK_DATA_DIR']=str(DATA)
os.environ.pop('QT_QPA_PLATFORM',None)

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
from cargo_track.appearance import configure_application
from cargo_track.berth_plan import generate_plan, plan_assignments, export_plan
from cargo_track.domain import Command
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_service import PersonnelService
from cargo_track.service import ApplicationService
from cargo_track.workspace import WorkspaceWindow

app=QApplication([])
app.setOrganizationName('Cargo Track crew sync validation')
app.setApplicationName('Cargo Track crew sync validation')
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(DATA/'preferences'))
configure_application(app)

def wait(predicate):
    until=time.monotonic()+15
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.02)
    raise AssertionError('Native page did not finish loading')

cargo=ApplicationService(DATA/'cargo-track.sqlite3');cargo.open()
sequence=0
def command(name,payload):
    global sequence
    sequence+=1
    return cargo.handle(Command('crew-sync-'+str(sequence),name,payload)).result

a,b=[command('create_vessel',{'name':name})['id'] for name in ('BGP Challenger','BGP Innovator')]
command('create_voyage',{'name':'Fictional port crew change'})
visits=[command('add_stop',{'vessel_id':vessel})['stop_id'] for vessel in (a,b,a)]
command('choose_stop',{'stop_id':visits[0]})
source=read_cargo(cargo.path)
shore=next(r['id'] for r in source['locations'] if r['kind']=='SHORE')
source['stops'].insert(1,{'id':'plan:crew-port','vessel_id':shore,'vessel_name_snapshot':'xx port'})
personnel=PersonnelService(DATA/'personnel-transfer.sqlite3')
list_id=personnel.create_plan('Fictional roster','2026-10-27')
ids=[]
for name,direction in [('Omar Fictional','Sign-off'),('Alex Fictional','Sign-on')]:
    record=personnel.bind_record(dict(name=name,position='Engineer',date='2026-10-27',direction=direction,
                                    vessel='BGP Challenger'),source)
    ids.append(personnel.add_passenger(list_id,record))
plan=generate_plan(source,personnel.crew_records(list_id,source),[],'2026-10-27','xx port',mode='Final',personnel_plan_id=list_id)
assert not plan['issues'],plan['issues']
plan['personnel_context']=personnel.context(list_id)
saved=personnel.save_berth(plan,True)
assignments=plan_assignments(saved)
assert assignments['Passengers:'+ids[0]]=={'pick':visits[0],'drop':'plan:crew-port'}
assert assignments['Passengers:'+ids[1]]=={'pick':'plan:crew-port','drop':visits[2]}
cargo.close();personnel.close()
cargo_hash=hashlib.sha256((DATA/'cargo-track.sqlite3').read_bytes()).hexdigest()

window=WorkspaceWindow(DATA/'cargo-track.sqlite3',DATA)
window.resize(1366,900);window.show()
errors=[]
try:
    wait(lambda:window.snapshot is not None and window.dashboard_page.data is not None)
    dashboard=window.dashboard_page
    def inspect_about(navigation, name):
        def close_about():
            dialog=app.activeModalWidget()
            assert dialog.windowTitle()=='About MarineOps'
            assert dialog.version.text()=='Version '+__version__
            dialog.grab().save(str(OUT/('about-'+name+'.png')))
            dialog.accept()
        QTimer.singleShot(50,close_about)
        navigation.about_button.click()
    inspect_about(dashboard.navigation,'dashboard')
    inspect_about(window.navigation,'cargo')
    wait(lambda:dashboard.data['personnel']['status']=='ready')
    assert (dashboard.boarding.text(),dashboard.leaving.text())==('0','1')
    dashboard.scroll.ensureWidgetVisible(dashboard.crew_table);app.processEvents()
    window.grab().save(str(OUT/'dashboard-before.png'))
    window.open_personnel()
    page=window.personnel_page
    wait(lambda:page.source is not None and not page._jobs)
    inspect_about(page.navigation,'personnel')
    page.show_error=errors.append
    page.saved_plan=saved;page.show_plan(saved)
    record=page.service.passenger(ids[1])
    edited=page.service.bind_record({**record,'name':'Alex Updated','position':'Chief Engineer',
        'to_name':'BGP Innovator','vessel':'BGP Innovator'},page.source)
    page.run_write('edit_crew_entry',(record['id'],edited,record['version']),lambda _:page.crew_changed())
    wait(lambda:not page._write_pending and not page._jobs)
    current=page.displayed_plan
    assert current['id']!=saved['id'] and not current['issues'],(current,errors)
    assert plan_assignments(current)['Passengers:'+ids[1]]=={'pick':'plan:crew-port','drop':visits[1]}
    assert next(t for s in current['stops'] for t in s['drop_passengers'] if t['id']==ids[1])['name']=='Alex Updated'
    assert cargo_hash==hashlib.sha256((DATA/'cargo-track.sqlite3').read_bytes()).hexdigest()
    page.copy_complete()
    wait(lambda:page.live_builder is not None)
    page.refresh_live_preview()
    window.grab().save(str(OUT/'personnel-after.png'))
    # Persist the working route before navigating to Dashboard.
    page.save_version(True)
    wait(lambda:not page._write_pending and not page.view_state.dirty and not page._jobs)
    export_plan(page.saved_plan,OUT/'updated-berthing-plan.xlsx')
    assert not errors,errors
    window.show_dashboard()
    window._toggle_stop_id(visits[1])
    wait(lambda:window.snapshot['current_stop_id']==visits[1] and not window._busy)
    wait(lambda:dashboard.data['cargo']['current_stop_id']==visits[1] and dashboard.data['personnel']['status']=='ready')
    assert (dashboard.boarding.text(),dashboard.leaving.text())==('1','0')
    assert any(r['name']=='Alex Updated' for r in dashboard.crew_model.rows)
    dashboard.scroll.ensureWidgetVisible(dashboard.crew_table);app.processEvents()
    window.grab().save(str(OUT/'dashboard-after.png'))
    captures=[]
    for theme in ('light','dark'):
        dashboard.choose_theme(theme)
        for width,height in ((1366,900),(1000,700)):
            window.resize(width,height)
            for name,open_page,navigation in (
                ('dashboard',window.show_dashboard,dashboard.navigation),
                ('cargo',window.show_cargo,window.navigation),
                ('personnel',window.open_personnel,page.navigation)):
                open_page()
                wait(lambda:not window._busy and not page._jobs)
                if name=='dashboard':
                    wait(lambda:not dashboard._jobs and not dashboard.refresh_timer.isActive()
                         and dashboard.data['personnel']['status']=='ready' and dashboard.boarding.text()=='1')
                app.processEvents()
                assert not navigation.brand.pixmap().isNull()
                assert navigation.brand.pixmap().width()>navigation.brand.pixmap().height()
                assert navigation.brand.pixmap().hasAlphaChannel()
                assert window.width()==width,(name,theme,width,window.width())
                for control in (navigation.title,navigation.dashboard_button,navigation.cargo_button,navigation.personnel_button,navigation.about_button):
                    assert control.width()>=control.sizeHint().width(),(name,theme,width,control.objectName(),control.width(),control.sizeHint().width())
                filename=f'{name}-{theme}-{width}.png'
                window.grab().save(str(OUT/filename));captures.append(filename)
        inspect_about(page.navigation,theme)
    # The only Cargo write in this check is the explicit current-visit switch.
    report={'result':'PASS','version':__version__,'platform':app.platformName(),'data_directory':str(DATA),
        'real_port_pickup':True,'sign_off_before_port':True,'master_edit_updates_saved_plan':True,
        'from_to_updated_without_generate':True,'native_dashboard_before':{'boarding':0,'leaving':1},
        'native_dashboard_after':{'boarding':1,'leaving':0},'historical_version_retained':saved in page.service.berth_versions(),
        'saved_versions':len(page.service.berth_versions()),'excel_export':str(OUT/'updated-berthing-plan.xlsx'),
        'fictional_data_only':True,'cargo_unchanged_by_crew_update':True,'brand':'MarineOps',
        'about_all_three_workspaces':True,'english_help':True,
        'approved_logo':True,'theme_and_viewport_captures':captures,
        'screenshots':['dashboard-before.png','personnel-after.png','dashboard-after.png']}
    (OUT/'native-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
finally:
    if window.personnel_page:window.personnel_page.view_state.dirty=False
    window.close();app.processEvents()

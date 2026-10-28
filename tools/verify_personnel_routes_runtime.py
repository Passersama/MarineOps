"""Visible native workflow and exported fixture for the 1.1.8 personnel update."""
from pathlib import Path
import os
import sys
import time
import json
import copy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
os.environ.pop('QT_QPA_PLATFORM', None)
OUTPUT = ROOT / 'output/personnel-routes-20261011'
data = OUTPUT / ('native-' + str(time.time_ns()));data.mkdir(parents=True)
os.environ['CARGO_TRACK_DATA_DIR'] = str(data)
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QDialog
from cargo_track.service import ApplicationService
from cargo_track.domain import Command
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_ui import CrewPlanBuilder, PassengerForm
from cargo_track.berth_plan import plan_assignments, export_plan
from cargo_track.appearance import configure_application
from cargo_track.workspace import WorkspaceWindow

cargo = ApplicationService(data / 'cargo-track.sqlite3');cargo.open();seq=0
def command(name, values):
    global seq
    seq += 1
    return cargo.handle(Command(str(seq), name, values)).result
vessels={name:command('create_vessel',{'name':name})['id'] for name in
    ('BGP Victor','HB6','BGP Innovator','DFKT2','BGP Spirit','Niger')}
command('create_voyage',{'name':'20261011 Niger route'})
visits=[command('add_stop',{'vessel_id':vessels[name]})['stop_id'] for name in
    ('BGP Victor','HB6','BGP Innovator','DFKT2','HB6','BGP Victor','BGP Innovator')]
for name, source, target in (('Hard Disk','BGP Victor','BGP Innovator'),('GPS cable','HB6','DFKT2'),
                            ('QNAP','BGP Innovator','BGP Victor'),('Paper Box','BGP Innovator','BGP Spirit')):
    command('create_transfer',{'description':name,'from_location_id':vessels[source],
        'to_location_id':vessels[target],'physical_id':'','comment':''})
cargo.close()
service=PersonnelService(data/'personnel-transfer.sqlite3');service.set_setting('transfer_vessel_name','Niger')
plan_id=service.create_plan('Fictional multi-leg crew','2026-10-11')
def record(name, source, target, position='OBS'):
    return service.bind_record({'name':name,'position':position,'date':'2026-10-11','direction':'Transfer',
        'from_name':source,'to_name':target},read_cargo(data/'cargo-track.sqlite3'))
first=service.add_passenger(plan_id,record('Alex Fictional','Niger','HB6','Port Captain'))
second=service.add_next_leg(first,record('Alex Fictional','HB6','BGP Victor','Port Captain'),
    read_cargo(data/'cargo-track.sqlite3'),0)
aboard=service.add_passenger(plan_id,record('Sam Fictional','Niger','BGP Innovator'))
service.add_passenger(plan_id,record('Taylor Fictional','BGP Victor','BGP Innovator'))
service.close()
before=(data/'cargo-track.sqlite3').read_bytes()
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Personnel route validation');QApplication.setApplicationName('Personnel route validation')
app=QApplication([]);assert app.platformName()=='windows';configure_application(app)
window=WorkspaceWindow(data/'cargo-track.sqlite3',data)
def wait(predicate):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Native workflow timed out')
def settle():
    for _ in range(15):app.processEvents();time.sleep(.01)
report={'native_visible':True,'data_directory':str(data),'fictional_data':True}
builder=None
try:
    window.resize(1366,768);window.show();wait(lambda:window.snapshot is not None and not window._busy)
    QTest.mouseClick(window.personnel_button,Qt.MouseButton.LeftButton)
    wait(lambda:window.personnel_page is not None and window.personnel_page.source is not None)
    page=window.personnel_page
    wait(lambda:not page._jobs)
    page.plan_combo.setCurrentIndex(page.plan_combo.findData(plan_id))
    builder=CrewPlanBuilder(page)
    builder.show();settle()
    assert builder.route.count()==7 and not builder.added_names
    for task, include in zip(builder.tasks,builder.includes):
        if task['kind']=='Materials':include.setChecked(True)
    builder.refresh_assignments();draft=builder.build()
    assert not draft['issues'],draft['issues']
    assignments=plan_assignments(draft)
    assert assignments['Passengers:'+first]=={'pick':None,'drop':visits[1]}
    assert assignments['Passengers:'+second]=={'pick':visits[4],'drop':visits[5]}
    assert assignments['Passengers:'+aboard]=={'pick':None,'drop':visits[2]}
    assert len(draft['stops'])==7
    report.update(optional_port_not_appended=True,transfer_origin_drop_only=True,
                  next_leg_uses_later_repeated_visit=True)
    builder.grab().save(str(OUTPUT/'multi-leg-builder.png'))
    # Add, move and remove a Port call through the actual native editor actions.
    shore=next(r['id'] for r in builder.source['locations'] if r['kind']=='SHORE')
    builder.vessels.setCurrentIndex(builder.vessels.findData(shore));builder.add_stop()
    assert builder.build()['stops'][-1]['vessel_id']==shore
    builder.route.setCurrentRow(builder.route.count()-1);builder.move_stop(-1)
    assert builder.build()['stops'][-2]['vessel_id']==shore
    builder.remove_stop();assert len(builder.build()['stops'])==7
    report['port_add_move_remove']=True
    saved=page.service.save_berth(draft,True)
    workbook=OUTPUT/'Niger-plan-example.xlsx';export_plan(saved,workbook)
    frozen=copy.deepcopy(saved)
    builder.reject();builder.deleteLater();builder=None
    page.saved_plan=saved;page.draft=None;page.show_plan(saved);settle()
    assert 'Pick up 1 passengers: 1. Alex Fictional(Port Captain)' in page.preview.toPlainText()
    window.grab().save(str(OUTPUT/'plan-preview-native.png'))
    # Reopen and inspect the saved version; independent visit identities must survive.
    builder=CrewPlanBuilder(page,saved,inline=True)
    reopened=builder.build();assert not reopened['issues']
    assert plan_assignments(reopened)==assignments
    assert page.service.berth_versions()[0]==frozen
    report['saved_reopen_keeps_legs_and_visits']=True
    # The transfer vessel may be a configured name outside Fleet; the form still offers it.
    page.service.set_setting('transfer_vessel_name','Plan Boat Outside Fleet')
    form=PassengerForm(page.service,page.source,'2026-10-11',parent=page)
    form.name.setText('Virtual Fictional');form.position.setText('OBS')
    form.from_location.setCurrentIndex(form.from_location.findText('Plan Boat Outside Fleet'))
    form.to_location.setCurrentIndex(form.to_location.findData(vessels['HB6']))
    form.validate();assert form.result()==QDialog.DialogCode.Accepted
    report['configured_virtual_source_form']=True;form.deleteLater()
    page.service.set_setting('transfer_vessel_name','Niger')
    assert (data/'cargo-track.sqlite3').read_bytes()==before
    report.update(cargo_database_bytes_unchanged=True,exported_workbook=str(workbook))
    (OUTPUT/'native-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUTPUT/'plan-fixture.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    if builder:builder.deleteLater()
    if window.personnel_page:
        window.personnel_page.view_state.dirty=False
    window.close();app.processEvents()

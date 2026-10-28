"""Windows Qt acceptance on isolated fictional workbooks and databases."""
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import copy
import json
import os
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'output/text-case-1.2.4';OUT.mkdir(parents=True,exist_ok=True)
data=OUT/('fixture-'+str(time.time_ns()));data.mkdir()
os.environ['CARGO_TRACK_DATA_DIR']=str(data);os.environ['QT_QPA_PLATFORM']='windows'
from openpyxl import Workbook, load_workbook
from PySide6.QtCore import QSettings, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from cargo_track.appearance import configure_application
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_import import read_personnel_excel
from cargo_track.personnel_service import PersonnelService, clean_payload
from cargo_track.personnel_ui import PassengerForm, ImportDialog, CrewPlanBuilder
from cargo_track.text_case_ui import CasePreviewDialog
from cargo_track.ui import TransferForm, CorrectionDialog
from cargo_track.workspace import WorkspaceWindow
from cargo_track.berth_plan import generate_plan, export_plan

cargo=ApplicationService(data/'cargo-track.sqlite3');cargo.open()
def command(name,payload):return cargo.handle(Command(str(uuid4()),name,payload)).result
ship=command('create_vessel',{'name':'CHA'})['id']
command('create_voyage',{'name':'Fictional casing validation'})
command('add_stop',{'vessel_id':ship})
shore=cargo.workspace_snapshot()['shore_location_id']
item=command('create_transfer',{'description':'SAFETY HELMET','from_location_id':shore,'to_location_id':ship})
cargo.db.execute('UPDATE transfer_legs SET description=? WHERE no=?',('SAFETY HELMET',item['no']))
cargo.db.execute('UPDATE cargo SET default_description=? WHERE id=?',('SAFETY HELMET',item['cargo_id']))
cargo.close()
source=read_cargo(data/'cargo-track.sqlite3')
service=PersonnelService(data/'personnel-transfer.sqlite3');roster=service.create_plan('Fictional rotation','2026-10-26')
entry=service.add_passenger(roster,service.bind_record({'name':'ALEX MORGAN','position':'NAV QC',
    'date':'2026-10-26','from_name':'xx port','to_name':'CHA'},source))
raw=clean_payload(service.passenger(entry));raw.pop('text_case');raw.update(name='ALEX MORGAN',position='Nav Qc',
    original_values={'name':'ALEX MORGAN','position':'NAV QC'},batch_id='legacy-fixture')
service.db.execute('UPDATE passengers SET payload=? WHERE id=?',(json.dumps(raw),entry))
saved=service.save_berth(generate_plan(source,service.passengers(roster),[],'2026-10-26','xx port',mode='Final'))
historical=copy.deepcopy(saved);service.close()
book=Workbook();sheet=book.active;sheet.title='Crew'
sheet.append(['Name','Position','From','To','Date'])
sheet.append(["ANNE-MARIE O'NEILL",'hse OFFICER','xx port','CHA','2026-10-26'])
sheet.append(['MCDONALD J.','nav qc','xx port','CHA','2026-10-26'])
workbook=OUT/'fictional-crew.xlsx';book.save(workbook);book.close();original_workbook=workbook.read_bytes()
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Cargo Track 124 validation');QApplication.setApplicationName('Fictional casing checks')
app=QApplication([]);configure_application(app)
w=WorkspaceWindow(data/'cargo-track.sqlite3',data);errors=[]
def wait(predicate):
    until=time.monotonic()+20
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Native operation timed out: '+str(errors))
def settle():
    for _ in range(12):app.processEvents();time.sleep(.01)
report={'fictional_data':True,'data_directory':str(data),'platform':app.platformName(),'captures':[]}
try:
    w.show();wait(lambda:w.snapshot is not None and not w._refresh_wait)
    w.open_personnel();wait(lambda:w.personnel_page and w.personnel_page.source and not w.personnel_page._jobs)
    p=w.personnel_page;p.show_error=errors.append
    p.plan_combo.setCurrentIndex(p.plan_combo.findData(roster));settle()
    imported=ImportDialog(p,read_personnel_excel(workbook));imported.show();settle()
    assert imported.rows.item(0,2).text()=="Anne-Marie O'Neill"
    assert imported.rows.item(0,3).text()=='HSE Officer'
    assert "ANNE-MARIE O'NEILL" in imported.rows.item(0,2).toolTip()
    QTest.mouseClick(imported.preserve_case,Qt.MouseButton.LeftButton,pos=QPoint(10,imported.preserve_case.height()//2));settle()
    assert imported.rows.item(0,2).text()=="ANNE-MARIE O'NEILL"
    QTest.mouseClick(imported.preserve_case,Qt.MouseButton.LeftButton,pos=QPoint(10,imported.preserve_case.height()//2));settle()
    for theme in ('light','dark'):
        QSettings().setValue('appearance/theme',theme);configure_application(app);settle()
        imported.grab().save(str(OUT/f'import-{theme}.png'));report['captures'].append(f'import-{theme}.png')
    with patch('cargo_track.personnel_ui.confirm',return_value=True):
        QTest.mouseClick(imported.commit_button,Qt.MouseButton.LeftButton)
        wait(lambda:not p._write_pending)
    assert imported.result['plan_id']==roster
    imported.close();p.refresh_rows();settle()
    changes=p.service.text_case_preview(roster);assert len(changes)==2
    preview=CasePreviewDialog(changes,p);preview.show();settle()
    assert len(preview.selected())==2
    preview.rows.item(0,0).setCheckState(Qt.CheckState.Unchecked);assert len(preview.selected())==1
    preview.rows.item(0,0).setCheckState(Qt.CheckState.Checked)
    preview.grab().save(str(OUT/'bulk-dark.png'));report['captures'].append('bulk-dark.png')
    QTest.mouseClick(preview.buttons.button(QDialogButtonBox.StandardButton.Apply),Qt.MouseButton.LeftButton)
    assert preview.result()==QDialog.DialogCode.Accepted
    p.service.apply_text_case(roster,preview.selected());preview.close()
    assert p.service.passenger(entry)['position']=='NAV QC'
    form=PassengerForm(p.service,p.source,p.plan_date(),parent=p);form.show()
    form.name.setText('de la CRUZ');form.position.setText('hSe')
    form.from_location.setCurrentIndex(form.from_location.findData(shore));form.to_location.setCurrentIndex(form.to_location.findData(ship))
    assert 'HSE' in form.case_preview.text()
    QTest.mouseClick(form.preserve_case,Qt.MouseButton.LeftButton);settle()
    assert form.data()['name']=='de la CRUZ'
    manual=p.service.add_passenger(roster,form.data());form.close()
    assert next(r for r in p.service.crew_records(roster,p.source) if r['id']==manual)['position']=='hSe'
    cargo_form=TransferForm(vessels=w.snapshot['locations'],cargo_choices=[],parent=w);cargo_form.show()
    cargo_form.description.setPlainText('gps aNTENNA DN50 12V 2 mA\nPVC pIPE')
    cargo_form._select(cargo_form.from_location,shore);cargo_form._select(cargo_form.to_location,ship)
    assert 'GPS Antenna DN50 12V 2 mA\nPVC Pipe' in cargo_form.case_preview.toPlainText()
    for theme in ('light','dark'):
        QSettings().setValue('appearance/theme',theme);configure_application(app);settle()
        cargo_form.grab().save(str(OUT/f'cargo-form-{theme}.png'));report['captures'].append(f'cargo-form-{theme}.png')
    w._submit('create_transfer',cargo_form.payload(),'Fictional cargo saved')
    wait(lambda:not w._busy and not w._refresh_wait);cargo_form.close()
    cargo=ApplicationService(data/'cargo-track.sqlite3');cargo.open()
    changes=cargo.text_case_preview();assert len(changes)==2
    preview=CasePreviewDialog(changes,w);preview.show();settle()
    QSettings().setValue('appearance/theme','light');configure_application(app);settle()
    preview.grab().save(str(OUT/'bulk-light.png'));report['captures'].append('bulk-light.png')
    selected=preview.selected();preview.close()
    cargo.handle(Command(str(uuid4()),'normalize_text_case',{'changes':selected}))
    cargo.export_to(OUT/'normalized-cargo.xlsx','all',{'range':'all'},'xlsx',True);cargo.close()
    assert p.service.berth_versions()[0]==historical
    p.source=read_cargo(data/'cargo-track.sqlite3')
    builder=CrewPlanBuilder(p)
    try:plan=builder.build();assert not plan['issues'],plan['issues']
    finally:builder.deleteLater()
    plan=p.service.save_berth(plan,True);export_plan(plan,OUT/'normalized-plan.xlsx')
    backup=data/'case-backup.sqlite3';p.service.backup(backup);PersonnelService.validate_file(backup)
    assert original_workbook==workbook.read_bytes()
    assert not errors,errors
    report.update(result='PASS',import_toggle=True,source_tooltips=True,native_import_commit=True,
        selective_bulk_apply=True,manual_preserve=True,cargo_save=True,saved_history_unchanged=True,
        regenerated_plan=True,excel_export=True,backup_validation=True,source_workbook_unchanged=True)
    (OUT/'native-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
finally:
    if w.personnel_page:w.personnel_page.view_state.dirty=False
    w.close();app.processEvents()

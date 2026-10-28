"""Exercise the approved native workspaces against fictional, isolated data."""
from pathlib import Path
import copy,json,os,sys,time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
os.environ.pop('QT_QPA_PLATFORM',None)
OUTPUT=ROOT/'output/approved-ui-20261011';OUTPUT.mkdir(parents=True,exist_ok=True)
data=OUTPUT/('fixture-'+str(time.time_ns()));data.mkdir()
os.environ['CARGO_TRACK_DATA_DIR']=str(data)
from PySide6.QtCore import Qt,QSettings
from PySide6.QtWidgets import QApplication,QMessageBox,QDialog
from PySide6.QtTest import QTest
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_ui import CrewPlanBuilder
from cargo_track.berth_plan import plan_assignments,export_plan
from cargo_track.appearance import configure_application
from cargo_track.workspace import WorkspaceWindow

cargo=ApplicationService(data/'cargo-track.sqlite3');cargo.open();seq=0
def command(name,values):
    global seq
    seq+=1;return cargo.handle(Command(str(seq),name,values)).result
vessels={name:command('create_vessel',{'name':name})['id'] for name in ('BGP Victor','HB6','BGP Innovator','DFKT2','BGP Spirit','Niger')}
command('create_voyage',{'name':'20261011 Niger transfer plan'})
visits=[command('add_stop',{'vessel_id':vessels[name]})['stop_id'] for name in ('BGP Victor','HB6','BGP Innovator','DFKT2','HB6','BGP Victor','BGP Innovator','BGP Spirit')]
command('choose_stop',{'stop_id':visits[1]})
for description,source,target in (('Hard Disk','BGP Victor','BGP Innovator'),('GPS cable','HB6','DFKT2'),('QNAP','BGP Innovator','BGP Victor')):
    command('create_transfer',{'description':description,'from_location_id':vessels[source],'to_location_id':vessels[target],'physical_id':'','comment':''})
cargo.close()
service=PersonnelService(data/'personnel-transfer.sqlite3');service.set_setting('transfer_vessel_name','Niger')
crew=service.create_plan('Fictional crew — October 11','2026-10-11')
def person(name,source,target):return service.bind_record({'name':name,'position':'OBS','date':'2026-10-11','direction':'Transfer','from_name':source,'to_name':target},read_cargo(data/'cargo-track.sqlite3'))
first=service.add_passenger(crew,person('Alex Fictional','Niger','HB6'))
second=service.add_next_leg(first,person('Alex Fictional','HB6','BGP Victor'),read_cargo(data/'cargo-track.sqlite3'),0)
service.add_passenger(crew,person('Sam Fictional','Niger','BGP Innovator'))
service.add_passenger(crew,person('Taylor Fictional','BGP Victor','BGP Innovator'));service.close()
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Approved UI validation');QApplication.setApplicationName('Approved UI validation')
app=QApplication([]);assert app.platformName()=='windows'
QSettings().setValue('appearance/theme','dark');QSettings().setValue('appearance/font_size',12);configure_application(app)
window=WorkspaceWindow(data/'cargo-track.sqlite3',data)
def wait(predicate):
    until=time.monotonic()+15
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Native UI operation timed out')
def settle():
    for _ in range(12):app.processEvents();time.sleep(.01)
report={'fictional_data':True,'native_visible':True,'data_directory':str(data),'scenarios':[]}
try:
    window.show();wait(lambda:window.snapshot is not None and not window._refresh_wait and window.model.rowCount()==3)
    window.table.selectRow(1);settle()
    assert window.pickup_button.isEnabled() and not window.deliver_button.isEnabled()
    assert window.pickup_button.objectName()=='primaryButton' and window.add_button.objectName()!='primaryButton'
    help_menu=window.help_menu
    with patch.object(window,'open_help') as help_callback:
        for action in help_menu.actions():action.trigger()
        assert all(isinstance(call.args[0],str) for call in help_callback.call_args_list)
        assert len(help_callback.call_args_list)==8
    report['help_menu_routes_to_named_sections']=True
    window.open_personnel();wait(lambda:window.personnel_page is not None and window.personnel_page.source and not window.personnel_page._jobs)
    page=window.personnel_page;page.plan_combo.setCurrentIndex(page.plan_combo.findData(crew))
    builder=CrewPlanBuilder(page)
    draft=builder.build();builder.deleteLater();assert not draft['issues'],draft['issues']
    page.draft=draft;page.show_plan(draft);editor=page.live_builder
    assert all(t['kind']=='Passengers' for t in editor.tasks)
    assert plan_assignments(editor.build())['Passengers:'+second]=={'pick':visits[4],'drop':visits[5]}
    assert editor.endpoint_controls[1][0].currentText().startswith('05')
    editor.route.setCurrentRow(1);settle()
    assert 'Alex Fictional' in page.stop_preview.toPlainText() and 'material' not in page.stop_preview.toPlainText().lower()
    page.stop_comment.setPlainText('Fictional stop comment');page.refresh_live_preview()
    assert page.draft['stops'][1]['comment']=='Fictional stop comment'
    page.stop_comment.clear();page.refresh_live_preview()
    report.update(separate_pickup_drop_columns=True,later_visit_assignment_preserved=True,stop_comments_in_draft=True,personnel_only_visible=True)
    for theme in ('dark','light'):
        for width,height in ((1672,940),(1366,768),(1000,700)):
            QSettings().setValue('appearance/theme',theme);configure_application(app);window._set_snapshot(window.snapshot)
            window.resize(width,height);settle()
            page.view_state.dirty=False;window.show_cargo();page.view_state.dirty=True
            assert window.pages.currentWidget() is window.cargo_page
            window.statusBar().clearMessage();window.table.selectRow(1);settle()
            window.cargo_page.grab().save(str(OUTPUT/f'cargo-{theme}-{width}.png'))
            assert all(window.route_content.rect().contains(window.route_items.itemAt(i).widget().geometry()) for i in range(8)),(width,window.route_content.rect(),[window.route_items.itemAt(i).widget().geometry() for i in range(8)])
            window.open_personnel();wait(lambda:not page._jobs);settle();editor.route.setCurrentRow(1);page.render_stop_preview()
            window.personnel_page.grab().save(str(OUTPUT/f'personnel-{theme}-{width}.png'))
            report['scenarios'].append({'theme':theme,'width':width,'height':height,'cargo_route_visible':True,'personnel_rows':editor.rows.rowCount(),'personnel_row_height':editor.rows.verticalHeader().defaultSectionSize()})
    # Explicit endpoint choices retain identities and survive save/reopen.
    control=editor.endpoint_controls[1][1];index=next(i for i,(_,value) in enumerate(control.options) if value==visits[5]);control.setCurrentIndex(index)
    editor.rows.item(0,2).setText('Alex Edited');editor.undo_cell();assert editor.rows.item(0,2).text()=='Alex Fictional'
    page.stop_comment.setPlainText('Persisted stop note');page.save_version(True);wait(lambda:not page._write_pending)
    saved=copy.deepcopy(page.saved_plan);assert not page.view_state.dirty and 'Unsaved' not in page.plan_notice.text()
    assert saved['stops'][1]['comment']=='Persisted stop note'
    export_plan(saved,OUTPUT/'approved-plan.xlsx')
    from openpyxl import load_workbook
    workbook=load_workbook(OUTPUT/'approved-plan.xlsx');assert any(cell.value=='Persisted stop note' for row in workbook['Berthing Plan'] for cell in row)
    assert any('material' in str(cell.value).lower() for row in workbook['Berthing Plan'] for cell in row)
    workbook.close();page.copy_complete();assert page.live_builder.stop_comments[visits[1]]=='Persisted stop note'
    assert page.service.berth_versions()[0]==saved
    report.update(saved_notice_consistent=True,comments_survive_save_edit_export=True,excel_four_group_contract_preserved=True)
    for i in range(8,24):
        name=('BGP Victor','HB6','BGP Innovator','DFKT2','BGP Spirit')[i%5]
        page.live_builder.append_stop({'id':'plan:stress-'+str(i),'vessel_id':vessels[name],'vessel_name_snapshot':name})
    QSettings().setValue('appearance/theme','dark');configure_application(app)
    page.live_builder.refresh_assignments();page.refresh_live_preview();window.resize(1000,700);settle()
    route=page.live_builder.route;route.reflow();settle()
    assert all(route.viewport().rect().contains(route.visualItemRect(route.item(i))) for i in range(24)),[route.visualItemRect(route.item(i)) for i in range(24)]
    assert plan_assignments(page.live_builder.build())['Passengers:'+second]=={'pick':visits[4],'drop':visits[5]}
    page.grab().save(str(OUTPUT/'personnel-24-stops-1000.png'))
    report['personnel_24_visits_visible_without_scrolling']=True
    page.view_state.dirty=False;window.show_cargo()
    # Current-stop click is a reversible selection; it does not change transfers.
    QTest.mouseClick(window.route_items.itemAt(1).widget(),Qt.MouseButton.LeftButton);wait(lambda:window.snapshot['current_stop_id'] is None and not window._busy)
    QTest.mouseClick(window.route_items.itemAt(1).widget(),Qt.MouseButton.LeftButton);wait(lambda:window.snapshot['current_stop_id']==visits[1] and not window._busy and not window._refresh_wait)
    window.table.selectRow(1);QTest.mouseClick(window.pickup_button,Qt.MouseButton.LeftButton);wait(lambda:not window._busy and not window._refresh_wait and window.model.rows[1]['status']=='On Board')
    window.status_filter.setCurrentIndex(window.status_filter.findData('completed|Done'));wait(lambda:window.model.rowCount()==0)
    assert window.filters['all']['range']=='completed' and window.filters['all']['status']=='Done'
    window.clear_filters();wait(lambda:window.model.rowCount()==3)
    window.tabs.setCurrentIndex(1);wait(lambda:window.view=='current_stop')
    assert not window.status_filter.model().item(3).isEnabled()
    window.status_filter.setCurrentIndex(3)
    assert window.status_filter.currentData()=='open|' and window.filters['current_stop']['range']=='open'
    window.tabs.setCurrentIndex(2);window.clear_filters()
    assert window.status_filter.currentData()=='open|On Board' and not window.status_filter.isEnabled()
    window.tabs.setCurrentIndex(0)
    window.clear_filters();wait(lambda:window.model.rowCount()==3)
    with patch('cargo_track.ui.TransferForm') as form:
        form.return_value.exec.return_value=QDialog.DialogCode.Accepted
        form.return_value.payload.return_value={'description':'Added through cargo form','from_location_id':vessels['HB6'],'to_location_id':vessels['DFKT2'],'physical_id':'','comment':''}
        window.add_transfer();wait(lambda:window.model.rowCount()==4 and window.selected_no==4 and not window._refresh_wait and not window._busy)
    assert window._selected_row()['description']=='Added through cargo form'
    report['cargo_creation_receipt_selects_new_record']=True
    report.update(single_status_filter_consistent=True,current_selection_toggle=True,pickup_command_works=True)
    (OUTPUT/'native-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    if window.personnel_page:window.personnel_page.view_state.dirty=False
    window.close();app.processEvents()

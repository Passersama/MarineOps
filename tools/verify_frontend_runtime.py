"""Visible native keyboard, demand-editor and unsaved-close checks on fictional copies."""
from pathlib import Path
import os,sys,json,time,copy,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
output=ROOT/'output/frontend-update-20261007/keyboard-native';data=output/str(time.time_ns());data.mkdir(parents=True)
fixture=json.loads((ROOT/'output/frontend-update-20261007/ui-final/native-visible.json').read_text(encoding='utf-8'))
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):shutil.copy2(Path(fixture['data_directory'])/name,data/name)
os.environ['CARGO_TRACK_DATA_DIR']=str(data)
from PySide6.QtCore import Qt,QSettings,QTimer
from PySide6.QtWidgets import QApplication,QLineEdit,QComboBox,QMessageBox
from PySide6.QtTest import QTest
from cargo_track.appearance import configure_application
from cargo_track.workspace import WorkspaceWindow
from cargo_track.personnel_service import PersonnelService
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Cargo frontend keyboard validation');QApplication.setApplicationName('Cargo frontend keyboard validation')
app=QApplication([]);configure_application(app)
def wait(predicate):
    until=time.monotonic()+15
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Native frontend did not complete')
window=WorkspaceWindow(data/'cargo-track.sqlite3',data)
report={'native_visible':True,'data_directory':str(data),'scope':'QTest keyboard and real modal buttons in the native Qt window; no Narrator speech or physical DPI certification'}
try:
    window.show();wait(lambda:window.snapshot is not None and not window._busy and not window._refresh_wait)
    window.open_personnel();page=window.personnel_page;wait(lambda:page.source is not None and not page._jobs)
    plan=next(p for p in page.service.berth_versions() if p['mode']=='Final' and p['status']=='Published')
    page.plan_combo.setCurrentIndex(page.plan_combo.findData(plan['personnel_plan_id']))
    plan=copy.deepcopy(plan);plan.pop('id',None);page.draft=plan;page.saved_plan=None;page.show_plan(plan);app.processEvents()
    builder=page.live_builder;name=builder.tasks[0]['name'];builder.rows.setCurrentCell(0,2);builder.rows.setFocus()
    QTest.keyClick(builder.rows,Qt.Key.Key_F2);app.processEvents()
    editor=next(w for w in builder.rows.findChildren(QLineEdit) if w.isVisible())
    QTest.keyClick(editor,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);QTest.keyClicks(editor,'Keyboard Fictional');QTest.keyClick(editor,Qt.Key.Key_Return);app.processEvents()
    assert builder.tasks[0]['name']=='Keyboard Fictional'
    QTest.keyClick(builder.rows,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);app.processEvents();assert builder.tasks[0]['name']==name
    QTest.keyClick(builder.rows,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);app.processEvents();assert builder.tasks[0]['name']=='Keyboard Fictional'
    report['keyboard_edit_undo_redo']=True
    builder.rows.setCurrentCell(0,4);before=copy.deepcopy(builder.assignments[0].currentData())
    QTest.keyClick(builder.rows,Qt.Key.Key_F2);app.processEvents()
    choice=next(w for w in builder.rows.findChildren(QComboBox) if w.isVisible());assert choice.count()>1 and choice.accessibleName()
    QTest.keyClick(choice,Qt.Key.Key_Down);QTest.keyClick(choice,Qt.Key.Key_Return);app.processEvents()
    assert builder.assignments[0].currentData()!=before;report['keyboard_assignment_demand_editor']=True
    builder.rows.setCurrentCell(0,0);QTest.keyClick(builder.rows,Qt.Key.Key_Space);app.processEvents();assert not builder.includes[0].isChecked()
    QTest.keyClick(builder.rows,Qt.Key.Key_Space);app.processEvents();assert builder.includes[0].isChecked();report['keyboard_native_checkbox']=True
    window.grab().save(str(output/'keyboard-edited.png'))
    def choose(label):
        box=QApplication.activeModalWidget();assert isinstance(box,QMessageBox)
        box.grab().save(str(output/(label.replace(' ','-')+'-close.png')))
        next(b for b in box.buttons() if b.text().replace('&','')==label).click()
    QTimer.singleShot(30,lambda:choose('Cancel'));window.close();assert window.isVisible() and page.view_state.dirty
    report['close_cancel_keeps_editor']=True
    QTimer.singleShot(30,lambda:choose('Save draft'));window.close();wait(lambda:not window.isVisible())
    service=PersonnelService(data/'personnel-transfer.sqlite3')
    try:
        saved=service.berth_versions()[0];assert saved['status']=='Draft' and 'Keyboard Fictional' in str(saved)
    finally:service.close()
    report['close_save_persists_draft']=True
    (output/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
finally:
    if window.personnel_page is not None:window.personnel_page.view_state.dirty=False
    window.close();app.processEvents()

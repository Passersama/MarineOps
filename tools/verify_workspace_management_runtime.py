"""Native Windows checks for shared navigation and workspace management."""
from pathlib import Path
import copy
import json
import os
import shutil
import sqlite3
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));os.environ.pop('QT_QPA_PLATFORM',None)
OUTPUT=ROOT/'output/workspace-audit-20261011';OUTPUT.mkdir(parents=True,exist_ok=True)
fixture=json.loads((ROOT/'output/personnel-routes-20261011/native-checks.json').read_text(encoding='utf-8'))
assert fixture['fictional_data']
data=OUTPUT/('native-'+str(time.time_ns()));data.mkdir()
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):shutil.copy2(Path(fixture['data_directory'])/name,data/name)
os.environ['CARGO_TRACK_DATA_DIR']=str(data)
from PySide6.QtCore import Qt,QSettings
from PySide6.QtWidgets import QApplication,QMessageBox,QPushButton
from PySide6.QtTest import QTest
from cargo_track.appearance import configure_application
from cargo_track.workspace import WorkspaceWindow
from cargo_track.personnel_ui import CrewPlanBuilder

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Workspace validation');QApplication.setApplicationName('Workspace validation')
app=QApplication([]);configure_application(app);assert app.platformName()=='windows'
window=WorkspaceWindow(data/'cargo-track.sqlite3',data)

def wait(predicate):
    until=time.monotonic()+15
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Native workspace operation timed out')

def settle():
    for _ in range(15):app.processEvents();time.sleep(.01)

def business_rows():
    with sqlite3.connect(data/'cargo-track.sqlite3') as conn:
        return {table:list(conn.execute('SELECT * FROM '+table+' ORDER BY rowid')) for table in ('cargo','transfer_legs','voyage_stops')}

report={'native_visible':True,'fictional_data':True,'data_directory':str(data),'scenarios':[]}
try:
    window.show();wait(lambda:window.snapshot is not None and not window._refresh_wait)
    original=business_rows();stop=window.snapshot['stops'][0]['id']
    for expected in (stop,None,stop):
        QTest.mouseClick(window.route_items.itemAt(0).widget(),Qt.MouseButton.LeftButton)
        wait(lambda:window.snapshot['current_stop_id']==expected and not window._busy)
    report['current_stop_select_clear_reselect']=True
    QTest.mouseClick(window.personnel_button,Qt.MouseButton.LeftButton)
    wait(lambda:window.personnel_page is not None and window.personnel_page.source is not None and not window.personnel_page._jobs)
    page=window.personnel_page
    identifier=page.plan_combo.currentData();saved=page.service.berth_versions()[0]
    frozen=copy.deepcopy(saved);crew=page.service.passengers(identifier)
    with patch('cargo_track.personnel_ui.QInputDialog.getText',return_value=('Renamed Fictional Crew',True)):
        QTest.mouseClick(page.rename_list_button,Qt.MouseButton.LeftButton)
    wait(lambda:not page._write_pending and page.plan_combo.currentText()=='Renamed Fictional Crew')
    assert page.plan_combo.currentData()==identifier and page.service.passengers(identifier)==crew
    assert page.service.berth_versions()[0]==frozen
    report['rename_preserves_identity_crew_and_snapshot']=True
    page.saved_plan=saved;page.draft=None;page.show_plan(saved)
    # Build and edit a draft, then exercise navigation cancellation and discard.
    page.copy_complete();page.live_builder.rows.item(0,2).setText('Unsaved Fictional Name')
    def choose(label):
        return lambda box:next(b for b in box.buttons() if b.text().replace('&','')==label)
    with patch.object(QMessageBox,'exec',return_value=0),patch.object(QMessageBox,'clickedButton',choose('Cancel')):
        QTest.mouseClick(page.navigation.cargo_button,Qt.MouseButton.LeftButton)
    assert window.pages.currentWidget() is page and page.view_state.dirty
    assert page.navigation.personnel_button.isChecked()
    with patch.object(QMessageBox,'exec',return_value=0),patch.object(QMessageBox,'clickedButton',choose('Discard')):
        QTest.mouseClick(page.navigation.cargo_button,Qt.MouseButton.LeftButton)
    assert window.pages.currentWidget() is window.cargo_page and page.live_builder is None
    report['navigation_cancel_and_discard']=True
    for theme in ('light','dark'):
        for font in (11,12):
            QSettings().setValue('appearance/theme',theme);QSettings().setValue('appearance/font_size',font);configure_application(app)
            window._set_snapshot(window.snapshot)
            for width,height in ((1000,700),(1366,768)):
                window.resize(width,height);settle()
                views=[]
                for name in ('cargo','personnel'):
                    if name=='cargo':window.show_cargo()
                    else:window.open_personnel();wait(lambda:not page._jobs)
                    settle();nav=window.navigation if name=='cargo' else page.navigation
                    active=nav.cargo_button if name=='cargo' else nav.personnel_button
                    assert active.isChecked()
                    page_widget=window.cargo_page if name=='cargo' else page
                    nav_bounds=nav.geometry();assert page_widget.rect().contains(nav.mapTo(page_widget,nav.rect().bottomRight()))
                    assert nav.brand.size().width()==36 and nav.brand.size().height()==36
                    views.append({'workspace':name,'brand_size':[nav.brand.width(),nav.brand.height()],
                                  'cargo_button_size':[nav.cargo_button.width(),nav.cargo_button.height()],
                                  'personnel_button_size':[nav.personnel_button.width(),nav.personnel_button.height()]})
                    window.grab().save(str(OUTPUT/f'{name}-{theme}-{font}-{width}.png'))
                assert views[0]['brand_size']==views[1]['brand_size']
                assert views[0]['cargo_button_size']==views[1]['cargo_button_size']
                assert views[0]['personnel_button_size']==views[1]['personnel_button_size']
                report['scenarios'].append({'theme':theme,'font':font,'requested_window':[width,height],
                                          'actual_window':[window.width(),window.height()],'views':views,'navigation_consistent':True})
    page.saved_plan=saved;page.draft=None;page.show_plan(saved);page.refresh_versions(saved['id']);page.history_row.show();settle()
    window.grab().save(str(OUTPUT/'version-history-before-clear.png'))
    with patch('cargo_track.personnel_ui.confirm',return_value=True):QTest.mouseClick(page.clear_history_button,Qt.MouseButton.LeftButton)
    wait(lambda:not page._write_pending and page.versions.count()==0)
    assert page.service.berth_versions(True)==[frozen] and page.service.passengers(identifier)==crew
    report['history_clear_keeps_snapshot_and_crew']=True
    assert original==business_rows();report['cargo_transfers_and_route_rows_unchanged']=True
    report['shared_navigation']=True
    (OUTPUT/'native-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    if window.personnel_page:window.personnel_page.view_state.dirty=False
    window.close();app.processEvents()

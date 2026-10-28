"""Native saved-plan/Cargo-progress reproduction, using fictional data only."""
from pathlib import Path
import hashlib
import json
import os
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
os.environ['TMP']=str(ROOT/'.tmp-build');os.environ['TEMP']=os.environ['TMP']
OUT=ROOT/'output/dashboard-fix-1.2.6';OUT.mkdir(exist_ok=True)
from test_dashboard_cargo_independence import DashboardCargoIndependenceTests
from cargo_track.dashboard_data import read_dashboard
from cargo_track.personnel_cargo import source_matches
from cargo_track.appearance import configure_application
from cargo_track.workspace import WorkspaceWindow
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication,QPushButton
from cargo_track.about_ui import AboutDialog

os.environ.pop('QT_QPA_PLATFORM',None)
app=QApplication([]);app.setOrganizationName('MarineOps validation');app.setApplicationName('Dashboard fix')
fixture=DashboardCargoIndependenceTests();fixture.setUp();f=fixture.f
os.environ['CARGO_TRACK_DATA_DIR']=str(f.root)
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(f.root/'preferences'))
configure_application(app)
def wait(predicate,seconds=20):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.015)
    raise AssertionError('Timed out waiting for native Dashboard')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

window=None
try:
    saved=fixture.save(legacy=True);fixture.pickup()
    row=f.personnel.passenger(f.ids[0])
    with patch.object(f.personnel,'_sync_crew_plans'):
        f.personnel.edit_crew_entry(row['id'],{**row,'position':'Updated role'},row['version'])
    with patch('cargo_track.dashboard_data.crew_source_matches',source_matches):
        assert f.read()['personnel']['status']=='stale','Original blank state was not reproduced'
    before={p.name:sha(p) for p in (f.cargo.path,f.personnel.path)}
    window=WorkspaceWindow(f.cargo.path,f.root);window.setWindowTitle('MarineOps');window.show()
    wait(lambda:window.snapshot is not None and not window._busy)
    window.show_dashboard();dashboard=window.dashboard_page
    wait(lambda:dashboard.data is not None and not dashboard._jobs and not dashboard.refresh_timer.isActive())
    assert dashboard.data['personnel']['status']=='ready',dashboard.data['personnel']['message']
    assert (dashboard.boarding.text(),dashboard.leaving.text())==('3','2')
    assert dashboard.crew_model.rowCount()==5
    assert any(r['position']=='Updated Role' for r in dashboard.crew_model.rows)
    checked_about=[]
    def close_about():
        dialog=app.activeModalWidget()
        if isinstance(dialog,AboutDialog):checked_about.append(dialog.windowTitle());dialog.accept()
    QTimer.singleShot(100,close_about);dashboard.navigation.about_button.click()
    assert checked_about==['About MarineOps']
    captures=[];layout_issues=[]
    for theme in ('light','dark'):
        dashboard.choose_theme(theme)
        for width,height in ((1366,1000),(1000,800)):
            window.resize(width,height)
            wait(lambda:not dashboard._jobs and not dashboard.refresh_timer.isActive())
            app.processEvents()
            about=dashboard.navigation.about_button
            settings=next(b for b in dashboard.findChildren(QPushButton) if b.text()=='Settings')
            assert about.mapTo(dashboard,about.rect().topLeft()).x()>settings.mapTo(dashboard,settings.rect().topLeft()).x()
            assert about.width()>=about.sizeHint().width()
            for control in (dashboard.navigation.title,dashboard.navigation.dashboard_button,dashboard.navigation.cargo_button,dashboard.navigation.personnel_button):
                if control.width()<control.sizeHint().width():
                    layout_issues.append((theme,width,control.text(),control.width(),control.sizeHint().width()))
            dashboard.scroll.ensureWidgetVisible(dashboard.crew_table,0,8);app.processEvents()
            name=f'dashboard-{theme}-{width}.png';window.grab().save(str(OUT/name));captures.append(name)
            assert (dashboard.boarding.text(),dashboard.leaving.text())==('3','2')
    # A real structural route change must still block; its explanation is now
    # above the counts/table rather than below an empty 210px roster.
    f.command('add_stop',{'vessel_id':f.vessels['HB6']})
    dashboard.refresh_from_source()
    wait(lambda:not window._busy and not dashboard._jobs and not dashboard.refresh_timer.isActive()
         and dashboard.data['personnel']['status']=='stale')
    assert not dashboard.crew_table.isVisible()
    assert dashboard.crew_notice.isVisible() and 'changed sources' in dashboard.crew_notice.text()
    assert dashboard.crew_notice.geometry().top()<dashboard.boarding.mapTo(dashboard.personnel_panel,dashboard.boarding.rect().topLeft()).y()
    dashboard.scroll.ensureWidgetVisible(dashboard.personnel_panel,0,8);app.processEvents()
    window.grab().save(str(OUT/'dashboard-route-review.png'))
    assert sha(f.personnel.path)==before[f.personnel.path.name]
    assert not layout_issues,layout_issues
    report={'result':'PASS','platform':app.platformName(),'fictional_data_only':True,
        'original_blank_reproduced':True,'legacy_plan_after_cargo_pickup':True,'current_roster_refreshed':True,
        'boarding':3,'leaving':2,'roster_rows':5,'dashboard_about_right_of_settings':True,'about_dialog_opened':True,
        'real_route_change_still_blocked':True,'review_message_above_counts':True,
        'personnel_database_unchanged':True,'captures':captures+['dashboard-route-review.png']}
    (OUT/'native-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
finally:
    if window is not None:window.close();app.processEvents()
    fixture.tearDown()

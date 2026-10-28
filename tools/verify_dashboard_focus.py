"""Validate keyboard containment in the native full-roster drawer."""
from pathlib import Path
import json,os,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'output/dashboard-release-20261012'
data=ROOT/'artifacts/validation-1.2.1'/('keyboard-fixture-'+str(time.time_ns()))
import subprocess
subprocess.run([sys.executable,str(ROOT/'tools/prepare_dashboard_release_fixture.py'),str(data)],check=True,capture_output=True)
os.environ['CARGO_TRACK_DATA_DIR']=str(data);os.environ.pop('QT_QPA_PLATFORM',None)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings,Qt
from PySide6.QtTest import QTest
from cargo_track.workspace import WorkspaceWindow
from cargo_track.appearance import configure_application
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Isolated keyboard audit');QApplication.setApplicationName('Dashboard')
app=QApplication([]);configure_application(app);window=WorkspaceWindow(data/'cargo-track.sqlite3',data);window.show();page=window.dashboard_page
def wait(predicate):
    until=time.monotonic()+20
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Keyboard fixture timed out')
try:
    wait(lambda:page.data and not page._jobs and page.data['personnel']['status']=='ready')
    page.open_drawer();outside=[]
    for key in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):
        for i in range(20):
            QTest.keyClick(app.focusWidget(),key);app.processEvents()
            focus=app.focusWidget()
            if focus is not page.drawer and not page.drawer.isAncestorOf(focus):
                outside.append({'key':str(key),'widget':focus.metaObject().className(),'name':focus.objectName(),'text':focus.text() if hasattr(focus,'text') else ''})
    report={'native_platform':app.platformName(),'outside_drawer':outside,'result':'FAIL' if outside else 'PASS'}
    (OUT/('focus-before.json' if '--before' in sys.argv else 'focus-after.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));assert not outside,report
finally:window.close();app.processEvents()

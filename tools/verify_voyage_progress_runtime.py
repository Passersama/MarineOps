"""Native acceptance for voyage counts, plan progress and Qt drag/drop events."""
from pathlib import Path
import json,os,sys,time
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'output/voyage-progress-20261012';OUT.mkdir(parents=True,exist_ok=True)
data=OUT/('fixture-'+str(time.time_ns()));data.mkdir();os.environ['CARGO_TRACK_DATA_DIR']=str(data)
os.environ.pop('QT_QPA_PLATFORM',None)
from PySide6.QtCore import QPoint,QPointF,Qt,QSettings,QMimeData,QEvent,QTimer
from PySide6.QtGui import QDrag,QDragEnterEvent,QDragMoveEvent,QDropEvent,QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from cargo_track.appearance import configure_application
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.berth_plan import generate_plan
from cargo_track.workspace import WorkspaceWindow

cargo=ApplicationService(data/'cargo-track.sqlite3');cargo.open()
def command(name,payload):return cargo.handle(Command(str(uuid4()),name,payload)).result
def material(name):return command('create_transfer',{'description':name,'from_location_id':fleet['BGP Victor'],'to_location_id':fleet['BGP Spirit']})['no']
with patch('cargo_track.service.now_utc',return_value='2026-10-01T00:00:00.000000Z'):
    fleet={name:command('create_vessel',{'name':name})['id'] for name in ('BGP Victor','HB6','BGP Spirit','Niger')}
    command('create_voyage',{'name':'Previous voyage'})
    old=material('Historical completed cargo');command('pick_up',{'no':old,'expected_version':0,'confirmed_location':True});command('deliver',{'no':old,'expected_version':1,'confirmed_location':True})
    backlog=material('Departure backlog');waiting=material('Still waiting')
    onboard=material('Already aboard at departure');command('pick_up',{'no':onboard,'expected_version':0,'confirmed_location':True})
with patch('cargo_track.service.now_utc',return_value='2026-10-12T00:00:00.000000Z'):
    command('create_voyage',{'name':'20261012 Niger route'})
    visits=[command('add_stop',{'vessel_id':fleet[name]})['stop_id'] for name in ('BGP Victor','HB6','BGP Victor','HB6','BGP Spirit')]
    command('set_setting',{'key':'transfer_vessel_name','value':'Niger'})
    new=material('New voyage cargo');command('pick_up',{'no':backlog,'expected_version':0,'confirmed_location':True});command('deliver',{'no':backlog,'expected_version':1,'confirmed_location':True})
    command('choose_stop',{'stop_id':visits[1]})
cargo.close()
service=PersonnelService(data/'personnel-transfer.sqlite3');service.set_setting('transfer_vessel_name','Niger')
roster=service.create_plan('Fictional voyage roster','2026-10-12');source=read_cargo(data/'cargo-track.sqlite3')
def person(name,from_name,to_name):return service.bind_record({'name':name,'position':'Engineer','direction':'Transfer','date':'2026-10-12','from_name':from_name,'to_name':to_name},source)
first=service.add_passenger(roster,person('Alex Fictional','Niger','BGP Victor'))
service.add_next_leg(first,person('Alex Fictional','BGP Victor','HB6'),source,0)
service.add_passenger(roster,person('Sam Fictional','BGP Victor','BGP Spirit'))
service.add_passenger(roster,person('Taylor Fictional','Niger','HB6'))
source=service.planning_source(source)
plan=generate_plan(source,service.crew_records(roster,source),[],'2026-10-12',service.port_name(source),mode='Final',personnel_plan_id=roster)
assert not plan['issues'],plan['issues']
plan.update(personnel_context=service.context(roster),personnel_source_path=str(service.path));service.save_berth(plan,True);service.close()
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
app=QApplication([]);QApplication.setOrganizationName('Voyage progress validation');QApplication.setApplicationName('Isolated validation')
QSettings().setValue('appearance/theme','dark');QSettings().setValue('appearance/font_size',11);configure_application(app)
w=WorkspaceWindow(data/'cargo-track.sqlite3',data);p=w.dashboard_page
def wait(predicate,timeout=20):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Native operation timed out')
def settle():
    for _ in range(12):app.processEvents();time.sleep(.01)
def choose(identifier):
    w._submit('choose_stop',{'stop_id':identifier},'Validation visit')
    wait(lambda:not w._busy and not w._refresh_wait and not p._jobs and not p.refresh_timer.isActive() and p.data['cargo']['current_stop_id']==identifier)
report={'fictional_data':True,'data_directory':str(data),'platform':app.platformName(),'scenarios':[]}
try:
    w.show();wait(lambda:w.snapshot is not None and p.data and not p._jobs and not w._refresh_wait)
    assert p.data['cargo']['counts']=={'Waiting':2,'On Board':1,'Done':1}
    assert p.data['cargo']['total']==4 and w.snapshot['counts']['all']==5 and w.tabs.tabText(0)=='All transfers  3'
    assert p.personnel_donut.counts=={'Completed':1,'Pending':3}
    for font in (10,11,12):
        for theme in ('light','dark'):
            for width,height in ((1000,700),(1366,768)):
                QSettings().setValue('appearance/font_size',font);QSettings().setValue('appearance/theme',theme);configure_application(app);p.apply_theme();w.resize(width,height);settle()
                assert w.width()==width and p.scroll.horizontalScrollBar().maximum()==0
                for donut in (p.donut,p.personnel_donut):assert p.content.rect().contains(donut.mapTo(p.content,donut.rect().bottomRight()))
                p.grab().save(str(OUT/f'dashboard-{theme}-{font}-{width}.png'))
                report['scenarios'].append({'theme':theme,'font':font,'width':width,'counts':p.donut.counts,'progress':p.personnel_donut.counts})
    choose(visits[2]);assert p.personnel_donut.counts=={'Completed':2,'Pending':2}
    choose(visits[3]);assert p.personnel_donut.counts=={'Completed':2,'Pending':2}
    choose(visits[4]);assert p.personnel_donut.counts=={'Completed':3,'Pending':1}
    choose(visits[1]);assert p.personnel_donut.counts=={'Completed':1,'Pending':3}
    report['linked_legs_counted_separately_and_current_drop_pending']=True
    w.show_cargo();wait(lambda:not w._refresh_wait);w.resize(1366,768);settle();w.raise_();w.activateWindow();settle()
    first_button=w.route_items.itemAt(0).widget();last_button=w.route_items.itemAt(4).widget()
    stale=QMimeData();stale.setData(first_button.MIME,f'old-scope:{visits[0]}'.encode())
    event=QDragEnterEvent(QPoint(20,20),Qt.DropAction.MoveAction,stale,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    last_button.dragEnterEvent(event);assert not event.isAccepted();report['stale_drag_rejected']=True
    # Use deterministic Qt mouse/drop events, replacing the blocking OS drag
    # loop only. No input is sent to other applications or the desktop cursor.
    drag_started=[];drop_accepted=[]
    def execute_drag(drag,*args):
        drag_started.append(True)
        def finish_drop():
            point=QPoint(last_button.width()//2,last_button.height()-7);mime=drag.mimeData()
            enter=QDragEnterEvent(point,Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(last_button,enter)
            move=QDragMoveEvent(point,Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(last_button,move)
            drop=QDropEvent(QPointF(point),Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(last_button,drop);drop_accepted.append(drop.isAccepted());QDrag.cancel()
        finish_drop()
        return Qt.DropAction.MoveAction
    start=QPoint(first_button.width()//2,first_button.height()//2)
    QTest.mousePress(first_button,Qt.MouseButton.LeftButton,pos=start)
    moved=start+QPoint(0,QApplication.startDragDistance()+5)
    with patch.object(QDrag,'exec',execute_drag):
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(moved),QPointF(first_button.mapToGlobal(moved)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(first_button,event)
    assert drag_started and drop_accepted==[True],(drag_started,drop_accepted)
    QTest.mouseRelease(first_button,Qt.MouseButton.LeftButton,pos=start)
    desired=visits[1:]+visits[:1]
    wait(lambda:not w._busy and not w._refresh_wait and [s['id'] for s in w.snapshot['stops']]==desired)
    assert w.snapshot['current_stop_id']==visits[1]
    assert [s['id'] for s in read_cargo(data/'cargo-track.sqlite3')['stops']]==desired
    w.cargo_page.grab().save(str(OUT/'cargo-dragged.png'))
    report.update(qt_mouse_start_and_drop_events=True,os_drag_loop_replaced_in_test=True,physical_desktop_mouse_test=False,reorder_persisted=True,current_stop_identity_preserved=True,all_transfers_excludes_done=True,historical_done_excluded=True)
    w.show_dashboard();wait(lambda:not p._jobs and p.data['personnel']['status']=='stale');assert p.personnel_donut.available is False
    report['stale_plan_clears_personnel_progress']=True
    report['result']='PASS';(OUT/'native-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
finally:
    w.close();app.processEvents()

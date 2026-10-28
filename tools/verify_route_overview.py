"""Check all route stops remain visible and clickable on isolated native fixtures."""
from pathlib import Path
import os,sys,time,json,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
parser=argparse.ArgumentParser();parser.add_argument('--visible',action='store_true');parser.add_argument('--stops',type=int,default=13);args=parser.parse_args()
if args.visible:os.environ.pop('QT_QPA_PLATFORM',None)
else:os.environ['QT_QPA_PLATFORM']='offscreen'
output=ROOT/'output/route-overview-20261007';data=output/str(time.time_ns());data.mkdir(parents=True)
os.environ['CARGO_TRACK_DATA_DIR']=str(data)
from PySide6.QtCore import QSettings,Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from cargo_track.service import ApplicationService
from cargo_track.domain import Command
from cargo_track.appearance import configure_application
from cargo_track.workspace import WorkspaceWindow
service=ApplicationService(data/'cargo-track.sqlite3');service.open();seq=0
def command(name,payload):
    global seq;seq+=1;return service.handle(Command(str(seq),name,payload)).result
command('create_voyage',{'name':'20261006 Complete route'})
names=['BGP Spirit','BGP Challenger','BGP Guardian','BGP Innovator','Stanford Niger','BGP Victor','BGP Pioneer','BGP Explorer','BGP Prospector','BGP Discovery','BGP Navigator','BGP Surveyor']
vessels=[command('create_vessel',{'name':name})['id'] for name in names]
stop_ids=[command('add_stop',{'vessel_id':v})['stop_id'] for v in vessels]
stop_ids.append(command('add_stop',{'vessel_id':vessels[1]})['stop_id'])
for index in range(13,args.stops):
    vessel=command('create_vessel',{'name':f'BGP Support {index+1}'})['id']
    stop_ids.append(command('add_stop',{'vessel_id':vessel})['stop_id'])
service.close()
from cargo_track.personnel_service import PersonnelService
companion=PersonnelService(data/'personnel-transfer.sqlite3');companion.close()
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Route overview validation');QApplication.setApplicationName('Route overview validation')
app=QApplication([]);configure_application(app);window=WorkspaceWindow(data/'cargo-track.sqlite3',data)
if args.visible:assert app.platformName()=='windows'
def wait(predicate):
    end=time.monotonic()+12
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Route operation did not complete')
def settle():
    for _ in range(10):app.processEvents();time.sleep(.01)
report={'native_visible':args.visible,'data_directory':str(data),'stops':len(stop_ids),'scenarios':[]}
try:
    window.show();wait(lambda:window.snapshot is not None and not window._refresh_wait)
    for theme in ('light','dark'):
        for font in (11,12):
            QSettings().setValue('appearance/theme',theme);QSettings().setValue('appearance/font_size',font);configure_application(app)
            for width,height in ((1000,700),(1366,768),(1920,1080)):
                window.resize(width,height);settle()
                buttons=[window.route_items.itemAt(i).widget() for i in range(window.route_items.count())]
                assert len(buttons)==len(stop_ids)
                for button in buttons:
                    assert button.isVisible() and window.route_content.rect().contains(button.geometry()),(button.full_title,button.geometry(),window.route_content.rect())
                from PySide6.QtCore import QPoint
                origin=window.route_content.mapTo(window,QPoint(0,0))
                assert origin.y()+window.route_content.height()<=window.height()
                scene={'name':f'{width}x{height}-{font}pt-{theme}','actual_window':[window.width(),window.height()],'all_stops_visible':True,'route_rows':len({b.y() for b in buttons}),'route_height':window.route_content.height()}
                report['scenarios'].append(scene);window.grab().save(str(output/(('stress-' if args.stops!=13 else '')+scene['name']+'.png')))
    assert window.snapshot['current_stop_id'] is None
    QTest.mouseClick(window.route_items.itemAt(len(stop_ids)-1).widget(),Qt.MouseButton.LeftButton)
    wait(lambda:window.snapshot['current_stop_id']==stop_ids[-1] and not window._busy and not window._refresh_wait);settle()
    assert window.route_items.itemAt(len(stop_ids)-1).widget().isChecked()
    report['last_stop_click_uses_original_identity']=True;report['current_stop_remains_manual']=True
    button=window.route_items.itemAt(0).widget();assert [a.text() for a in button.menu().actions() if not a.isSeparator()]==['Move earlier','Move later','Remove this stop']
    report['stop_menus_retained']=True
    window.resize(1000,700);settle();window.grab().save(str(output/'overview-selected.png'))
    (output/('checks.json' if args.stops==13 else f'checks-{args.stops}.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
finally:window.close();app.processEvents()

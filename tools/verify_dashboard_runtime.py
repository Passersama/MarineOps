"""Native Dashboard acceptance with actual services and fictional data only."""
from pathlib import Path
import copy, json, os, sys, time
from threading import Event
from uuid import uuid4
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUTPUT=ROOT/'output/dashboard-release-20261012';OUTPUT.mkdir(exist_ok=True)
data=OUTPUT/('native-fixture-'+str(time.time_ns()));data.mkdir()
os.environ['CARGO_TRACK_DATA_DIR']=str(data)
if '--offscreen' in sys.argv:os.environ['QT_QPA_PLATFORM']='offscreen'
else:os.environ.pop('QT_QPA_PLATFORM',None)
from PySide6.QtCore import Qt,QSettings
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from cargo_track.appearance import configure_application
from cargo_track.berth_plan import generate_plan,export_plan
from cargo_track.domain import Command
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_service import PersonnelService
from cargo_track.service import ApplicationService
from cargo_track.workspace import WorkspaceWindow

cargo=ApplicationService(data/'cargo-track.sqlite3');cargo.open()
def command(name,payload):return cargo.handle(Command(str(uuid4()),name,payload)).result
fleet={name:command('create_vessel',{'name':name})['id'] for name in ('BGP Victor','HB6','BGP Innovator','DFKT2','Niger')}
command('create_voyage',{'name':'20261012 Niger route'})
visits=[command('add_stop',{'vessel_id':fleet[name]})['stop_id'] for name in ('BGP Victor','HB6','BGP Innovator','DFKT2','HB6','BGP Victor','BGP Innovator')]
command('set_setting',{'key':'transfer_vessel_name','value':'Niger'})
for i in range(24):
    description=('Hard Disk','GPS cable','Paper Box','Spare parts','QNAP')[i] if i<5 else 'Material '+str(i+1)
    source,target=(('BGP Innovator','BGP Victor'),('BGP Innovator','DFKT2'),('BGP Innovator','HB6'),('BGP Victor','BGP Innovator'),('HB6','BGP Innovator'))[i] if i<5 else ('HB6','DFKT2')
    no=command('create_transfer',{'description':description,'from_location_id':fleet[source],'to_location_id':fleet[target]})['no']
    if i in (3,4) or 14<=i<=23:command('pick_up',{'no':no,'expected_version':0,'confirmed_location':True})
    if i>=20:command('deliver',{'no':no,'expected_version':1,'confirmed_location':True})
command('choose_stop',{'stop_id':visits[2]});cargo.close()
personnel=PersonnelService(data/'personnel-transfer.sqlite3');personnel.set_setting('transfer_vessel_name','Niger')
crew=personnel.create_plan('October rotation','2026-10-12')
first_names=('Chen Wei','Omar Hassan','Arun Kumar','Miguel Santos','Yusuf Ali','Emmanuel Boateng')
roles=('Second Engineer','Electrician','Able Seaman','Motorman','Deck Cadet','Chief Cook')
for i in range(47):
    name=first_names[i] if i<6 else ('Daniel Mensah' if i==28 else 'Crew Fictional '+str(i+1))
    role=roles[i%6] if i!=28 else 'Chief Officer'
    source,target=('Niger','BGP Innovator') if i<28 else ('BGP Innovator','DFKT2')
    record=personnel.bind_record({'name':name,'position':role,'direction':'Transfer','from_name':source,'to_name':target,'date':'2026-10-12'},read_cargo(data/'cargo-track.sqlite3'))
    personnel.add_passenger(crew,record)
def save(service):
    source=service.planning_source(read_cargo(data/'cargo-track.sqlite3',active_only=True))
    draft=generate_plan(source,service.crew_records(crew,source),[],'2026-10-12',service.port_name(source),mode='Final',personnel_plan_id=crew)
    assert not draft['issues'],draft['issues']
    draft.update(personnel_context=service.context(crew),personnel_source_path=str(service.path))
    return service.save_berth(draft,True)
saved=save(personnel);export_plan(saved,OUTPUT/'dashboard-plan.xlsx');personnel.close()
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Cargo Track Dashboard validation');QApplication.setApplicationName('Isolated validation')
app=QApplication([]);QSettings().setValue('appearance/font_size',11);QSettings().setValue('appearance/theme','light')
original=QFontDatabase.addApplicationFont
with patch.object(QFontDatabase,'addApplicationFont',wraps=original) as calls:
    configure_application(app);configure_application(app);assert calls.call_count==2,calls.call_count
window=WorkspaceWindow(data/'cargo-track.sqlite3',data);window.setWindowTitle('Cargo Track 1.2.1 / Dashboard validation')
def wait(predicate,timeout=20):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Native operation timed out')
def settle():
    for _ in range(10):app.processEvents();time.sleep(.01)
report={'data_directory':str(data),'fictional_data':True,'platform':app.platformName(),'font_assets_registered_once':True,'scenarios':[]}
try:
    window.show();page=window.dashboard_page
    wait(lambda:page.data and not page._jobs and window.snapshot is not None and not window._refresh_wait)
    assert window.pages.currentWidget() is page
    assert page.data['cargo']['counts']=={'Waiting':12,'On Board':8,'Done':4}
    assert (page.data['personnel']['boarding'],page.data['personnel']['leaving'])==(28,19),page.data
    assert page.crew_proxy.rowCount()==47
    assert not page.crew_table.isColumnHidden(2)
    assert {page.crew_proxy.index(i,2).data() for i in range(47)}=={'Boarding','Leaving'}
    report['combined_roster']={'rows':47,'boarding':28,'leaving':19,'movement_column_visible':True}
    assert page.personnel_donut.counts=={'Completed':0,'Pending':47}
    for theme in ('light','dark'):
        for width,height in ((1440,1024),(1366,768),(1000,700)):
            QSettings().setValue('appearance/theme',theme);configure_application(app);page.apply_theme();window.resize(width,height);settle()
            assert page.route_items.count()==7
            assert all(page.route_content.rect().contains(page.route_items.itemAt(i).widget().geometry()) for i in range(7))
            assert page.crew_table.horizontalScrollBar().maximum()==0
            assert page.crew_table.columnWidth(2)>=page.crew_table.fontMetrics().horizontalAdvance('Boarding')+8
            page.grab().save(str(OUTPUT/f'dashboard-{theme}-{width}.png'))
            report['scenarios'].append({'theme':theme,'width':width,'height':height,'actual':(window.width(),window.height()),
                'roster_height':page.crew_table.height(),'roster_row_height':page.crew_table.verticalHeader().defaultSectionSize(),
                'roster_header_height':page.crew_table.horizontalHeader().height(),'route_height':page.route_content.height(),
                'page_content_height':page.content.height(),'viewport_height':page.scroll.viewport().height()})
    window.resize(1440,1024);QSettings().setValue('appearance/theme','light');configure_application(app);page.apply_theme();settle()
    page.open_drawer();assert page.overlay.isVisible();page.grab().save(str(OUTPUT/'dashboard-drawer.png'))
    page.drawer_tabs.setCurrentIndex(1)
    assert page.crew_proxy.rowCount()==47
    page.search.setText('Electrician');wait(lambda:page.drawer_proxy.rowCount()==5)
    page.search.setText('no-match-for-this-name');wait(lambda:page.drawer_proxy.rowCount()==0);assert page.drawer_empty.isVisible()
    page.drawer_tabs.setCurrentIndex(0);page.search.clear();wait(lambda:page.drawer_proxy.rowCount()==47)
    QTest.keyClick(page.search,Qt.Key.Key_Escape);settle();assert not page.overlay.isVisible()
    report.update(roster_search_and_empty=True,drawer_escape=True)
    QTest.mouseClick(page.route_items.itemAt(6).widget(),Qt.MouseButton.LeftButton)
    wait(lambda:window.snapshot['current_stop_id']==visits[6] and page.data['cargo']['current_stop_id']==visits[6] and not page._jobs)
    assert (page.data['personnel']['boarding'],page.data['personnel']['leaving'])==(0,0)
    assert page.personnel_donut.counts=={'Completed':47,'Pending':0}
    QTest.mouseClick(page.route_items.itemAt(2).widget(),Qt.MouseButton.LeftButton)
    wait(lambda:page.data['cargo']['current_stop_id']==visits[2] and not page._jobs)
    page.open_current();wait(lambda:window.pages.currentWidget() is window.cargo_page and window.view=='current_stop' and not window._refresh_wait)
    assert window.navigation.cargo_button.isChecked();window.show_dashboard();wait(lambda:not page._jobs and not page.refresh_timer.isActive())
    report.update(repeated_visits_distinct=True,cargo_navigation=True)
    window.open_personnel();wait(lambda:window.personnel_page and not window.personnel_page._jobs)
    personnel_page=window.personnel_page
    personnel_page.plan_combo.setCurrentIndex(personnel_page.plan_combo.findData(crew));personnel_page.view_state.dirty=True
    with patch.object(personnel_page,'guard_leave',return_value=False):
        assert window.show_dashboard() is False;assert window.pages.currentWidget() is personnel_page
        assert personnel_page.navigation.personnel_button.isChecked()
    personnel_page.view_state.dirty=False;window.show_dashboard();wait(lambda:page.data and not page._jobs and not page.refresh_timer.isActive())
    # Delay a completed old read, then change the exact visit before delivery.
    from cargo_track.dashboard_ui import read_dashboard as real_read
    old_ready=Event();release_old=Event();calls=[]
    def delayed_read(*args,**kwargs):
        result=real_read(*args,**kwargs);calls.append(result)
        if len(calls)==1:
            old_ready.set();release_old.wait(10)
        return result
    with patch('cargo_track.dashboard_ui.read_dashboard',side_effect=delayed_read):
        page.schedule_refresh();wait(old_ready.is_set)
        window._submit('choose_stop',{'stop_id':visits[6]},'Delayed-read scope check')
        wait(lambda:window.snapshot['current_stop_id']==visits[6] and not window._busy)
        release_old.set()
        wait(lambda:not page._jobs and not page.refresh_timer.isActive() and page.data['cargo']['current_stop_id']==visits[6])
        assert page.boarding.text()=='0' and page.crew_model.rowCount()==0
    window._submit('choose_stop',{'stop_id':visits[2]},'Return current visit')
    wait(lambda:not page._jobs and not page.refresh_timer.isActive() and page.data['cargo']['current_stop_id']==visits[2])
    report['delayed_old_read_rejected']=True
    report['unsaved_personnel_navigation_guard']=True
    # Add a large current-visit crew roster and save a new immutable version.
    service=PersonnelService(data/'personnel-transfer.sqlite3')
    source=read_cargo(data/'cargo-track.sqlite3')
    for i in range(47,240):
        record=service.bind_record({'name':'Large Roster '+str(i+1),'position':roles[i%6],'direction':'Transfer','from_name':'Niger','to_name':'BGP Innovator','date':'2026-10-12'},source)
        service.add_passenger(crew,record)
    large=save(service);service.close();page._selected_version=large['id'];page.schedule_refresh()
    wait(lambda:not page._jobs and not page.refresh_timer.isActive() and page.data['personnel']['selected_id']==large['id'])
    height=page.crew_table.height();page.crew_table.scrollToBottom();settle()
    assert height==210 and page.data['personnel']['boarding']==221 and page.crew_proxy.rowCount()==240
    assert page.crew_proxy.index(239,2).data()=='Leaving'
    assert page.boarding.text()=='221' and page.leaving.text()=='19';page.grab().save(str(OUTPUT/'dashboard-large-roster.png'))
    assert page.personnel_donut.counts=={'Completed':0,'Pending':240}
    report.update(large_roster_240=True,fixed_roster_height=height,large_boarding=221,large_leaving=19)
    # Changing the actual roster clears stale counts rather than retaining names.
    service=PersonnelService(data/'personnel-transfer.sqlite3');record=service.passengers(crew)[0];record['position']='Updated position'
    service.edit_crew_entry(record['id'],record,record['version']);service.close();page.schedule_refresh()
    wait(lambda:page.data['personnel']['status']=='stale' and not page._jobs)
    assert page.crew_model.rowCount()==0 and page.boarding.text()=='-';report['stale_roster_clears_counts']=True
    assert not page.personnel_donut.available
    # All visits remain available without horizontal scrolling for longer routes.
    window.show_cargo()
    for i in range(7,24):
        window._submit('add_stop',{'vessel_id':fleet[('BGP Victor','HB6','BGP Innovator','DFKT2')[i%4]]},'Test visit added')
        wait(lambda:not window._busy and not window._refresh_wait)
    window.show_dashboard();window.resize(1000,700);wait(lambda:page.data and len(page.data['cargo']['stops'])==24 and not page._jobs);settle()
    assert all(page.route_content.rect().contains(page.route_items.itemAt(i).widget().geometry()) for i in range(24))
    page.grab().save(str(OUTPUT/'dashboard-24-visits.png'));report['route_24_visits_wrap_without_horizontal_scroll']=True
    report['final']='PASS';(OUTPUT/'native-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    if window.personnel_page:window.personnel_page.view_state.dirty=False
    window.close();app.processEvents()

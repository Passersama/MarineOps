"""Windows Qt link-order acceptance and fictional 1.2.3 print fixtures."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/audit-fixes-1.2.3'
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import QSettings,QTimer,Qt,QItemSelectionModel
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from cargo_track.personnel_ui import CrewLegOrderDialog
from cargo_track.personnel_service import PersonnelService
from cargo_track.berth_plan import export_plan,generate_plan
from test_frontend import FrontendTests
from test_personnel_routes import PersonnelRouteTests

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(OUT/'preferences'))
QApplication.setOrganizationName('Cargo Track 123 validation');QApplication.setApplicationName('Fictional audit fix checks')
FrontendTests.setUpClass();app=FrontendTests.app
report={'platform':app.platformName(),'fictional_data':True,'scenarios':[],'workbooks':[]}
assert app.platformName()=='windows'

for scenario in ('removed-child-relink','reverse-record-order'):
    f=FrontendTests();f.setUp()
    try:
        service=f.page.service;before_cargo=f.f.cargo_path.read_bytes()
        def record(a,b):return service.bind_record({'name':'Audit Fictional','position':'Engineer','date':'2026-10-06',
            'direction':'Transfer','from_name':a,'to_name':b},f.page.source)
        if scenario=='removed-child-relink':
            root=service.add_passenger(f.f.plan,record('INN','CHA'))
            first=service.add_passenger(f.f.plan,record('CHA','Niger'))
            child=service.add_next_leg(first,record('Niger','INN'),f.page.source,0)
            service.remove_crew_entries({child:0});historical=service.passenger(child);history=service.history(child)
            expected=[root,first]
        else:
            second=service.add_passenger(f.f.plan,record('Niger','INN'))
            first=service.add_passenger(f.f.plan,record('CHA','Niger'));expected=[first,second]
        editor=f.draft();rows={t['id']:i for i,t in enumerate(editor.tasks)}
        editor.rows.clearSelection()
        for identifier in expected:
            editor.rows.selectionModel().select(editor.rows.model().index(rows[identifier],0),
                QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        seen=[]
        def approve():
            dialog=app.activeModalWidget()
            if not isinstance(dialog,CrewLegOrderDialog):
                QTimer.singleShot(10,approve);return
            seen.append([t['id'] for t in dialog.ordered_tasks()])
            dialog.grab().save(str(OUT/(scenario+'-dialog.png')))
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
        QTimer.singleShot(0,approve);editor.link_selected_crew_legs();f.wait(lambda:not f.page._write_pending)
        assert seen==[expected] and not f.errors,(seen,f.errors)
        assert service.passenger(expected[1])['previous_task_id']==expected[0]
        backup=OUT/(scenario+'-backup.sqlite3');service.backup(backup);PersonnelService.validate_file(backup)
        stored=service.path.read_bytes();reopened=PersonnelService(service.path)
        try:
            assert reopened.passenger(expected[1])['previous_task_id']==expected[0]
            if scenario=='removed-child-relink':
                assert reopened.passenger(child)==historical and reopened.history(child)==history
        finally:reopened.close()
        assert service.path.read_bytes()==stored and f.f.cargo_path.read_bytes()==before_cargo
        report['scenarios'].append({'name':scenario,'reviewed_order_used':True,'backup_valid':True,
            'reopen_passed':True,'historical_payload_unchanged':True,'cargo_unchanged':True})
    finally:f.tearDown()

for size in (4,120):
    f=PersonnelRouteTests();f.setUp()
    try:
        first,second,source=f.chain()
        for i in range(1,size+1):f.add('CHA','INN',f'Fictional Passenger {i:03d} Long English Full Name')
        materials=[]
        for i in range(2):
            materials.append(f.f.command('create_transfer',{'description':f'Material {i+1:02d} 测试电缆设备 END{i+1:02d}',
                'from_location_id':f.f.a,'to_location_id':f.f.c,'comment':'Fictional material note'})['no'])
        live=f.source();source={**live,'stops':source['stops']}
        draft=generate_plan(source,f.service.crew_records(f.f.plan,source),materials,'2026-10-25',
            f.service.port_name(source),mode='Final',personnel_plan_id=f.f.plan)
        assert not draft['issues'],draft['issues']
        draft['stops'][0]['comment']=('Briefing notes 测试备注. '*100 if size==120 else 'Fictional print check. ')+'COMMENT-END'
        saved=f.service.save_berth(draft,True);frozen=copy.deepcopy(saved)
        path=OUT/('normal-plan.xlsx' if size==4 else 'long-plan.xlsx');export_plan(saved,path)
        assert saved==frozen and f.service.berth_versions()[0]==frozen
        report['workbooks'].append({'path':str(path),'extra_passengers':size,'saved_snapshot_unchanged':True})
        if size==4:
            f.f.cargo.export_to(OUT/'cargo-normal.xlsx','all',{'range':'all'},'xlsx')
            f.f.command('create_transfer',{'description':'Extended Cargo','from_location_id':f.f.a,'to_location_id':f.f.b,
                'comment':('Cargo note '*450)+'CARGO-NOTE-END'})
            f.f.cargo.export_to(OUT/'cargo-long.xlsx','all',{'range':'all'},'xlsx')
    finally:f.tearDown()
report['result']='PASS'
(OUT/'native-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

"""Real Qt workflow: plan, adopt, undo, save/export, and Dashboard independent visits."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import time
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'output/berth-optimizer-release-20261012';OUT.mkdir(parents=True,exist_ok=True)
data=OUT/('fixture-'+str(time.time_ns()));data.mkdir()
os.environ['CARGO_TRACK_DATA_DIR']=str(data)
from PySide6.QtCore import QSettings,Qt
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox
from PySide6.QtTest import QTest
from cargo_track.appearance import configure_application
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_ui import CrewPlanBuilder
from cargo_track.berth_optimization_ui import OptimizationDialog,apply_result,editor_snapshot
from cargo_track.berth_plan import export_plan,plan_assignments
from cargo_track.workspace import WorkspaceWindow

cargo=ApplicationService(data/'cargo-track.sqlite3');cargo.open()
def command(name,args):return cargo.handle(Command(str(uuid4()),name,args)).result
fleet={n:command('create_vessel',{'name':n})['id'] for n in ('A','B','C','Plan Boat')}
command('create_voyage',{'name':'Optimizer acceptance'})
visits=[command('add_stop',{'vessel_id':fleet[n]})['stop_id'] for n in ('A','B','C')]
command('choose_stop',{'stop_id':visits[1]})
for a,b in (('A','B'),('B','C'),('C','A')):command('create_transfer',{'description':'Material '+a+b,'from_location_id':fleet[a],'to_location_id':fleet[b]})
cargo.close();cargo_before=hashlib.sha256((data/'cargo-track.sqlite3').read_bytes()).hexdigest()
service=PersonnelService(data/'personnel-transfer.sqlite3');service.set_setting('transfer_vessel_name','Plan Boat')
roster=service.create_plan('Optimization roster','2026-10-12')
def record(name,a,b):return service.bind_record({'name':name,'position':'Engineer','from_name':a,'to_name':b,'date':'2026-10-12'},read_cargo(data/'cargo-track.sqlite3'))
first=service.add_passenger(roster,record('Linked Person','A','B'))
second=service.add_next_leg(first,record('Linked Person','B','C'),read_cargo(data/'cargo-track.sqlite3'),0)
service.add_passenger(roster,record('Boat Passenger','Plan Boat','B'))
service.add_passenger(roster,record('Leaving Person','B','C'));service.close()
QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(data/'preferences'))
QApplication.setOrganizationName('Optimizer validation');QApplication.setApplicationName('Optimizer validation')
app=QApplication([]);configure_application(app);window=WorkspaceWindow(data/'cargo-track.sqlite3',data)
def wait(predicate,seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise RuntimeError('Optimizer UI timed out')
def settle():
    for _ in range(10):app.processEvents();time.sleep(.01)
report={'data_directory':str(data),'platform':app.platformName(),'fictional_data':True}
try:
    window.show();window.resize(1366,768);wait(lambda:window.snapshot and not window._refresh_wait)
    window.open_personnel();wait(lambda:window.personnel_page and window.personnel_page.source and not window.personnel_page._jobs)
    page=window.personnel_page;page.plan_combo.setCurrentIndex(page.plan_combo.findData(roster));wait(lambda:not page._jobs)
    builder=CrewPlanBuilder(page);original=editor_snapshot(builder)
    # The second linked leg is currently unavailable on the three-call route.
    assert not next(c.isChecked() for t,c in zip(builder.tasks,builder.includes) if t['id']==second)
    dialog=OptimizationDialog(builder);dialog.show();settle()
    for i in range(dialog.materials.count()):dialog.materials.item(i).setCheckState(Qt.CheckState.Checked)
    QTest.mouseClick(dialog.calculate,Qt.MouseButton.LeftButton);wait(lambda:dialog.result is not None and dialog.job is None)
    assert dialog.result['status']=='OPTIMAL',dialog.result
    assert dialog.result['cost']==[5,0],dialog.result
    dialog.grab().save(str(OUT/'auto-plan-preview.png'));QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
    assert dialog.accepted_result
    apply_result(builder,dialog.original,dialog.accepted_result);plan=builder.build();assert not plan['issues'],plan['issues']
    assert len(plan['included'])==7 and len([s for s in plan['stops'] if s['vessel_id']==fleet['B']])==2
    report['unavailable_leg_repaired']=True;report['selected_materials_all_delivered']=True;report['minimum_calls']=5
    assert builder.undo_optimization_button.isEnabled();builder.undo_auto_plan()
    assert builder.route_snapshot()['stops']==original['route'];assert builder.selection_overrides==original['selections']
    report['undo_restores_route_and_scope']=True
    apply_result(builder,original,dialog.accepted_result)
    plan=builder.build();saved=page.service.save_berth(plan,True);export_plan(saved,OUT/'optimized-plan.xlsx')
    # Reopen as inline editor, then confirm material assignments survive reload.
    inline=CrewPlanBuilder(page,saved,inline=True);inline.reload_tasks()
    reopened=inline.build();assert not reopened['issues'],reopened['issues']
    assert plan_assignments(reopened)==plan_assignments(saved)
    page.show_plan(reopened);settle();page.grab().save(str(OUT/'personnel-auto-plan.png'))
    # Invalid manual order retains the strict goal and clears the minimum label.
    inline.route.setCurrentRow(inline.route.count()-1);inline.move_stop(-1)
    assert inline.optimization['status']=='STALE';assert not inline.undo_optimization_button.isEnabled()
    report['manual_changes_invalidate_proof']=True
    # Create a valid independent route with fresh visit IDs to exercise Dashboard fix.
    independent=copy.deepcopy(saved);mapping={s['id']:'plan:dashboard-'+str(i) for i,s in enumerate(independent['stops'])}
    for stop in independent['stops']:stop['id']=mapping[stop['id']]
    for assignment in independent['assignments'].values():
        for side in ('pick','drop'):
            if assignment[side] is not None:assignment[side]=mapping[assignment[side]]
    independent.pop('optimization',None)
    saved_independent=page.service.save_berth(independent,True)
    page.view_state.dirty=False;window.show_dashboard();dashboard=window.dashboard_page;dashboard._selected_version=saved_independent['id'];dashboard.schedule_refresh()
    wait(lambda:dashboard.data and dashboard.data['personnel']['selected_id']==saved_independent['id'] and not dashboard._jobs)
    assert dashboard.data['personnel']['status']=='choose_visit';assert dashboard.plan_visit_combo.isVisible()
    # Find first B call: two boarding people and one leaving person.
    bstop=next(s for s in independent['stops'] if s['vessel_id']==fleet['B'])
    dashboard.plan_visit_combo.setCurrentIndex(dashboard.plan_visit_combo.findData(bstop['id']))
    wait(lambda:dashboard.data['personnel']['status']=='ready' and not dashboard._jobs)
    assert dashboard.data['personnel']['boarding']==2;assert dashboard.data['personnel']['leaving']==1
    assert dashboard.crew_model.rowCount()==3
    settle();dashboard.scroll.ensureWidgetVisible(dashboard.personnel_panel);settle()
    dashboard.grab().save(str(OUT/'dashboard-personnel-fixed.png'))
    report.update(dashboard_boarding=2,dashboard_leaving=1,independent_repeated_visit_selector=True)
    # A new reviewed version after a roster edit must replace the automatic old
    # selection. Pinning the auto-selected old ID used to leave this panel stale.
    changed=page.service.passenger(first);changed['position']='Senior Engineer'
    page.service.edit_crew_entry(first,changed,changed['version'])
    fresh=copy.deepcopy(saved_independent);fresh['personnel_context']=page.service.context(roster)
    fresh['personnel_versions']={r['id']:r['version'] for r in page.service.passengers(roster)}
    for stop in fresh['stops']:
        for group in ('pick_passengers','drop_passengers'):
            for person in stop[group]:
                if person['id']==first:person['position']='Senior Engineer'
    fresh=page.service.save_berth(fresh,True);dashboard.schedule_refresh()
    wait(lambda:dashboard.data['personnel']['selected_id']==fresh['id'] and not dashboard._jobs)
    assert dashboard.data['personnel']['status']=='ready'
    assert dashboard.data['personnel']['boarding']==2 and dashboard.data['personnel']['leaving']==1
    # A user's explicit historical choice is respected and reports stale sources.
    dashboard.version_combo.setCurrentIndex(dashboard.version_combo.findData(saved_independent['id']))
    wait(lambda:dashboard.data['personnel']['status']=='stale' and not dashboard._jobs)
    assert dashboard.data['personnel']['selected_id']==saved_independent['id']
    dashboard.version_combo.setCurrentIndex(0)
    wait(lambda:dashboard.data['personnel']['selected_id']==fresh['id'] and not dashboard._jobs)
    dashboard.plan_visit_combo.setCurrentIndex(dashboard.plan_visit_combo.findData(bstop['id']))
    wait(lambda:dashboard.data['personnel']['status']=='ready' and not dashboard._jobs)
    report['latest_plan_follows_new_save_after_roster_edit']=True
    report['explicit_history_selection_retained']=True
    dialog.deleteLater();builder.deleteLater();inline.deleteLater()
    report['cargo_database_unchanged']=hashlib.sha256((data/'cargo-track.sqlite3').read_bytes()).hexdigest()==cargo_before
    assert report['cargo_database_unchanged']
    report['result']='PASS';(OUT/'native-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    window.close();app.processEvents()

"""Frontend workflow regressions on isolated, fictional personnel fixtures."""
import copy
import json
import os
import shutil
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication,QWidget,QLabel,QMessageBox,QComboBox,QCheckBox
import test_personnel as fixtures
from cargo_track.personnel_ui import PersonnelPage
from cargo_track.personnel_models import ModelTable
from cargo_track.theme_tokens import LIGHT,DARK,render_style

class FrontendTests(unittest.TestCase):
    def test_rename_keeps_dirty_draft_and_selected_list(self):
        editor=self.draft();context=self.page.service.context(self.f.plan)
        with patch('cargo_track.personnel_ui.QInputDialog.getText',return_value=('Renamed crew list',True)):
            self.page.rename_plan()
        self.wait(lambda:not self.page._write_pending)
        self.assertEqual(self.f.plan,self.page.plan_combo.currentData())
        self.assertEqual('Renamed crew list',self.page.plan_combo.currentText())
        self.assertIs(editor,self.page.live_builder);self.assertTrue(self.page.view_state.dirty)
        self.assertEqual(context,self.page.service.context(self.f.plan))

    def test_cancel_history_clear_keeps_saved_version(self):
        saved=self.page.service.save_berth(self.plan,True);self.page.refresh_versions(saved['id'])
        with patch('cargo_track.personnel_ui.confirm',return_value=False):self.page.clear_version_history()
        self.assertEqual([saved],self.page.service.berth_versions())

    def test_clear_history_action_removes_displayed_version(self):
        saved=self.page.service.save_berth(self.plan,True)
        self.page.saved_plan=saved;self.page.show_plan(saved);self.page.refresh_versions(saved['id'])
        with patch('cargo_track.personnel_ui.confirm',return_value=True):self.page.clear_version_history()
        self.wait(lambda:not self.page._write_pending)
        self.assertEqual(0,self.page.versions.count());self.assertIsNone(self.page.saved_plan)
        self.assertFalse(self.page.view_state.has_plan)
        self.assertEqual([saved],self.page.service.berth_versions(True))

    def test_cargo_navigation_cancel_retains_dirty_draft(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QStackedWidget
        from cargo_track.navigation import WorkspaceNavigation
        from cargo_track.workspace import WorkspaceWindow
        editor=self.draft();stack=QStackedWidget();cargo=QWidget();stack.addWidget(cargo);stack.addWidget(self.page);stack.setCurrentWidget(self.page)
        root=SimpleNamespace(personnel_page=self.page,navigation=WorkspaceNavigation('personnel'),pages=stack,cargo_page=cargo,_cargo_actions=[])
        root._sync_navigation=lambda active:WorkspaceWindow._sync_navigation(root,active)
        root.show_cargo=lambda:WorkspaceWindow.show_cargo(root)
        with patch.object(QMessageBox,'exec',return_value=0),self.choice('Cancel'):root.show_cargo()
        self.assertIs(self.page,stack.currentWidget());self.assertIs(editor,self.page.live_builder)
        self.assertTrue(self.page.view_state.dirty);self.assertTrue(self.page.navigation.personnel_button.isChecked())
        self.page.setParent(self.host);stack.deleteLater();root.navigation.deleteLater()

    def test_plan_transfer_origin_does_not_require_a_source_call(self):
        self.page.service.set_setting('transfer_vessel_name', 'Niger')
        data=self.page.service.bind_record({'name':'Already Aboard','position':'OBS','date':'2026-10-06',
            'direction':'Transfer','from_name':'Niger','to_name':'INN'},self.page.source)
        identifier=self.page.service.add_passenger(self.f.plan,data)
        editor=self.draft()
        for i in reversed(range(editor.route.count())):
            if editor.route.item(i).data(Qt.ItemDataRole.UserRole)['vessel_id']==self.f.b:editor.route.takeItem(i)
        editor.refresh_assignments();plan=editor.build()
        self.assertFalse(plan['issues'])
        self.assertEqual(1,sum(r['id']==identifier for s in plan['stops'] for r in s['drop_passengers']))
        self.assertFalse(any(r['id']==identifier for s in plan['stops'] for r in s['pick_passengers']))

    def test_port_is_addable_removable_and_not_forced(self):
        editor=self.draft()
        self.assertFalse(any(editor.route.item(i).data(Qt.ItemDataRole.UserRole)['vessel_id']==self.f.shore for i in range(editor.route.count())))
        editor.vessels.setCurrentIndex(editor.vessels.findData(self.f.shore));editor.add_stop()
        self.assertEqual(self.f.shore,editor.build()['stops'][-1]['vessel_id'])
        editor.route.setCurrentRow(editor.route.count()-1);editor.remove_stop()
        self.assertFalse(any(s['vessel_id']==self.f.shore for s in editor.build()['stops']))

    def test_next_leg_action_saves_same_person_and_assigns_later_visit(self):
        editor=self.draft();editor.rows.selectRow(0)
        old=self.page.service.passenger(editor.tasks[0]['id'])
        data=self.page.service.bind_record({'name':old['name'],'position':old['position'],'date':'2026-10-06',
            'direction':'Transfer','from_name':'CHA','to_name':'INN'},editor.source)
        with patch('cargo_track.personnel_ui.PassengerForm.exec',return_value=1),patch('cargo_track.personnel_ui.PassengerForm.data',return_value=data):
            editor.add_next_crew_leg()
        self.wait(lambda:not self.page._write_pending)
        second=next(t for t in editor.tasks if t.get('previous_task_id')==old['id'])
        self.assertEqual(old['person_id'],second['person_id'])
        editor.append_stop({'id':'plan:again','vessel_id':self.f.a,'vessel_name_snapshot':'CHA'})
        item=editor.route.takeItem(editor.route.count()-1);editor.route.insertItem(2,item);editor.refresh_assignments()
        plan=editor.build();self.assertFalse(plan['issues'])
        self.assertTrue(any(r['id']==second['id'] for r in plan['stops'][2]['pick_passengers']))
        self.assertEqual([],self.errors)

    def test_link_legs_action_preserves_chain_when_preceding_leg_is_excluded(self):
        from cargo_track.berth_plan import plan_assignments, export_plan
        service = self.page.service
        record = lambda source, target: service.bind_record({'name':'Linked Fictional','position':'Engineer',
            'date':'2026-10-06','direction':'Transfer','from_name':source,'to_name':target}, self.page.source)
        first = service.add_passenger(self.f.plan, record('CHA', 'Niger'))
        second = service.add_passenger(self.f.plan, record('Niger', 'INN'))
        editor = self.draft()
        editor.append_stop({'id':'plan:return-niger','vessel_id':self.f.b,'vessel_name_snapshot':'Niger'})
        visit = editor.route.takeItem(editor.route.count()-1);editor.route.insertItem(2,visit)
        editor.refresh_assignments()
        rows = {task['id']: i for i, task in enumerate(editor.tasks)}
        editor.rows.clearSelection()
        from PySide6.QtCore import QItemSelectionModel
        for identifier in (first, second):
            editor.rows.selectionModel().select(editor.rows.model().index(rows[identifier], 0),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        with patch('cargo_track.personnel_ui.CrewLegOrderDialog.exec', return_value=1):editor.link_selected_crew_legs()
        self.wait(lambda:not self.page._write_pending)
        self.assertEqual(first, service.passenger(second)['previous_task_id'])
        plan = editor.build();self.assertEqual([],plan['issues'])
        self.assertEqual('plan:return-niger', plan_assignments(plan)['Passengers:'+second]['pick'])
        saved = service.save_berth(plan, True)
        export_plan(saved, self.f.root/'linked-legs.xlsx')
        rows = {task['id']: i for i, task in enumerate(editor.tasks)}
        editor.includes[rows[first]].setChecked(False)
        invalid = editor.build()
        self.assertTrue(invalid['issues'])
        self.assertNotIn('Passengers:'+second, invalid['included'])
        self.assertEqual([], self.errors)

    def test_link_legs_uses_reviewed_order_instead_of_record_row_order(self):
        service=self.page.service
        def record(a,b):return service.bind_record({'name':'Reverse Fictional','position':'Engineer',
            'date':'2026-10-06','direction':'Transfer','from_name':a,'to_name':b},self.page.source)
        second=service.add_passenger(self.f.plan,record('Niger','INN'))
        first=service.add_passenger(self.f.plan,record('CHA','Niger'))
        editor=self.draft();rows={t['id']:i for i,t in enumerate(editor.tasks)}
        from PySide6.QtCore import QItemSelectionModel
        editor.rows.clearSelection()
        for identifier in (first,second):
            editor.rows.selectionModel().select(editor.rows.model().index(rows[identifier],0),
                QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        with patch('cargo_track.personnel_ui.CrewLegOrderDialog.exec',return_value=1):editor.link_selected_crew_legs()
        self.wait(lambda:not self.page._write_pending)
        self.assertEqual(first,service.passenger(second)['previous_task_id'])
        self.assertEqual([],self.errors)

    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.f=fixtures.PersonnelTests();self.f.setUp()
        self.f.passenger(name='Alex Fictional');self.f.passenger(name='Sam Fictional')
        self.plan=self.f.generate(mode='Final')
        self.other=self.f.service.create_plan('Other crew','2026-10-06')
        shutil.copy2(self.f.root/'personnel.sqlite3',self.f.root/'personnel-transfer.sqlite3')
        self.env=patch.dict(os.environ,{'CARGO_TRACK_DATA_DIR':str(self.f.root)});self.env.start()
        self.host=QWidget();self.host.data_directory=self.f.root;self.host.database_path=self.f.cargo_path
        self.host.brand=QLabel();self.host.brand.setPixmap(QPixmap(160,32))
        self.page=PersonnelPage(self.host,lambda:None);self.errors=[]
        self.error_patch=patch.object(self.page,'show_error',self.errors.append);self.error_patch.start()
        self.wait(lambda:self.page.source is not None and not self.page._jobs)
        self.page.plan_combo.setCurrentIndex(self.page.plan_combo.findData(self.f.plan))
        self.wait(lambda:not self.page._jobs and not self.page._loading_list)

    def tearDown(self):
        self.page._validation_timer.stop();self.page.shutdown();self.page.deleteLater();self.host.deleteLater()
        self.app.processEvents();self.error_patch.stop();self.env.stop();self.f.tearDown()

    def wait(self,predicate):
        end=time.monotonic()+8
        while time.monotonic()<end:
            self.app.processEvents()
            if predicate() and not self.page._jobs and not self.page._loading_list:return
            time.sleep(.01)
        self.fail('Frontend did not complete: '+str(self.errors))

    def draft(self):
        self.page.draft=copy.deepcopy(self.plan);self.page.saved_plan=None;self.page.show_plan(self.page.draft)
        return self.page.live_builder

    def test_legacy_mixed_leg_snapshot_previews_edits_saves_and_exports(self):
        legacy_id=self.plan['included'][0]
        for stop in self.plan['stops']:
            for group in ('pick_passengers','drop_passengers'):
                for task in stop[group]:
                    if task['id']==legacy_id:task['leg_index']=''
        original=copy.deepcopy(self.plan)
        editor=self.draft();self.assertIsNotNone(editor)
        self.assertEqual(original,self.plan)
        self.assertTrue(self.page.save_plan_button.isEnabled())
        plan=editor.build();self.assertFalse(plan['issues']);self.assertEqual([],self.errors)
        self.page.save_version(True);self.wait(lambda:not self.page._write_pending)
        saved=self.page.service.berth_versions()[0];self.assertEqual('Published',saved['status'])
        from cargo_track.berth_plan import export_plan
        target=self.f.root/'legacy-mixed-legs.xlsx';export_plan(saved,target);self.assertTrue(target.is_file())
        self.assertEqual(original,self.plan)

    def choice(self,label):
        return patch('cargo_track.personnel_ui.prompt',return_value=label)

    def test_cancel_export_does_not_create_version_or_replace_editor(self):
        editor=self.draft();before=self.page.service.berth_versions()
        with patch('cargo_track.personnel_ui.QFileDialog.getSaveFileName',return_value=('','')):self.page.export()
        self.assertEqual(before,self.page.service.berth_versions());self.assertIs(editor,self.page.live_builder)
        self.assertTrue(self.page.view_state.dirty)
        self.assertTrue(self.page.view_state.editing);self.assertTrue(self.page.view_state.working_draft_id)

    def test_issue_draft_saves_but_formal_publication_stays_blocked(self):
        self.plan['issues']=[{'task':'Passengers:unknown','name':'Unknown','message':'Needs review'}]
        self.draft()
        # The generated builder determines real issues; use a deliberately unresolved route.
        while self.page.live_builder.route.count():self.page.live_builder.route.takeItem(0)
        self.page.refresh_live_preview()
        self.assertTrue(self.page.draft['issues']);self.assertTrue(self.page.save_draft_button.isEnabled())
        self.assertFalse(self.page.save_plan_button.isEnabled());self.assertFalse(self.page.plan_export_button.isEnabled())
        self.page.save_version(False);self.wait(lambda:not self.page._write_pending)
        self.assertEqual('Draft',self.page.saved_plan['status']);self.assertFalse(self.page.view_state.dirty)
        self.assertFalse(self.page.view_state.editing);self.assertIsNone(self.page.view_state.working_draft_id)
        self.assertFalse(self.page.plan_export_button.isEnabled());self.assertEqual([],self.errors)

    def test_switch_cancel_retains_uuid_and_edits(self):
        editor=self.draft();editor.rows.item(0,2).setText('Changed name')
        with patch.object(QMessageBox,'exec',return_value=0),self.choice('Cancel'):
            self.page.plan_combo.setCurrentIndex(self.page.plan_combo.findData(self.other))
        self.assertEqual(self.f.plan,self.page.plan_combo.currentData());self.assertIs(editor,self.page.live_builder)
        self.assertEqual('Changed name',editor.tasks[0]['name'])

    def test_switch_save_persists_then_changes_list(self):
        self.draft().rows.item(0,2).setText('Saved changed name')
        with patch.object(QMessageBox,'exec',return_value=0),self.choice('Save draft'):
            self.page.plan_combo.setCurrentIndex(self.page.plan_combo.findData(self.other))
        self.wait(lambda:not self.page._write_pending)
        self.assertEqual(self.other,self.page.plan_combo.currentData())
        saved=self.page.service.berth_versions()[0];self.assertEqual('Draft',saved['status'])
        self.assertIn('Saved changed name',str(saved));self.assertEqual([],self.errors)

    def test_switch_discard_changes_list_without_saving(self):
        self.draft()
        with patch.object(QMessageBox,'exec',return_value=0),self.choice('Discard'):
            self.page.plan_combo.setCurrentIndex(self.page.plan_combo.findData(self.other))
        self.assertEqual(self.other,self.page.plan_combo.currentData());self.assertEqual([],self.page.service.berth_versions())

    def test_undo_redo_updates_local_fields_only(self):
        editor=self.draft();before=copy.deepcopy(editor.tasks[0]);original=editor.rows.item(0,2).text()
        editor.rows.item(0,2).setText('Changed');editor.undo_cell();self.assertEqual(original,editor.tasks[0]['name'])
        editor.redo_cell();self.assertEqual('Changed',editor.tasks[0]['name'])
        master=self.page.service.crew_records(self.f.plan,self.page.source)[0]
        self.assertEqual(before['name'],master['name'])

    def test_source_invalidation_preserves_recoverable_edits(self):
        self.draft().rows.item(0,2).setText('Recovery name');self.page.invalidate_plan('Restored source')
        files=list(self.page.recovery_directory.glob('*.json'));self.assertEqual(1,len(files))
        content=json.loads(files[0].read_text(encoding='utf-8'));self.assertTrue(content['source_invalid'])
        self.assertIn('Recovery name',str(content));self.assertFalse(self.page.plan_export_button.isEnabled())
        self.page.recover_draft();self.assertIsNotNone(self.page.live_builder)
        self.assertEqual('Recovery name',self.page.live_builder.tasks[0]['name']);self.assertEqual([],self.errors)

    def test_busy_feedback_is_visible_and_conflicting_commands_disabled(self):
        callbacks=[]
        with patch.object(self.page.service,'submit',side_effect=lambda method,args,done,failed:callbacks.append(done)):
            self.page.run_write('save_berth',(),lambda _:None)
        self.assertTrue(self.page.isEnabled());self.assertFalse(self.page.tabs.isEnabled())
        self.assertFalse(self.page.progress.isHidden());self.assertIn('Saving',self.page.notice.text())
        self.assertTrue(all(not c.isEnabled() for c in self.page._write_commands))
        callbacks[0](None);self.assertTrue(self.page.tabs.isEnabled());self.assertTrue(self.page.progress.isHidden())

    def test_selection_survives_model_refresh_and_filter_numbers_restart(self):
        self.page.passenger_table.selectRow(1);selected=self.page.selected()[0]['id'];self.page.refresh_rows()
        self.assertEqual([selected],[r['id'] for r in self.page.selected()])
        self.page.search.setText('Sam');self.wait(lambda:not self.page._crew_search_timer.isActive())
        self.assertEqual(1,self.page.crew_filter.rowCount());self.assertEqual('1',self.page.crew_filter.index(0,0).data())
        self.page.direction.setCurrentIndex(1);self.app.processEvents();self.assertEqual([],self.errors)

    def test_model_uses_accessible_native_checks_and_demand_editors(self):
        editor=self.draft();self.assertIsInstance(editor.rows,ModelTable)
        self.assertEqual([],editor.rows.findChildren(QComboBox));self.assertEqual([],editor.rows.findChildren(QCheckBox))
        index=editor.rows.model().index(0,0);self.assertIn('Alex',index.data(Qt.ItemDataRole.AccessibleTextRole))
        editor.rows.model().setData(index,Qt.CheckState.Unchecked,Qt.ItemDataRole.CheckStateRole)
        self.assertFalse(editor.includes[0].isChecked());self.assertTrue(self.page.view_state.dirty)

    def test_theme_roles_are_explicit_and_complete(self):
        self.assertEqual(set(LIGHT),set(DARK))
        for dark in (False,True):self.assertNotIn('@',render_style('@focus@ @selection@ @primary_text@',dark))

    def test_save_failure_keeps_dirty_editor(self):
        editor=self.draft();editor.rows.item(0,2).setText('Keep on error')
        with patch.object(self.page.service,'submit',side_effect=lambda m,a,d,f:f('Disk unavailable')):
            self.page.save_version(False)
        self.assertIs(editor,self.page.live_builder);self.assertTrue(self.page.view_state.dirty)
        self.assertFalse(self.page._write_pending);self.assertIn('Disk unavailable',str(self.errors))

    def test_export_failure_reports_saved_version_and_preserves_it(self):
        self.draft();target=self.f.root/'export.xlsx'
        with patch('cargo_track.personnel_ui.QFileDialog.getSaveFileName',return_value=(str(target),'')),patch('cargo_track.personnel_ui.export_plan',side_effect=PermissionError('Destination locked')):
            self.page.export();self.wait(lambda:not self.page._write_pending and not self.page._jobs)
        saved=self.page.service.berth_versions();self.assertEqual(1,len(saved))
        self.assertEqual('Published',saved[0]['status']);self.assertIn('remains saved',str(self.errors))
        self.assertFalse(target.exists());self.assertFalse(self.page.view_state.dirty)

    def test_leave_invalid_source_saves_recovery_without_publishing(self):
        self.draft();self.page.view_state.source_invalid=True
        with patch.object(QMessageBox,'exec',return_value=0),self.choice('Save draft'):
            self.assertTrue(self.page.guard_leave(lambda:None))
        self.assertFalse(self.page.view_state.dirty)
        self.assertEqual(1,len(list(self.page.recovery_directory.glob('*.json'))))
        self.assertEqual([],self.page.service.berth_versions())

    def test_recovery_write_failure_retains_invalid_editor_and_unsaved_content(self):
        editor=self.draft();editor.rows.item(0,2).setText('Preserve despite disk error')
        with patch('pathlib.Path.write_text',side_effect=OSError('Disk unavailable')):
            self.page.invalidate_plan('Source restored')
        self.assertIs(editor,self.page.live_builder);self.assertTrue(self.page.view_state.dirty)
        self.assertTrue(self.page.view_state.source_invalid);self.assertFalse(editor.isEnabled())
        self.assertIn('Preserve despite disk error',str(editor.local_edits))
        self.assertFalse(self.page.plan_export_button.isEnabled())

    def test_export_completion_clears_busy_state_after_source_invalidation(self):
        self.draft();self.page.view_state.export_state='writing'
        self.page.run_read(lambda:(time.sleep(.1),'old file')[1],lambda _:self.fail('Old result was delivered'),channel='export')
        self.page.invalidate_plan('New source')
        self.wait(lambda:not self.page._jobs)
        self.assertEqual('done',self.page.view_state.export_state)
        self.assertTrue(self.page.view_state.source_invalid)

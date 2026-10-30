"""Approved workspace interactions that affect persisted planning data."""
import copy,json
import unittest
import test_frontend as frontend
from cargo_track.personnel_ui import CrewPlanBuilder
from cargo_track.berth_plan import plan_assignments,plan_text


class ApprovedUITests(unittest.TestCase):
    setUpClass=classmethod(frontend.FrontendTests.setUpClass.__func__)
    setUp=frontend.FrontendTests.setUp
    tearDown=frontend.FrontendTests.tearDown
    wait=frontend.FrontendTests.wait
    draft=frontend.FrontendTests.draft

    def test_endpoint_selection_changes_the_joint_assignment_explicitly(self):
        editor=self.draft();task=editor.tasks[0]
        editor.append_stop({'id':'plan:repeat','vessel_id':task['to_id'],'vessel_name_snapshot':task['to_name']})
        editor.refresh_assignments()
        endpoint=editor.endpoint_controls[0][1]
        target=next(i for i,(_,value) in enumerate(endpoint.options) if value=='plan:repeat')
        endpoint.setCurrentIndex(target)
        self.assertEqual('plan:repeat',editor.assignments[0].currentData()['drop'])
        self.assertEqual('plan:repeat',plan_assignments(editor.build())['Passengers:'+task['id']]['drop'])

    def test_removed_endpoint_remains_unavailable_until_an_explicit_choice(self):
        editor=self.draft();old=copy.deepcopy(editor.assignments[0].currentData())
        for i in reversed(range(editor.route.count())):
            if editor.route.item(i).data(256)['id']==old['drop']:editor.route.takeItem(i)
        editor.refresh_assignments()
        self.assertEqual(old,editor.assignments[0].currentData())
        self.assertEqual('Review assignment',editor.endpoint_controls[0][1].currentText())
        self.assertTrue(editor.build()['issues'])

    def test_stop_comment_survives_save_reopen_and_snapshot_is_immutable(self):
        editor=self.draft();editor.route.setCurrentRow(0)
        self.page.stop_comment.setPlainText('An operational stop note')
        self.page.save_version(True);self.wait(lambda:not self.page._write_pending)
        saved=copy.deepcopy(self.page.saved_plan)
        self.assertEqual('An operational stop note',saved['stops'][0]['comment'])
        self.assertNotIn('Unsaved',self.page.plan_notice.text())
        self.page.copy_complete();self.wait(lambda:not self.page._jobs)
        self.page.stop_comment.setPlainText('Revised stop note')
        self.assertEqual(saved,self.page.service.berth_versions()[0])
        self.assertEqual('Revised stop note',self.page.live_builder.build()['stops'][0]['comment'])

    def test_comment_is_recovered_before_debounced_preview_runs(self):
        editor=self.draft();editor.route.setCurrentRow(0)
        self.page.stop_comment.setPlainText('Immediate unsaved note')
        self.page.invalidate_plan('New source')
        payload=json.loads(next(self.page.recovery_directory.glob('*.json')).read_text(encoding='utf-8'))['plan']
        self.assertIn('Immediate unsaved note',payload['stop_comments'].values())

    def test_personnel_views_do_not_show_cargo_rows_but_export_payload_retains_them(self):
        number=self.f.command('create_transfer',{'description':'Fictional cargo','from_location_id':self.f.a,'to_location_id':self.f.b,'physical_id':'','comment':''})['no']
        self.page.refresh_source();self.wait(lambda:not self.page._jobs)
        self.plan=self.f.generate(cargo=[number],mode='Final')
        editor=self.draft();plan=editor.build()
        self.assertTrue(editor.materials)
        self.assertTrue(all(t['kind']=='Passengers' for t in editor.tasks))
        self.assertNotIn('materials',plan_text(plan,personnel_only=True).lower())
        dialog=CrewPlanBuilder(self.page)
        try:
            material_rows=[i for i,t in enumerate(dialog.tasks) if t['kind']=='Materials']
            self.assertTrue(material_rows)
            self.assertTrue(all(dialog.rows.isRowHidden(i) for i in material_rows))
            self.assertTrue(any(s['pick_materials'] or s['drop_materials'] for s in dialog.build()['stops']))
        finally:dialog.deleteLater()

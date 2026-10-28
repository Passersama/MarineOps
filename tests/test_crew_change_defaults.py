"""Crew-change port defaults through workbook import and the actual editor."""
import copy
import unittest
from openpyxl import Workbook
import test_personnel as fixtures
import test_frontend as frontend
from cargo_track.personnel_import import read_personnel_excel
from cargo_track.personnel_service import encode
from cargo_track.personnel_ui import CrewPlanBuilder
from cargo_track.berth_plan import plan_assignments,export_plan


class CrewChangeDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PersonnelTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def record(self,direction,**fields):
        return dict(name='Test Crew',position='Engineer',date='2026-10-06',direction=direction,**fields)
    def test_direction_uses_port_and_vessel_side_endpoint_without_vessel_column(self):
        for direction,fields,expected in (
            ('Sign-on',{'from_name':'Ignore this origin','to_name':'INN'},(self.f.shore,self.f.c)),
            ('Sign-off',{'from_name':'CHA','to_name':'Ignore this destination'},(self.f.a,self.f.shore)),
            ('Sign-on',{'vessel':'INN'},(self.f.shore,self.f.c)),
            ('Sign-off',{'vessel':'CHA'},(self.f.a,self.f.shore))):
            with self.subTest(direction=direction,fields=fields):
                bound=self.f.service.bind_record(self.record(direction,**fields),self.f.snapshot)
                self.assertEqual(expected,(bound['from_id'],bound['to_id']))
                self.assertEqual([],bound['issues'])
    def test_explicit_vessel_side_endpoint_takes_precedence_over_stale_vessel(self):
        bound=self.f.service.bind_record(self.record('Sign-on',vessel='CHA',to_name='INN'),self.f.snapshot)
        self.assertEqual(self.f.c,bound['to_id'])
    def test_missing_or_unknown_ship_still_needs_review_and_transfer_is_not_inferred(self):
        for raw in (self.record('Sign-on'),self.record('Sign-off',from_name='Unknown ship'),self.record('Transfer',to_name='INN')):
            self.assertTrue(self.f.service.bind_record(raw,self.f.snapshot)['issues'])
    def test_one_sided_sign_on_off_headers_import_without_unused_endpoint_columns(self):
        book=Workbook();sheet=book.active
        sheet.append(['Sign-off','Position','From','Date','Sign-on','Position','To','Date'])
        sheet.append(['OFF CREW','Engineer','CHA','2026-10-06','ON CREW','Engineer','INN','2026-10-06'])
        path=self.f.root/'one-sided.xlsx';book.save(path);book.close()
        before=path.read_bytes();parsed=read_personnel_excel(path)
        self.assertEqual(['Sign-off','Sign-on'],[r['direction'] for r in parsed['records']])
        preview=self.f.service.import_preview(parsed,self.f.snapshot,self.f.plan)
        self.assertTrue(all(not item['data']['issues'] for item in preview['items']))
        self.f.service.commit_import(preview)
        people=self.f.service.crew_records(self.f.plan,self.f.snapshot)
        self.assertEqual([(self.f.a,self.f.shore),(self.f.shore,self.f.c)],[(p['from_id'],p['to_id']) for p in people])
        self.assertEqual(before,path.read_bytes())
    def test_legacy_import_with_lost_endpoint_rebinds_from_source_without_rewriting_rows(self):
        for direction,side,vessel in (('Sign-on','to','INN'),('Sign-off','from','CHA')):
            bound=self.f.service.bind_record(self.record(direction,**{side+'_name':vessel}),self.f.snapshot)
            identifier=self.f.service.add_passenger(self.f.plan,bound)
            legacy=copy.deepcopy(bound);legacy.update({side+'_name':'',side+'_id':None,'vessel':'','original_values':{side+'_name':vessel}})
            self.f.service.db.execute('UPDATE passengers SET payload=? WHERE id=?',(encode(legacy),identifier))
        before=self.f.service.db.execute('SELECT payload FROM passengers ORDER BY id').fetchall()
        people=self.f.service.crew_records(self.f.plan,self.f.snapshot)
        self.assertTrue(all(not p['issues'] for p in people))
        self.assertEqual(before,self.f.service.db.execute('SELECT payload FROM passengers ORDER BY id').fetchall())


class CrewChangeEditorTests(unittest.TestCase):
    setUpClass=classmethod(frontend.FrontendTests.setUpClass.__func__)
    setUp=frontend.FrontendTests.setUp
    tearDown=frontend.FrontendTests.tearDown
    wait=frontend.FrontendTests.wait
    def test_new_sign_off_plan_adds_terminal_port_and_publishes_without_review_assignment(self):
        service=self.page.service
        off=service.bind_record({'name':'Returning Crew','position':'Engineer','date':'2026-10-06',
                                'direction':'Sign-off','from_name':'CHA'},self.page.source)
        identifier=service.add_passenger(self.f.plan,off)
        cargo_before=self.f.cargo_path.read_bytes()
        builder=CrewPlanBuilder(self.page)
        try:
            plan=builder.build();self.assertEqual([],plan['issues'])
            self.assertEqual(self.f.shore,plan['stops'][-1]['vessel_id'])
            self.page.draft=plan;self.page.show_plan(plan);editor=self.page.live_builder
            index=next(i for i,t in enumerate(editor.tasks) if t['id']==identifier)
            self.assertNotIn('Review',editor.endpoint_controls[index][0].currentText())
            self.assertNotIn('Review',editor.endpoint_controls[index][1].currentText())
            saved=service.save_berth(editor.build(),True)
            export_plan(saved,self.f.root/'return-port.xlsx')
            self.assertEqual(cargo_before,self.f.cargo_path.read_bytes())
            self.assertEqual(2,sum(s['vessel_id']==self.f.shore for s in saved['stops']))
            self.assertEqual(self.f.shore,saved['stops'][0]['vessel_id'])
            self.assertIn('Passengers:'+identifier,plan_assignments(saved))
        finally:builder.deleteLater()
    def test_manual_port_removal_and_existing_route_are_retained(self):
        service=self.page.service
        identifier=service.add_passenger(self.f.plan,service.bind_record({'name':'Returning Crew','position':'Engineer',
            'date':'2026-10-06','direction':'Sign-off','vessel':'CHA'},self.page.source))
        builder=CrewPlanBuilder(self.page)
        try:
            self.assertEqual(self.f.shore,builder.route.item(builder.route.count()-1).data(256)['vessel_id'])
            builder.route.setCurrentRow(builder.route.count()-1);builder.remove_stop()
            plan=builder.build();self.assertTrue(plan['issues'])
            reopened=CrewPlanBuilder(self.page,base_plan=plan)
            try:self.assertEqual([s['id'] for s in plan['stops']],
                [reopened.route.item(i).data(256)['id'] for i in range(reopened.route.count())])
            finally:reopened.deleteLater()
        finally:builder.deleteLater()

"""Actual failure patterns: shorthand vessels, retained direction and applied aliases."""
import copy
import unittest
from unittest.mock import patch
from openpyxl import Workbook
import test_personnel as fixtures
import test_frontend as frontend
from cargo_track.personnel_import import read_personnel_excel
from cargo_track.personnel_ui import ImportDialog

class CrewVesselMatchingTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PersonnelTests();self.f.setUp()
        self.ids={name:self.f.command('create_vessel',{'name':name})['id'] for name in ('DFKT2','BGP Spirit','BGP Victor','BGP Innovator')}
        from cargo_track.personnel_cargo import read_cargo
        self.source=read_cargo(self.f.cargo_path)
    def tearDown(self):self.f.tearDown()
    def test_real_workbook_short_names_match_active_fleet(self):
        for label,name in (('DFKT 2','DFKT2'),('DFKT-2','DFKT2'),('SPR','BGP Spirit'),('BVC','BGP Victor'),('BGP INV','BGP Innovator')):
            with self.subTest(label=label):self.assertEqual(self.ids[name],self.f.service.resolve_location(self.source,label)['id'])
    def test_explicit_alias_beats_builtin_short_name(self):
        self.f.service.set_alias(self.source,'SPR',self.f.a)
        self.assertEqual(self.f.a,self.f.service.resolve_location(self.source,'SPR')['id'])
        preview=copy.deepcopy(self.source);preview['preview_aliases']={'spr':self.f.b}
        self.assertEqual(self.f.b,self.f.service.resolve_location(preview,'SPR')['id'])
    def test_ambiguous_or_inactive_vessels_are_not_guessed(self):
        source=copy.deepcopy(self.source)
        source['locations'].append(dict(next(r for r in source['locations'] if r['id']==self.ids['DFKT2']),id=999,name='DFKT-2'))
        self.assertIsNone(self.f.service.resolve_location(source,'DFKT 2'))
        source=copy.deepcopy(self.source)
        next(r for r in source['locations'] if r['id']==self.ids['BGP Spirit'])['active']=0
        self.assertIsNone(self.f.service.resolve_location(source,'SPR'))
        source=copy.deepcopy(self.source)
        source['locations'].append(dict(next(r for r in source['locations'] if r['id']==self.ids['BGP Innovator']),id=999,name='BGP Innovative'))
        self.assertIsNone(self.f.service.resolve_location(source,'BGP INN'))
    def test_unmatched_ship_does_not_change_imported_sign_on_off_to_transfer(self):
        parsed=read_personnel_excel(self.f.workbook())
        for row in parsed['records']:row['vessel']='Unknown crew ship'
        self.f.service.commit_import(self.f.service.import_preview(parsed,self.source,self.f.plan))
        before=[dict(r) for r in self.f.service.db.execute('SELECT id,payload FROM passengers ORDER BY id')]
        people=self.f.service.crew_records(self.f.plan,self.source)
        self.assertEqual(4,sum(r['direction']=='Sign-on' for r in people))
        self.assertEqual(1,sum(r['direction']=='Sign-off' for r in people))
        self.assertTrue(all(r['issues'] for r in people))
        self.assertEqual(before,[dict(r) for r in self.f.service.db.execute('SELECT id,payload FROM passengers ORDER BY id')])

class CrewImportMappingTests(unittest.TestCase):
    setUpClass=classmethod(frontend.FrontendTests.setUpClass.__func__)
    setUp=frontend.FrontendTests.setUp
    tearDown=frontend.FrontendTests.tearDown
    wait=frontend.FrontendTests.wait
    def test_selecting_mapping_updates_preview_and_persists_without_extra_refresh_click(self):
        book=Workbook();sheet=book.active
        sheet.append(['Sign-on','Position','To','Date'])
        sheet.append(['New Imported Crew','Engineer','Workbook Alias','2026-10-06'])
        path=self.f.root/'mapped.xlsx';book.save(path);book.close()
        dialog=ImportDialog(self.page,read_personnel_excel(path))
        try:
            self.assertIn('Workbook Alias',dialog.alias_widgets)
            combo=dialog.alias_widgets['Workbook Alias'];combo.setCurrentIndex(combo.findData(self.f.c))
            self.assertEqual(self.f.c,dialog.preview['items'][0]['data']['to_id'])
            self.assertEqual({'workbook alias':self.f.c},dialog.preview['aliases']['values'])
            with patch('cargo_track.personnel_ui.confirm',return_value=True):dialog.commit()
            self.wait(lambda:not self.page._write_pending)
            self.assertEqual([],self.errors)
            self.assertEqual(self.f.c,self.page.service.resolve_location(self.page.source,'Workbook Alias')['id'])
            person=next(r for r in self.page.service.crew_records(self.f.plan,self.page.source) if r['name']=='New Imported Crew')
            self.assertEqual('Sign-on',person['direction']);self.assertEqual(self.f.c,person['to_id'])
        finally:dialog.deleteLater()

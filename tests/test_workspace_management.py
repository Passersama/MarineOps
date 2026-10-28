"""Workspace management regression tests using isolated business records."""
import copy
import shutil
import sqlite3
import unittest
from unittest.mock import patch
import test_personnel as fixtures
from cargo_track.domain import AppError
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_import import PersonnelError


class WorkspaceManagementTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PersonnelTests();self.f.setUp()

    def tearDown(self):self.f.tearDown()

    def test_clear_current_stop_keeps_voyage_order_and_transfers(self):
        self.f.command('choose_stop',{'stop_id':self.f.s1})
        before=self.f.cargo.workspace_snapshot() if hasattr(self.f,'cargo') else None
        self.f.command('clear_current_stop',{'expected_stop_id':self.f.s1})
        from cargo_track.personnel_cargo import read_cargo
        after=read_cargo(self.f.cargo_path)
        self.assertIsNone(after['current_stop_id'])
        self.assertEqual([self.f.s1,self.f.s2,self.f.s3],[s['id'] for s in after['stops']])
        self.f.command('choose_stop',{'stop_id':self.f.s1})
        self.assertEqual(self.f.s1,read_cargo(self.f.cargo_path)['current_stop_id'])

    def test_stale_clear_cannot_clear_another_stop(self):
        self.f.command('choose_stop',{'stop_id':self.f.s2})
        with self.assertRaises(AppError):self.f.command('clear_current_stop',{'expected_stop_id':self.f.s1})
        from cargo_track.personnel_cargo import read_cargo
        self.assertEqual(self.f.s2,read_cargo(self.f.cargo_path)['current_stop_id'])

    def test_rename_keeps_ids_personnel_and_saved_snapshots(self):
        self.f.passenger();snapshot=self.f.service.save_berth(self.f.generate(mode='Final'),True)
        records=copy.deepcopy(self.f.service.passengers(self.f.plan))
        old=next(p for p in self.f.service.plans() if p['id']==self.f.plan)['name']
        self.f.service.rename_plan(self.f.plan,'Renamed 船员名单',old)
        self.assertEqual('Renamed 船员名单',next(p for p in self.f.service.plans() if p['id']==self.f.plan)['name'])
        self.assertEqual(records,self.f.service.passengers(self.f.plan))
        self.assertEqual(snapshot,self.f.service.berth_versions()[0])

    def test_invalid_or_stale_rename_is_atomic(self):
        old=self.f.service.plans()
        for name,expected in (('','Crew change'),('x'*201,'Crew change'),('Okay','Another name')):
            with self.assertRaises(PersonnelError):self.f.service.rename_plan(self.f.plan,name,expected)
        self.assertEqual(old,self.f.service.plans())

    def test_clear_selected_history_preserves_snapshot_and_next_version_number(self):
        draft=self.f.generate(mode='Final')
        first=self.f.service.save_berth(draft,True)
        second=self.f.service.save_berth(draft,True,first['family_id'])
        self.f.service.clear_berth_history([first['id']])
        self.assertEqual([second],self.f.service.berth_versions())
        self.assertIn(first,self.f.service.berth_versions(include_removed=True))
        third=self.f.service.save_berth(draft,True,first['family_id'])
        self.assertEqual(3,third['version'])
        with self.assertRaises(sqlite3.IntegrityError):self.f.service.db.execute('DELETE FROM berth_versions')

    def test_clear_history_is_atomic_on_stale_selection(self):
        saved=self.f.service.save_berth(self.f.generate(mode='Final'),True)
        with self.assertRaises(PersonnelError):self.f.service.clear_berth_history([saved['id'],'missing'])
        self.assertEqual([saved],self.f.service.berth_versions())

    def test_clear_all_history_survives_restart_and_backup(self):
        saved=self.f.service.save_berth(self.f.generate(mode='Final'),True)
        self.f.service.clear_berth_history([saved['id']])
        backup=self.f.root/'history-backup.sqlite3';self.f.service.backup(backup)
        restored=PersonnelService(backup)
        try:
            self.assertEqual([],restored.berth_versions())
            self.assertEqual([saved],restored.berth_versions(True))
        finally:restored.close()

    def test_restore_legacy_backup_adds_management_tables(self):
        legacy=self.f.root/'legacy.sqlite3';self.f.service.backup(legacy)
        conn=sqlite3.connect(legacy)
        conn.executescript('DROP TABLE removed_berth_history; DROP TABLE module_history;');conn.close()
        PersonnelService.validate_file(legacy)
        self.f.service.restore(legacy)
        self.assertEqual([],self.f.service.berth_versions())
        self.f.service.rename_plan(self.f.plan,'After restore','Crew change')
        PersonnelService.validate_file(self.f.service.path)

    def test_failed_gateway_open_closes_its_executor(self):
        from cargo_track.personnel_worker import PersonnelGateway
        from concurrent.futures import ThreadPoolExecutor
        executor=ThreadPoolExecutor(max_workers=1)
        with patch('cargo_track.personnel_worker.ThreadPoolExecutor',return_value=executor),patch('cargo_track.personnel_worker.PersonnelService',side_effect=PersonnelError('Invalid database')):
            with self.assertRaises(PersonnelError):PersonnelGateway(self.f.root/'invalid.sqlite3')
        self.assertTrue(executor._shutdown)

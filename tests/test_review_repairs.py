"""Regression coverage for the architecture review's failure scenarios."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_personnel as fixtures
from cargo_track.domain import AppError
from cargo_track.personnel_import import PersonnelError
from cargo_track.berth_plan import export_plan


class RecoveryRestartTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PersonnelTests();self.f.setUp()
        self.f.command('create_transfer', {'description':'Fictional equipment',
            'from_location_id':self.f.a,'to_location_id':self.f.b})
        self.backup=self.f.root/'backup.sqlite3';self.f.cargo.create_backup(self.backup)
    def tearDown(self):self.f.tearDown()
    def assert_restart_blocked(self):
        source=Path(__file__).resolve().parents[1]/'src'
        code=('import sys; from cargo_track.service import ApplicationService; '
              'ApplicationService(sys.argv[1]).open()')
        result=subprocess.run([sys.executable,'-c',code,str(self.f.cargo_path)],
            env={**os.environ,'PYTHONPATH':str(source)},capture_output=True,text=True,timeout=15)
        self.assertNotEqual(0,result.returncode)
        self.assertIn('recover',result.stderr.lower())
    def test_double_failure_remains_blocked_in_a_fresh_process(self):
        replace=os.replace
        def fail(src,dst):
            if str(src).endswith(('.restore','.rollback')):raise PermissionError('Injected failure')
            return replace(src,dst)
        with patch('cargo_track.service.os.replace',side_effect=fail),self.assertRaises(AppError):
            self.f.cargo.restore_backup(self.backup)
        self.assertTrue(self.f.cargo.recovery_marker.exists())
        self.assertFalse(self.f.cargo_path.exists());self.assert_restart_blocked()
        self.assertFalse(self.f.cargo_path.exists())
    def test_interrupt_after_each_destructive_rename_blocks_restart(self):
        replace=os.replace
        for phase in ('original','replacement'):
            with self.subTest(phase=phase):
                def interrupt(src,dst):
                    value=replace(src,dst)
                    if ((phase=='original' and Path(src)==self.f.cargo_path)
                            or (phase=='replacement' and str(src).endswith('.restore'))):
                        raise KeyboardInterrupt('Simulated process interruption')
                    return value
                with patch('cargo_track.service.os.replace',side_effect=interrupt),self.assertRaises(KeyboardInterrupt):
                    self.f.cargo.restore_backup(self.backup)
                self.assert_restart_blocked()
                record=json.loads(self.f.cargo.recovery_marker.read_text())
                replace(record['previous_ledger'],self.f.cargo_path)
                self.f.cargo.recovery_marker.unlink();self.f.cargo.open()
    def test_missing_legacy_main_with_rollback_copy_does_not_create_empty_ledger(self):
        self.f.cargo.close()
        old=self.f.cargo_path.with_name('.'+self.f.cargo_path.name+'.legacy.rollback')
        os.replace(self.f.cargo_path,old)
        self.assert_restart_blocked();self.assertFalse(self.f.cargo_path.exists())
    def test_recovery_record_failure_leaves_original_open_and_unchanged(self):
        original=self.f.cargo_path.read_bytes();replace=os.replace
        def fail_marker(src,dst):
            if Path(dst)==self.f.cargo.recovery_marker:raise PermissionError('Cannot commit marker')
            return replace(src,dst)
        with patch('cargo_track.service.os.replace',side_effect=fail_marker),self.assertRaises(AppError) as error:
            self.f.cargo.restore_backup(self.backup)
        self.assertEqual('RESTORE_PREPARE_FAILED',error.exception.code)
        self.assertEqual(original,self.f.cargo_path.read_bytes())
        self.assertEqual(1,self.f.cargo.workspace_snapshot()['counts']['all'])
    def test_success_clears_marker_and_allows_restart(self):
        self.f.cargo.restore_backup(self.backup)
        self.assertFalse(self.f.cargo.recovery_marker.exists())
        self.f.cargo.close();self.f.cargo.open()
        self.assertEqual(1,self.f.cargo.workspace_snapshot()['counts']['all'])


class ManualPlanContractTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PersonnelTests();self.f.setUp()
        self.identifier=self.f.passenger(source='CHA',target='Niger')
        self.plan=self.f.generate(mode='Final')
    def tearDown(self):self.f.tearDown()
    def test_missing_repeated_and_misplaced_actions_cannot_publish(self):
        for mutation in ('missing','duplicate','wrong_place','missing_scope'):
            with self.subTest(mutation=mutation):
                plan=copy.deepcopy(self.plan);drop=plan['stops'][1]['drop_passengers']
                if mutation=='missing':drop.clear()
                elif mutation=='duplicate':drop.append(copy.deepcopy(drop[0]))
                elif mutation=='wrong_place':plan['stops'][2]['drop_passengers'].append(drop.pop())
                else:
                    for stop in plan['stops']:
                        stop['drop_passengers'].clear();stop['pick_passengers'].clear()
                    plan['included'].clear()
                with self.assertRaises(PersonnelError):self.f.service.save_berth(plan,True)
        self.assertEqual([],self.f.service.berth_versions())
    def test_formal_export_rejects_missing_delivery_without_touching_destination(self):
        saved=self.f.service.save_berth(self.plan,True)
        saved['stops'][1]['drop_passengers'].clear()
        target=self.f.root/'existing.xlsx';target.write_bytes(b'keep existing output')
        with self.assertRaises(PersonnelError):export_plan(saved,target)
        self.assertEqual(b'keep existing output',target.read_bytes())
    def test_backup_validation_rejects_incomplete_published_manual_plan(self):
        plan=copy.deepcopy(self.plan);plan['stops'][1]['drop_passengers'].clear()
        plan.update(id=str(uuid4()),family_id=str(uuid4()),version=1,status='Published')
        self.f.service.db.execute('INSERT INTO berth_versions VALUES(?,?,?,?,?,?)',
            (plan['id'],plan['family_id'],1,'Published',json.dumps(plan),'2026-10-29'))
        with self.assertRaises(PersonnelError):self.f.service.validate_file(self.f.service.path)


class AsyncPersonnelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        import test_frontend as frontend
        frontend.FrontendTests.setUpClass()
        self.fixture=frontend.FrontendTests();self.fixture.setUp()
        self.page=self.fixture.page
    def tearDown(self):self.fixture.tearDown()
    def test_slow_database_refresh_keeps_qt_heartbeat_running(self):
        import time
        from PySide6.QtCore import QTimer
        ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
        invoke=self.page.service._invoke
        def slow(name,args,kwargs):
            if name=='ui_state':time.sleep(.3)
            return invoke(name,args,kwargs)
        try:
            with patch.object(self.page.service,'_invoke',side_effect=slow),patch.object(
                    self.page.service,'call_blocking',side_effect=AssertionError('UI must not wait on a database future')):
                started=time.monotonic();self.page.refresh_source()
                self.assertLess(time.monotonic()-started,.15)
                self.fixture.wait(lambda:not self.page._jobs)
                self.assertGreaterEqual(len(ticks),5)
                self.assertTrue(self.page.rows_data)
        finally:timer.stop()
    def test_save_and_selected_version_loading_use_async_gateway(self):
        self.fixture.draft()
        with patch.object(self.page.service,'call_blocking',side_effect=AssertionError('Blocking UI database call')):
            self.page.save_version(True)
            self.fixture.wait(lambda:not self.page._write_pending)
            saved=self.page.saved_plan
            self.assertEqual('Published',saved['status'])
            self.page.refresh_versions(saved['id']);self.page.load_version()
            self.fixture.wait(lambda:not self.page._jobs)
            self.assertEqual(saved['id'],self.page.saved_plan['id'])
    def test_detached_model_does_not_scan_unselected_rosters_or_decode_history(self):
        model=self.page.read_model
        self.assertEqual(self.page.plan_combo.currentData(),model.state['plan_id'])
        self.assertNotIn('payloads',model.state)
        with self.assertRaises(PersonnelError):model.passengers(self.fixture.other)
        model.settings()['transfer_vessel_name']='Changed only in returned copy'
        self.assertNotEqual('Changed only in returned copy',model.settings().get('transfer_vessel_name'))
    def test_refresh_after_restore_falls_back_when_old_list_no_longer_exists(self):
        self.page.refresh_plans('a-list-absent-after-restore',force=True)
        self.fixture.wait(lambda:not self.page._jobs)
        self.assertEqual(self.page.read_model.state['plan_id'],self.page.plan_combo.currentData())
        self.assertFalse(self.page._loading_list)
        self.assertTrue(self.page.tabs.isEnabled())

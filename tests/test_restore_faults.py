"""Disk failure injection against the real restore service and worker boundary."""
import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cargo_track.domain import AppError, Command
from cargo_track.schema import check_integrity
from cargo_track.service import ApplicationService


class RestoreFaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "ledger.sqlite3"
        self.service = ApplicationService(self.path)
        self.service.open()
        shore = self.service.workspace_snapshot()["shore_location_id"]
        for number in (1, 2):
            self.service.handle(Command(f"seed-{number}", "create_transfer", {
                "description": f"Cargo {number}", "from_location_id": shore, "to_location_id": shore,
            }))
            if number == 1:
                self.backup = self.root / "backup.sqlite3"
                self.service.create_backup(self.backup)
        self.original_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.original_dump = self.dump(self.path)
        self.original_epoch = self.service.dataset_epoch

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def assert_live_unchanged(self):
        self.assertEqual(2, self.service.workspace_snapshot()["counts"]["all"])
        self.assertEqual(self.original_epoch, self.service.dataset_epoch)
        # Reopening SQLite can alter header counters without changing ledger data.
        self.assertEqual(self.original_dump, self.dump(self.path))
        self.assertEqual([], check_integrity(str(self.path)))
        self.assertEqual([], list(self.root.glob("*.restore")))

    @staticmethod
    def dump(path):
        conn = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True)
        try:return tuple(conn.iterdump())
        finally:conn.close()

    def test_safety_backup_save_denied_preserves_current_ledger(self):
        real = os.replace
        def fail(src, dst):
            if "before-restore" in str(dst):
                raise PermissionError("Injected safety-copy save denial")
            return real(src, dst)
        with patch("cargo_track.service.os.replace", side_effect=fail), self.assertRaises(AppError) as caught:
            self.service.restore_backup(self.backup)
        self.assertEqual("BACKUP_FAILED", caught.exception.code)
        self.assert_live_unchanged()
        self.assertEqual([], list(self.root.glob("*.tmp")))

    def test_partial_preparation_copy_is_cleaned(self):
        def fail(src, dst):
            Path(dst).write_bytes(b"partial copy")
            raise OSError("Injected disk full while copying")
        with patch("cargo_track.service.shutil.copy2", side_effect=fail), self.assertRaises(AppError) as caught:
            self.service.restore_backup(self.backup)
        self.assertEqual("RESTORE_PREPARE_FAILED", caught.exception.code)
        self.assert_live_unchanged()

    def test_prepared_database_validation_failure_preserves_live_ledger(self):
        def validate(path):
            return ["Injected corruption"] if str(path).endswith(".restore") else check_integrity(path)
        with patch("cargo_track.service.check_integrity", side_effect=validate), self.assertRaises(AppError) as caught:
            self.service.restore_backup(self.backup)
        self.assertEqual("BACKUP_INVALID", caught.exception.code)
        self.assert_live_unchanged()

    def test_original_rename_denied_reopens_unchanged_ledger(self):
        real = os.replace
        def fail(src, dst):
            if Path(src) == self.path:
                raise PermissionError("Injected ledger rename denial")
            return real(src, dst)
        with patch("cargo_track.service.os.replace", side_effect=fail), self.assertRaises(AppError) as caught:
            self.service.restore_backup(self.backup)
        self.assertEqual("RESTORE_FAILED", caught.exception.code)
        self.assert_live_unchanged()

    def test_install_replacement_denied_rolls_back_identical_ledger(self):
        real = os.replace
        def fail(src, dst):
            if str(src).endswith(".restore"):
                raise PermissionError("Injected replacement denial")
            return real(src, dst)
        with patch("cargo_track.service.os.replace", side_effect=fail), self.assertRaises(AppError) as caught:
            self.service.restore_backup(self.backup)
        self.assertEqual("RESTORE_FAILED", caught.exception.code)
        self.assert_live_unchanged()
        self.assertTrue(Path(caught.exception.details["safety_copy"]).is_file())

    def test_replacement_open_failure_restores_original(self):
        real = self.service.open
        calls = 0
        def fail_once():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("Injected replacement reopen failure")
            return real()
        with patch.object(self.service, "open", side_effect=fail_once), self.assertRaises(AppError) as caught:
            self.service.restore_backup(self.backup)
        self.assertEqual("RESTORE_FAILED", caught.exception.code)
        self.assert_live_unchanged()

    def test_double_failure_keeps_original_and_safety_copy_and_blocks_writes(self):
        real = os.replace
        def fail(src, dst):
            if str(src).endswith((".restore", ".rollback")):
                raise PermissionError("Injected replacement and rollback denial")
            return real(src, dst)
        with patch("cargo_track.service.os.replace", side_effect=fail), self.assertRaises(AppError) as caught:
            self.service.restore_backup(self.backup)
        self.assertEqual("RESTORE_RECOVERY_REQUIRED", caught.exception.code)
        self.assertIsNone(self.service.connection)
        old = Path(caught.exception.details["previous_ledger"])
        safety = Path(caught.exception.details["safety_copy"])
        self.assertEqual(self.original_hash, hashlib.sha256(old.read_bytes()).hexdigest())
        for file in (old, safety):
            self.assertEqual(self.original_dump, self.dump(file))
            self.assertEqual([], check_integrity(str(file)))
        with self.assertRaises(AppError) as unavailable:
            self.service.workspace_snapshot()
        self.assertEqual("DATABASE_UNAVAILABLE", unavailable.exception.code)

    def test_worker_remains_in_maintenance_after_unrecoverable_restore(self):
        from cargo_track.worker import DatabaseWorker
        worker = DatabaseWorker(self.path)
        worker.service = self.service
        maintenance, errors = [], []
        worker.maintenance.connect(maintenance.append)
        worker.request_failed.connect(lambda request, error: errors.append(error))
        real = os.replace
        def fail(src, dst):
            if str(src).endswith((".restore", ".rollback")):
                raise PermissionError("Injected replacement and rollback denial")
            return real(src, dst)
        with patch("cargo_track.service.os.replace", side_effect=fail):
            worker.request("restore-test", "_restore", {"path":str(self.backup)})
        self.assertEqual([True, True], maintenance)
        self.assertEqual("RESTORE_RECOVERY_REQUIRED", errors[0]["code"])

    def test_rollback_cleanup_denied_does_not_report_failed_restore(self):
        real = Path.unlink
        def fail(path, *args, **kwargs):
            if str(path).endswith(".rollback"):
                raise PermissionError("Injected cleanup denial")
            return real(path, *args, **kwargs)
        with patch.object(Path, "unlink", new=fail):
            result = self.service.restore_backup(self.backup)
        self.assertEqual(1, self.service.workspace_snapshot()["counts"]["all"])
        self.assertNotEqual(self.original_epoch, self.service.dataset_epoch)
        self.assertTrue(Path(result["retained_rollback"]).exists())
        self.assertEqual([], check_integrity(str(self.path)))

    def test_live_database_is_not_a_backup_destination(self):
        with self.assertRaises(AppError) as caught:
            self.service.create_backup(self.path)
        self.assertEqual("BACKUP_TARGET_ACTIVE_DATABASE", caught.exception.code)
        self.assert_live_unchanged()

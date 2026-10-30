"""Defensive regression checks using disposable, fictional local data."""
import os
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import test_personnel as fixtures
from cargo_track.personnel_cargo import read_cargo
from cargo_track.personnel_import import PersonnelError, read_personnel_excel


class BackupSchemaTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PersonnelTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_personnel_rejects_unrecognized_schema_without_changing_live_data(self):
        f = self.fixture
        f.passenger()
        for suffix, sql in (
            ('view', 'CREATE VIEW additional_preview AS SELECT 1 AS value'),
            ('trigger', 'CREATE TRIGGER additional_notice AFTER INSERT ON passengers BEGIN SELECT 1; END;'),
        ):
            with self.subTest(kind=suffix):
                candidate = f.root / (suffix + '.sqlite3')
                f.service.backup(candidate)
                with closing(sqlite3.connect(candidate)) as connection:
                    connection.execute(sql)
                    connection.commit()
                before = f.service.path.read_bytes()
                with self.assertRaises(PersonnelError):
                    f.service.restore(candidate)
                self.assertEqual(before, f.service.path.read_bytes())

    def test_cargo_rejects_unrecognized_view_without_changing_live_data(self):
        f = self.fixture
        candidate = f.root / 'cargo-extra-view.sqlite3'
        f.cargo.create_backup(candidate)
        with closing(sqlite3.connect(candidate)) as connection:
            connection.execute('CREATE VIEW additional_preview AS SELECT 1 AS value')
            connection.commit()
        before = f.cargo.path.read_bytes()
        from cargo_track.domain import AppError
        with self.assertRaises(AppError):
            f.cargo.restore_backup(candidate)
        self.assertEqual(before, f.cargo.path.read_bytes())


class SourcePathTests(unittest.TestCase):
    def test_network_and_device_sources_are_rejected_before_filesystem_access(self):
        paths = ('//example.invalid/share/ledger.sqlite3',
                 r'\\example.invalid\share\ledger.sqlite3',
                 r'\\?\UNC\example.invalid\share\ledger.sqlite3',
                 r'\\?\C:\ledger.sqlite3')
        for path in paths:
            with self.subTest(path=path), patch(
                    'cargo_track.source_paths.os.lstat',
                    side_effect=AssertionError('Filesystem access must not occur')):
                with self.assertRaisesRegex(PersonnelError, 'local Cargo database'):
                    read_cargo(path)


class ImportedLabelTests(unittest.TestCase):
    def test_import_labels_display_markup_as_literal_text(self):
        import test_frontend
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        from cargo_track.personnel_ui import ImportDialog
        test_frontend.FrontendTests.setUpClass()
        fixture = test_frontend.FrontendTests()
        fixture.setUp()
        dialog = None
        try:
            parsed = read_personnel_excel(fixture.f.workbook())
            parsed['sheet'] = '<b>Worksheet</b>'
            parsed['records'][0]['vessel'] = '<b>Unmatched vessel</b>'
            dialog = ImportDialog(fixture.page, parsed)
            fixture.wait(lambda:dialog.preview is not None and not fixture.page._jobs)
            self.assertEqual(Qt.TextFormat.PlainText, dialog.summary.textFormat())
            self.assertIn('<b>Worksheet</b>', dialog.summary.text())
            self.assertEqual(Qt.TextFormat.PlainText, dialog.missing.textFormat())
            labels = [label for label in dialog.findChildren(QLabel)
                      if label.text().startswith(('Excel vessel:', 'Fleet vessel matches:'))]
            self.assertTrue(labels)
            self.assertTrue(all(label.textFormat() == Qt.TextFormat.PlainText for label in labels))
        finally:
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
                fixture.app.processEvents()
            fixture.tearDown()

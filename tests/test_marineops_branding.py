"""English public identity with intentionally unchanged storage/activation identity."""
import ast
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from PySide6.QtCore import QStandardPaths

import test_frontend as frontend
from cargo_track import __version__
from cargo_track.about_ui import AboutDialog, PRODUCT_DESCRIPTION
from cargo_track.navigation import WorkspaceNavigation
from cargo_track.ui import HelpDialog

ROOT=Path(__file__).resolve().parents[1]


class MarineOpsBrandingTests(unittest.TestCase):
    setUpClass=classmethod(frontend.FrontendTests.setUpClass.__func__)
    def test_every_navigation_opens_shared_english_about(self):
        for active in ('dashboard','cargo','personnel'):
            navigation=WorkspaceNavigation(active)
            try:
                self.assertEqual('MarineOps',navigation.title.text())
                self.assertEqual('MarineOps logo',navigation.brand.accessibleName())
                with patch('cargo_track.navigation.show_about') as show:
                    navigation.about_button.click();show.assert_called_once()
                self.assertNotIn(PRODUCT_DESCRIPTION,navigation.findChild(type(navigation.title)).text())
            finally:navigation.deleteLater()
        self.app.processEvents()
    def test_about_contains_description_actual_version_and_english_only(self):
        dialog=AboutDialog()
        try:
            self.assertEqual('About MarineOps',dialog.windowTitle())
            text=' '.join(label.text() for label in (dialog.title,dialog.version,dialog.description,dialog.summary))
            self.assertIn(__version__,text);self.assertIn(PRODUCT_DESCRIPTION,text)
            self.assertIn('cargo transfers',text);self.assertFalse(re.search(r'[\u3400-\u9fff]',text))
        finally:dialog.deleteLater()
    def test_help_keeps_every_context_anchor_and_is_english(self):
        html=(ROOT/'assets/help/user-guide.html').read_text(encoding='utf-8')
        anchors=set(re.findall(r'id="([^"]+)"',html))
        self.assertEqual(anchors,{'text-case','start','cargo','delete','fleet','voyages','search','backup',
            'settings','keys','personnel','legs','workspace','approved','dashboard','audit-fixes-123',
            'optimizer','crew-defaults','crew-vessel-matching'})
        self.assertFalse(re.search(r'[\u3400-\u9fff]',html));self.assertNotIn('Cargo Track Help',html)
        dialog=HelpDialog(section='crew-defaults')
        try:self.assertEqual('MarineOps Help',dialog.windowTitle());self.assertIn('Sign-on',dialog.browser.toPlainText())
        finally:dialog.deleteLater()
    def test_legacy_persistence_and_single_instance_id_are_retained(self):
        source=(ROOT/'src/cargo_track/main.py').read_text(encoding='utf-8')
        tree=ast.parse(source)
        assignments={node.func.attr:node.args[0].value for node in ast.walk(tree) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Attribute) and node.func.attr in {'setOrganizationName','setApplicationName','setApplicationDisplayName'}
            and node.args and isinstance(node.args[0],ast.Constant)}
        self.assertEqual(assignments,dict(setOrganizationName='Cargo Track',setApplicationName='Cargo Track',setApplicationDisplayName='MarineOps'))
        self.assertIn('f"CargoTrack-{user_key}"',source)
        self.assertIn('.cargo-track.instance.lock',source)
        self.assertIn('QSettings("CargoTrack","CargoTrack")',(ROOT/'src/cargo_track/ui.py').read_text(encoding='utf-8'))
    def test_display_name_does_not_change_default_data_directory(self):
        before=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        previous=self.app.applicationDisplayName()
        try:
            self.app.setApplicationDisplayName('MarineOps')
            self.assertEqual(before,QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        finally:self.app.setApplicationDisplayName(previous)


if __name__=='__main__':unittest.main()

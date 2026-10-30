"""Modal result and keyboard regressions for shared application dialogs."""
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit
from cargo_track.dialogs import FileDialog, InputDialog, PromptDialog, prompt


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_escape_cancels_and_confirm_selects_action(self):
        dialog=PromptDialog(None,'Confirm pickup','Confirm the pickup?',rows=(('Cargo','Pump'),('Location','BGP Victor')),
                            buttons=('Cancel','Confirm pickup'))
        self.assertTrue(dialog.buttons['Cancel'].isDefault())
        QTimer.singleShot(0,lambda:QTest.keyClick(dialog,Qt.Key.Key_Escape))
        self.assertEqual(QDialog.DialogCode.Rejected,dialog.exec());self.assertIsNone(dialog.choice)
        dialog=PromptDialog(None,'Confirm pickup','Confirm?',buttons=('Cancel','Confirm pickup'))
        QTimer.singleShot(0,dialog.buttons['Confirm pickup'].click)
        self.assertEqual(QDialog.DialogCode.Accepted,dialog.exec());self.assertEqual('Confirm pickup',dialog.choice)

    def test_text_entry_accepts_and_cancel_returns_empty(self):
        def submit():
            dialog=self.app.activeModalWidget();dialog.findChild(QLineEdit).setText('New voyage');dialog.buttons['OK'].click()
        QTimer.singleShot(0,submit)
        self.assertEqual(('New voyage',True),InputDialog.getText(None,'New voyage','Voyage name'))
        QTimer.singleShot(0,lambda:self.app.activeModalWidget().reject())
        self.assertEqual(('',False),InputDialog.getText(None,'New voyage','Voyage name',text='Old'))

    def test_prompt_does_not_call_system_beep(self):
        QTimer.singleShot(0,lambda:self.app.activeModalWidget().buttons['OK'].click())
        with patch.object(QApplication,'beep') as beep:
            self.assertEqual('OK',prompt(None,'Notice','Saved',buttons=('OK',),default='OK'))
        beep.assert_not_called()

    def test_cargo_confirmation_preserves_location_guard(self):
        from cargo_track.ui import CargoTrackWindow
        row={'no':7,'version':3,'is_void':False,'current_relation':'neither',
             'from_name':'Origin','to_name':'Destination','description':'Pump'}
        calls=[]
        host=SimpleNamespace(_selected_row=lambda:row,_submit=lambda *args:calls.append(args))
        with patch('cargo_track.ui.confirm',return_value=False):
            CargoTrackWindow.run_selected_action(host,'pick_up')
        self.assertEqual([],calls)
        with patch('cargo_track.ui.confirm',return_value=True) as confirm:
            CargoTrackWindow.run_selected_action(host,'deliver')
        self.assertEqual('deliver',calls[0][0]);self.assertTrue(calls[0][1]['confirmed_location'])
        self.assertEqual((('Cargo','Pump'),('Location','Destination')),confirm.call_args.args[4])
        calls.clear();row['current_relation']='from'
        with patch('cargo_track.ui.confirm') as confirm:
            CargoTrackWindow.run_selected_action(host,'pick_up')
        confirm.assert_not_called();self.assertNotIn('confirmed_location',calls[0][1])

    def test_save_dialog_checks_existing_file_and_keeps_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'example.xlsx';target.write_text('original')
            with patch('cargo_track.dialogs.prompt',return_value='Cancel') as confirm:
                def cancel_after_check():
                    dialog=self.app.activeModalWidget();dialog.accept();dialog.reject()
                QTimer.singleShot(0,cancel_after_check)
                self.assertEqual(('', ''),FileDialog.getSaveFileName(None,'Export',str(target),'Excel (*.xlsx)'))
                confirm.assert_called_once()
            with patch('cargo_track.dialogs.prompt',return_value='Replace'):
                QTimer.singleShot(0,lambda:self.app.activeModalWidget().accept())
                path,_=FileDialog.getSaveFileName(None,'Export',str(target),'Excel (*.xlsx)')
                self.assertEqual(target,Path(path));self.assertEqual('original',target.read_text())
            QTimer.singleShot(0,lambda:self.app.activeModalWidget().accept())
            path,_=FileDialog.getSaveFileName(None,'Export',str(Path(directory)/'new'),'Excel (*.xlsx)')
            self.assertEqual('new.xlsx',Path(path).name)

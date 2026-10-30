"""Render all workspace headers using isolated, empty databases."""
from pathlib import Path
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cargo_track import __version__

OUT = ROOT / 'output' / f'workspace-headers-{__version__}'
data = OUT / f'fictional-data-{time.time_ns()}'
data.mkdir(parents=True)
os.environ['CARGO_TRACK_DATA_DIR'] = str(data)
os.environ.pop('QT_QPA_PLATFORM', None)

from PySide6.QtCore import QPoint, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog
from cargo_track.appearance import configure_application
from cargo_track.about_ui import AboutDialog
from cargo_track.workspace import WorkspaceWindow

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(data / 'preferences'))
app = QApplication([])
app.setOrganizationName('MarineOps header validation')
app.setApplicationName('Isolated fixture')
QSettings().setValue('appearance/theme', 'light')
configure_application(app)
window = WorkspaceWindow(data / 'cargo-track.sqlite3', data)


def wait(predicate):
    end = time.monotonic() + 20
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise RuntimeError('Native workspace did not become ready')


report = {'version': __version__, 'platform': app.platformName(),
          'fictional_data_only': True, 'captures': [], 'about_dialogs': []}
try:
    window.show()
    wait(lambda: window.snapshot is not None and not window._busy and not window._refresh_wait)
    window.open_personnel()
    wait(lambda: window.personnel_page.source is not None and not window.personnel_page._jobs)
    for theme in ('light', 'dark'):
        window.dashboard_page.choose_theme(theme)
        for width, height in ((1366, 768), (1000, 700)):
            window.resize(width, height)
            for name, show, page, navigation in (
                ('dashboard', window.show_dashboard, window.dashboard_page, window.dashboard_page.navigation),
                ('cargo', window.show_cargo, window.cargo_page, window.navigation),
                ('personnel', window.open_personnel, window.personnel_page, window.personnel_page.navigation),
            ):
                show()
                for _ in range(5):
                    app.processEvents()
                button = window.sidebar_buttons[name]
                assert button.isVisible() and button.isEnabled() and button.isChecked(), name
                capture = f'{name}-{theme}-{width}.png'
                assert window.grab().save(str(OUT / capture))
                report['captures'].append({'file': capture, 'workspace': name,
                    'requested_width': width, 'actual_width': window.width(),
                    'sidebar_navigation': True})
        window.show_settings()
        app.processEvents()
        from PySide6.QtWidgets import QPushButton
        about = next(b for b in window.settings_page.findChildren(QPushButton) if b.text().startswith('About MarineOps'))
        assert about.isVisible() and about.isEnabled()
        seen = []
        def close_about():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, AboutDialog):
                seen.append(dialog.version.text())
                dialog.accept()
        QTimer.singleShot(100, close_about)
        about.click()
        assert seen and __version__ in seen[0]
        report['about_dialogs'].append('settings-' + theme)
    window.show_cargo()
    seen_help = []
    def close_help():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QDialog):
            seen_help.append(dialog.windowTitle())
            dialog.accept()
    QTimer.singleShot(100, close_help)
    window.open_help('optimizer')
    assert seen_help == ['MarineOps Help']
    report['shared_help_opens'] = True
    report['result'] = 'PASS'
finally:
    window.close()
    app.processEvents()
(OUT / 'native-validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))

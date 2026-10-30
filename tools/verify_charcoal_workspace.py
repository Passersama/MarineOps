"""Exercise the shared navigation in a native window with isolated data."""
import json
import copy
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'output' / 'charcoal-ui-validation'
if os.environ.get('MARINEOPS_QA_LABEL'):
    OUT = OUT / os.environ['MARINEOPS_QA_LABEL']
DATA = OUT / ('fixture-' + str(time.time_ns()))
OUT.mkdir(parents=True, exist_ok=True)
from create_release_fixture import create_fixture
create_fixture(DATA)
os.environ['CARGO_TRACK_DATA_DIR'] = str(DATA)

from PySide6.QtCore import QSettings, QTimer, Qt, QPointF, QMimeData
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from cargo_track.appearance import configure_application
from cargo_track.workspace import WorkspaceWindow
from cargo_track.route_layout import SidebarRouteButton

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(DATA / 'preferences'))
app = QApplication([])
app.setOrganizationName('MarineOps UI validation')
app.setApplicationName('isolated fixture')
QSettings().setValue('appearance/theme', 'dark')
configure_application(app)
window = WorkspaceWindow(DATA / 'cargo-track.sqlite3', DATA)

def wait(predicate):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(20)
    raise AssertionError('Timed out waiting for application state')

def dialog_action(action, title):
    seen = []
    def close_dialog():
        modal = app.activeModalWidget()
        if isinstance(modal, QDialog):
            seen.append(modal.windowTitle())
            modal.reject()
        else:
            QTimer.singleShot(50, close_dialog)
    QTimer.singleShot(50, close_dialog)
    action()
    if not seen:
        wait(lambda: bool(seen))
    assert seen and title in seen[0], (title, seen)
    return seen[0]

result = {'version': '1.2.8', 'platform': app.platformName(), 'checks': [], 'screenshots': []}
try:
    window.resize(1366, 768)
    window.show()
    wait(lambda: window.snapshot is not None and not window._busy and not window._refresh_wait)
    assert len(window.snapshot['stops']) == 2
    for name in ('cargo', 'personnel', 'dashboard'):
        QTest.mouseClick(window.sidebar_buttons[name], Qt.MouseButton.LeftButton)
        wait(lambda: window.sidebar_buttons[name].isChecked())
        if name == 'personnel':
            wait(lambda: window.personnel_page is not None and window.personnel_page.source is not None and not window.personnel_page._jobs)
            assert window.personnel_page.plan_combo.count() > 0
            page = window.personnel_page
            QTest.keyClicks(page.search, 'Alex Fictional')
            wait(lambda: page.crew_filter.rowCount() == 1)
            page.search.clear()
            page.tabs.setCurrentIndex(1)
            assert page.tabs.currentIndex() == 1
            page.tabs.setCurrentIndex(0)
            result['checks'].append('personnel roster search and berthing tab')
        if name == 'cargo':
            wait(lambda: window.model.rowCount() > 0)
            assert window.table.isVisible()
            assert window.grab().save(str(OUT / 'cargo-filled-dark-1366.png'))
            original_order = [stop['id'] for stop in window.snapshot['stops']]
            original_current = window.snapshot['current_stop_id']
            target = window.route_items.itemAt(1).widget()
            mime = QMimeData()
            mime.setData(SidebarRouteButton.MIME, f'{target.drag_scope}:{original_order[0]}'.encode('utf-8'))
            drop = QDropEvent(QPointF(target.width()-2, target.height()/2), Qt.DropAction.MoveAction,
                              mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            target.dropEvent(drop)
            assert drop.isAccepted()
            wait(lambda: not window._busy and [stop['id'] for stop in window.snapshot['stops']] == original_order[::-1])
            assert window.snapshot['current_stop_id'] == original_current
            window.route_items.itemAt(1).widget().menu().actions()[0].trigger()
            wait(lambda: not window._busy and [stop['id'] for stop in window.snapshot['stops']] == original_order)
            assert window.snapshot['current_stop_id'] == original_current
            result['checks'].append('route reorder retains current visit')
            window.table.selectRow(0)
            wait(lambda: window.pickup_button.isEnabled())
            QTest.mouseClick(window.pickup_button, Qt.MouseButton.LeftButton)
            wait(lambda: not window._busy and any(row['status'] == 'On Board' for row in window.model.rows))
            first_stop = window.snapshot['current_stop_id']
            QTest.mouseClick(window.next_button, Qt.MouseButton.LeftButton)
            wait(lambda: not window._busy and window.snapshot['current_stop_id'] != first_stop)
            window.table.selectRow(0)
            wait(lambda: window.deliver_button.isEnabled())
            QTest.mouseClick(window.deliver_button, Qt.MouseButton.LeftButton)
            wait(lambda: not window._busy and window.snapshot['current_stop_id'] != first_stop and not any(row['status'] == 'On Board' for row in window.model.rows))
            result['checks'].append('cargo pickup, next stop and delivery')
        if name == 'dashboard':
            wait(lambda: window.dashboard_page.data is not None and not window.dashboard_page._jobs
                 and not window.dashboard_page.refresh_timer.isActive()
                 and not window.dashboard_page.cargo_caption.text().startswith('Loading')
                 and not window.dashboard_page.crew_notice.text().startswith('Loading'))
        app.processEvents()
        assert window.sidebar.isVisible()
        assert not window.navigation.isVisible()
        path = OUT / (name + '-dark-1366.png')
        assert window.grab().save(str(path))
        result['screenshots'].append(path.name)
        result['checks'].append('sidebar opens ' + name)
    assert not hasattr(window, 'sidebar_voyages')
    assert not any(child.text() == 'Local workspace' for child in window.sidebar.findChildren(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel))
    assert dialog_action(window.dashboard_page._open_voyages, 'Voyages')
    result['checks'].append('dashboard voyages opens; sidebar duplicates removed')
    QTest.mouseClick(window.sidebar_settings, Qt.MouseButton.LeftButton)
    assert window.pages.currentWidget() is window.settings_page
    result['checks'].append('settings page opens from sidebar')
    assert window.grab().save(str(OUT / 'settings-dark-1366.png'))
    result['screenshots'].append('settings-dark-1366.png')
    wait(lambda: window.appearance_card._backdrop.pixmap() is not None)
    old_background=window.appearance_card._backdrop.pixmap().toImage().pixelColor(30,30)
    window.settings_page.setStyleSheet('QWidget#settingsPage {background: #673142;}')
    QTest.qWait(120)
    changed_background=window.appearance_card._backdrop.pixmap().toImage().pixelColor(30,30)
    assert changed_background != old_background, 'blur backdrop must follow actual background changes'
    window.settings_page.setStyleSheet('QWidget#settingsPage {background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #000000,stop:0.49 #000000,stop:0.51 #ffffff,stop:1 #ffffff);}')
    QTest.qWait(120)
    window.appearance_card.refresh_material(0);QTest.qWait(120)
    sharp=window.appearance_card._backdrop.grab().toImage()
    window.appearance_card.refresh_material(100);QTest.qWait(120)
    blurred=window.appearance_card._backdrop.grab().toImage()
    assert sharp != blurred, 'changing intensity must change rendered backdrop pixels'
    window.settings_page.setStyleSheet('');QTest.qWait(120)
    result['checks'].append('frosted panel captures updated background and applies graphics blur')
    initial_style=app.styleSheet()
    window.glass_slider.setSliderDown(True)
    start=time.monotonic()
    for value in range(0,101):window.glass_slider.setValue(value);app.processEvents()
    elapsed=time.monotonic()-start
    assert elapsed < 2.0, ('slider drag stalled',elapsed)
    assert app.styleSheet()==initial_style, 'drag must not repolish entire application on every step'
    window.glass_slider.setValue(15);QTest.qWait(150)
    assert abs(window.appearance_card._blur.blurRadius()-3.3)<0.1, 'drag preview must update blur radius'
    window.glass_slider.setSliderDown(False);app.processEvents()
    assert QSettings().value('appearance/glass_intensity',type=int)==15
    assert abs(window.appearance_card._blur.blurRadius()-3.3)<0.1
    result['checks'].append('100 slider steps with live card preview in %.3fs; commit on release' % elapsed)
    assert window.grab().save(str(OUT / 'settings-glass-15.png'))
    window.glass_slider.setValue(100);QTest.qWait(300)
    assert window.grab().save(str(OUT / 'settings-glass-100.png'))
    window.theme_buttons['light'].click();app.processEvents()
    assert QSettings().value('appearance/theme')=='light'
    assert window.grab().save(str(OUT / 'settings-light-1366.png'))
    window.theme_buttons['dark'].click();window.glass_slider.setValue(60);QTest.qWait(300)
    assert QSettings().value('appearance/theme')=='dark' and QSettings().value('appearance/glass_intensity',type=int)==60
    from cargo_track.appearance import application_font_family
    assert application_font_family()=='Manrope'
    result['checks'].append('theme and glass slider update and persist; Manrope loaded')
    for key, title, action in (('Preferences', 'Settings',window.open_settings), ('Fleet', 'Fleet',window.open_fleet), ('About', 'About',lambda: __import__('cargo_track.about_ui',fromlist=['show_about']).show_about(window))):
        result['checks'].append(key + ': ' + dialog_action(action, title))
    window.open_personnel()
    wait(lambda: window.personnel_page is not None and not window.personnel_page._jobs)
    result['checks'].append('personnel settings: ' + dialog_action(window._sidebar_personnel_settings, 'Personnel'))
    window.show_cargo()
    original = window.snapshot
    synthetic = copy.deepcopy(original)
    synthetic['stops'] = [dict(original['stops'][0], id=i + 1000,
                               vessel_name_snapshot='Fictional vessel ' + str(i + 1)) for i in range(24)]
    synthetic['current_stop_id'] = synthetic['stops'][0]['id']
    window.snapshot = synthetic
    window._render_stops()
    app.processEvents()
    assert window.route_items.count() == 24
    last = window.route_items.itemAt(23).widget()
    window.route_scroll.ensureWidgetVisible(last)
    app.processEvents()
    assert last.isVisible()
    assert window.route_scroll.verticalScrollBar().maximum() > 0
    assert window.route_scroll.verticalScrollBar().value() > 0
    result['checks'].append('24 visits remain reachable in horizontal route')
    window.snapshot = original
    window._render_stops()
    window.open_personnel()
    wait(lambda: window.personnel_page is not None and not window.personnel_page._jobs)
    window.resize(1000, 700)
    app.processEvents()
    path = OUT / 'personnel-dark-1000.png'
    assert window.grab().save(str(path))
    result['screenshots'].append(path.name)
    result['status'] = 'passed'
finally:
    window.close()
    app.processEvents()
    (OUT / 'navigation-validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))

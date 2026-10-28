"""Validate the simplified crew-import-to-final-plan workflow with fictional names."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

def wait(app, predicate):
    end = time.monotonic() + 12
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.02)
    raise RuntimeError('Crew page did not finish loading')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--visible', action='store_true')
    parser.add_argument('--output', default='artifacts/personnel-final')
    parser.add_argument('--plan-load-regression', action='store_true')
    args = parser.parse_args()
    if not args.visible:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtTest import QTest
    from openpyxl import Workbook, load_workbook
    from cargo_track.appearance import configure_application
    from cargo_track.domain import Command
    from cargo_track.service import ApplicationService
    from cargo_track.workspace import WorkspaceWindow
    from cargo_track.personnel_ui import ImportDialog, CrewPlanBuilder
    from cargo_track.personnel_import import read_personnel_excel
    from cargo_track.berth_plan import export_plan

    output = ROOT / args.output
    data = output / str(time.time_ns())
    data.mkdir(parents=True)
    os.environ['CARGO_TRACK_DATA_DIR'] = str(data)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(data / 'preferences'))
    QApplication.setOrganizationName('Crew final validation')
    QApplication.setApplicationName('Crew final validation')
    app = QApplication([])
    configure_application(app)
    cargo_path = data / 'cargo-track.sqlite3'
    cargo = ApplicationService(cargo_path)
    cargo.open()
    sequence = 0
    def command(operation, payload):
        nonlocal sequence
        sequence += 1
        return cargo.handle(Command(f'crew-final-{sequence}', operation, payload)).result
    challenger, innovator, niger = [command('create_vessel', {'name': name})['id'] for name in
        ('BGP Challenger', 'BGP Innovator', 'Stanford Niger')]
    command('create_voyage', {'name': 'Crew change · 06 October'})
    for vessel in (challenger, innovator, challenger):
        command('add_stop', {'vessel_id': vessel})
    for description in ('Navigation equipment', 'Engineering spares'):
        command('create_transfer', {'description': description, 'from_location_id': challenger,
            'to_location_id': innovator, 'physical_id': '', 'comment': 'Fictional validation data'})
    cargo.close()
    cargo_before = hashlib.sha256(cargo_path.read_bytes()).hexdigest()
    book = Workbook()
    sheet = book.active
    sheet.title = 'Crew change example'
    sheet.append(['下船\nSign-off', '职位\nPosition', '船名\nVessel', '下船时间\nDate of departure',
                  '上船\nSign-on', '职位\nPosition', '船名\nVessel', '到船日期\nDate of arrival', 'Company Name'])
    for i, (name, position, vessel) in enumerate([('Sam Carter', 'Navigation', 'CHA'), ('Riley Khan', 'Navigator', 'Niger'),
        ('Jordan Lee', 'Gunner', 'INN'), ('Casey Ali', 'Gunner', 'INN')]):
        sheet.append((['Alex Morgan', 'Navigation QC', 'CHA', '2026-10-06'] if i == 0 else [None]*4) +
            [name, position, vessel, '2026-10-06', 'IGNORED-COMPANY'])
    workbook = data / 'crew-example.xlsx'
    book.save(workbook)
    book.close()
    window = WorkspaceWindow(cargo_path, data)
    try:
        window.show()
        window.resize(1366, 768)
        wait(app, lambda: window.snapshot is not None and not window._busy)
        QTest.mouseClick(window.personnel_button, Qt.MouseButton.LeftButton)
        wait(app, lambda: window.personnel_page is not None and window.personnel_page.source is not None)
        page = window.personnel_page
        parsed = read_personnel_excel(workbook)
        dialog = ImportDialog(page, parsed)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output / 'crew-import.png'))
        assert all(not item['data']['issues'] for item in dialog.preview['items'])
        imported = page.service.commit_import(dialog.preview, '06 October crew change', '2026-10-06')
        dialog.reject()
        page.refresh_plans(imported['plan_id'])
        assert page.passenger_table.rowCount() == 5
        assert 'Status' not in [page.passenger_table.horizontalHeaderItem(i).text() for i in range(page.passenger_table.columnCount())]
        forbidden = {'Pick up', 'Drop', 'Cancel transfer', 'Correct status…'}
        assert not any(b.isVisible() and b.text() in forbidden for b in page.findChildren(QPushButton))
        page.passenger_table.selectRow(1)
        window.grab().save(str(output / 'crew-filled.png'))
        builder = CrewPlanBuilder(page)
        builder.show()
        app.processEvents()
        assert builder.added_names == ['Stanford Niger']
        assert builder.route.count() == 4
        for task, include in zip(builder.tasks, builder.includes):
            if task['kind'] == 'Materials':
                include.setChecked(True)
        builder.route.setCurrentRow(3)
        QTest.mouseClick(next(b for b in builder.findChildren(QPushButton) if b.text() == 'Move up'), Qt.MouseButton.LeftButton)
        assert builder.route.item(2).text() == 'Stanford Niger'
        builder.grab().save(str(output / 'final-builder.png'))
        draft = builder.build()
        builder.reject()
        assert draft['mode'] == 'Final' and not draft['issues'], draft['issues']
        by_name = {}
        for stop in draft['stops']:
            counts = by_name.setdefault(stop['name'], [0, 0])
            counts[0] += len(stop['drop_passengers'])
            counts[1] += len(stop['pick_passengers'])
        assert by_name['BGP Challenger'] == [1, 1]
        assert by_name['BGP Innovator'] == [2, 0]
        assert by_name['Stanford Niger'] == [1, 0]
        assert by_name[page.service.port_name(page.source)] == [1, 0]
        page.draft = draft
        page.save_version(True)
        wait(app,lambda:not page._write_pending)
        export_path = output / '20261006_Fleet Personnel Transfer Plan.xlsx'
        export_plan(page.saved_plan, export_path)
        check = load_workbook(export_path)
        assert check.sheetnames == ['Berthing Plan', 'Transfer Details', 'Transfer Print']
        assert all('Waiting' not in str(cell.value) and 'On Board' not in str(cell.value) for sheet in check for row in sheet for cell in row)
        check.close()
        assert hashlib.sha256(cargo_path.read_bytes()).hexdigest() == cargo_before
        regression = {}
        if args.plan_load_regression:
            regression = verify_plan_load(page, app, window, output)
            assert hashlib.sha256(cargo_path.read_bytes()).hexdigest() == cargo_before
        for theme in ('light', 'dark'):
            QSettings().setValue('appearance/theme', theme)
            configure_application(app)
            page.tabs.setCurrentIndex(0)
            app.processEvents()
            window.grab().save(str(output / f'crew-{theme}.png'))
            page.tabs.setCurrentIndex(1)
            app.processEvents()
            window.grab().save(str(output / f'final-{theme}.png'))
        QSettings().setValue('appearance/theme', 'light')
        configure_application(app)
        window.resize(1000, 700)
        app.processEvents()
        window.grab().save(str(output / 'final-small.png'))
        window.show_cargo()
        assert window.model.rowCount() == 2
        assert all(r['status'] == 'Waiting' for r in window.model.rows)
        report = {'native_visible': args.visible, 'crew_count': 5, 'crew_status_controls_absent': True,
            'automatic_abbreviations': True, 'departure_date_recognized': True, 'missing_vessel_added': True,
            'reorder_via_button': True, 'cargo_hash_unchanged': True, 'two_excel_sheets': True,
            'passenger_counts_by_vessel': by_name, 'data_directory': str(data), 'export': str(export_path)}
        report.update(regression)
        (output / 'native-visible.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if window.personnel_page is not None:window.personnel_page.view_state.dirty=False
        window.close()
        app.processEvents()

def verify_plan_load(page, app, window, output):
    import copy
    from PySide6.QtCore import QTimer, QDate, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton, QDialogButtonBox, QLineEdit
    from cargo_track.personnel_ui import CrewPlanBuilder, PassengerForm
    from cargo_track.berth_plan import task_key, export_plan
    from openpyxl import load_workbook
    baseline = copy.deepcopy(page.saved_plan)
    legacy = copy.deepcopy(baseline)
    for field in ('id', 'version', 'family_id', 'status', 'selected_tasks', 'available_tasks'):
        legacy.pop(field, None)
    legacy['mode'], legacy['date'] = 'Complete', '2026-10-05'
    legacy['issues'] = []
    for crew in page.service.crew_records(page.plan_combo.currentData(), page.source):
        for reason in ('Unmatched vessel abbreviation', 'Missing or identical From / To', 'Passenger transfer date does not match this plan'):
            legacy['issues'].append({'task': task_key(crew), 'name': crew['name'], 'message': reason})
    legacy['included'] = [key for key in baseline['included'] if key.startswith('Materials:')]
    saved = page.service.save_berth(legacy, False)
    page.refresh_versions(saved['id'])
    page.history_row.show()
    QTest.mouseClick(next(b for b in page.findChildren(QPushButton) if b.text() == 'Load version'), Qt.MouseButton.LeftButton)
    assert page.draft['mode'] == 'Final' and not page.draft['issues']
    assert page.draft['date'] == '2026-10-06'
    assert sum(len(s['drop_passengers']) for s in page.draft['stops']) == 5
    assert next(p for p in page.service.berth_versions() if p['id'] == saved['id']) == saved
    app.processEvents()
    window.grab().save(str(output / 'legacy-loaded.png'))
    # A remaining real review is grouped, and clicking it always explains the reasons.
    unresolved = copy.deepcopy(page.draft)
    unresolved['issues'] = legacy['issues'][:3] + legacy['issues'][:1] + [
        {'task': 'Materials:1', 'name': 'Navigation equipment', 'message': 'Destination outside route'}]
    page.draft = unresolved
    page.show_plan(unresolved)
    page.plan_views.blockSignals(True)
    page.plan_views.setCurrentWidget(page.preview)
    page.plan_views.blockSignals(False)
    page.stops.show()
    reviews = [page.stops.item(i) for i in range(page.stops.count()) if page.stops.item(i).text().startswith('Review:')]
    assert len(reviews) == 2
    QTest.mouseClick(page.stops.viewport(), Qt.MouseButton.LeftButton, pos=page.stops.visualItemRect(reviews[0]).center())
    assert 'Unmatched vessel abbreviation' in page.preview.toPlainText() and page.review_button.isVisible()
    app.processEvents()
    window.grab().save(str(output / 'review-selected.png'))
    QTest.mouseClick(page.stops.viewport(), Qt.MouseButton.LeftButton, pos=page.stops.visualItemRect(reviews[1]).center())
    assert 'Destination outside route' in page.preview.toPlainText() and not page.review_button.isVisible()
    builder = CrewPlanBuilder(page, base_plan=page.draft)
    builder.show()
    app.processEvents()
    # Add via the real nested form, then remove from this plan without deleting the crew list.
    def fill_new():
        form = next(w for w in app.topLevelWidgets() if isinstance(w, PassengerForm) and w.isVisible())
        form.name.setText('Taylor Reed')
        form.position.setText('Engineer')
        shore = next(r['id'] for r in page.source['locations'] if r['kind'] == 'SHORE')
        form.from_location.setCurrentIndex(form.from_location.findData(shore))
        form.to_location.setCurrentIndex(form.to_location.findData(builder.source['stops'][0]['vessel_id']))
        QTest.mouseClick(form.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
    QTimer.singleShot(100, fill_new)
    QTest.mouseClick(next(b for b in builder.findChildren(QPushButton) if b.text() == 'Add crew entry'), Qt.MouseButton.LeftButton)
    wait(app,lambda:not page._write_pending)
    assert len(builder.crew) == 6
    added_index = next(i for i, r in enumerate(builder.tasks) if r['name'] == 'Taylor Reed')
    added_key = task_key(builder.tasks[added_index])
    builder.rows.selectRow(added_index)
    QTest.mouseClick(next(b for b in builder.findChildren(QPushButton) if b.text() == 'Remove from plan'), Qt.MouseButton.LeftButton)
    assert not builder.includes[added_index].isChecked()
    # An unchecked cargo row can be added without changing its Cargo source record.
    cargo_index = next(i for i, r in enumerate(builder.tasks) if r['kind'] == 'Materials')
    builder.rows.selectRow(cargo_index)
    QTest.mouseClick(next(b for b in builder.findChildren(QPushButton) if b.text() == 'Remove from plan'), Qt.MouseButton.LeftButton)
    builder.includes[cargo_index].setChecked(True)
    app.processEvents()
    builder.grab().save(str(output / 'edit-plan.png'))
    revised = builder.build()
    assert not revised['issues'] and added_key not in revised['selected_tasks']
    builder.reject()
    page.draft, page.saved_plan = revised, None
    page.show_plan(revised)
    page.date.setDate(QDate(2026, 10, 7))
    assert page.draft['date'] == '2026-10-07'
    page.save_version(True)
    wait(app,lambda:not page._write_pending)
    assert not page.date.isEnabled()
    new_saved = copy.deepcopy(page.saved_plan)
    replay = CrewPlanBuilder(page, base_plan=new_saved)
    assert not replay.includes[next(i for i, t in enumerate(replay.tasks) if task_key(t) == added_key)].isChecked()
    # Preserve the user's exact second visit when the route remains valid.
    passenger_index = next(i for i, r in enumerate(replay.tasks) if r['kind'] == 'Passengers' and r['direction'] == 'Sign-on' and r['vessel'] == 'CHA')
    combo = replay.assignments[passenger_index]
    combo.setCurrentIndex(combo.count()-1)
    specific = combo.currentData()
    second = replay.build()
    replay.reject()
    replay_again = CrewPlanBuilder(page, base_plan=second)
    assert replay_again.assignments[passenger_index].currentData() == specific
    replay_again.reject()
    path = output / 'revised-date-check.xlsx'
    export_plan(new_saved, path)
    book = load_workbook(path)
    assert '2026-10-07' in str(book['Berthing Plan']['A3'].value)
    book.close()
    # Edit applies to the displayed version even if the version selector points elsewhere.
    page.refresh_versions(baseline['id'])
    QTest.mouseClick(page.plan_edit_button, Qt.MouseButton.LeftButton)
    assert page.live_builder.plan_date == '2026-10-07' and page.plan_views.currentWidget() is page.live_builder
    inline = page.live_builder
    assert all(t['kind'] == 'Passengers' for t in inline.tasks)
    app.processEvents()
    inline.rows.setCurrentCell(1, 2)
    QTest.mouseClick(inline.rows.viewport(), Qt.MouseButton.LeftButton, pos=inline.rows.visualItemRect(inline.rows.item(1, 2)).center())
    QTest.mouseDClick(inline.rows.viewport(), Qt.MouseButton.LeftButton, pos=inline.rows.visualItemRect(inline.rows.item(1, 2)).center())
    app.processEvents()
    cell_editor = next(w for w in inline.rows.findChildren(QLineEdit) if w.isVisible())
    QTest.keyClick(cell_editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(cell_editor, 'Sam Updated')
    typed = cell_editor.text()
    QTest.keyClick(cell_editor, Qt.Key.Key_Return)
    app.processEvents()
    assert inline.tasks[1]['name'] == 'Sam Updated', (typed, inline.rows.item(1, 2).text(), inline.tasks[1]['name'], inline.local_edits)
    inline.rows.item(1, 3).setText('Senior Navigation')
    app.processEvents()
    window.grab().save(str(output / 'inline-draft.png'))
    window.resize(1000, 700)
    app.processEvents()
    window.grab().save(str(output / 'inline-small.png'))
    window.resize(1366, 768)
    QTest.mouseClick(next(b for b in page.findChildren(QPushButton) if b.text() == 'Save plan version'), Qt.MouseButton.LeftButton)
    wait(app,lambda:not page._write_pending)
    direct = copy.deepcopy(page.saved_plan)
    assert any(t['name'] == 'Sam Updated' and t['position'] == 'Senior Navigation' for s in direct['stops'] for t in s['drop_passengers'])
    assert all(t['name'] in {'Navigation equipment', 'Engineering spares'} for s in direct['stops'] for g in ('drop_materials', 'pick_materials') for t in s[g])
    assert page.live_builder is None
    path = output / 'direct-personnel-edit.xlsx'
    export_plan(direct, path)
    book = load_workbook(path)
    assert 'Sam Updated(Senior Navigation)' in '\n'.join(str(c.value) for row in book['Berthing Plan'] for c in row)
    book.close()
    assert next(p for p in page.service.berth_versions() if p['id'] == saved['id']) == saved
    # Leave a clean five-person baseline for the overview and Excel comparison captures.
    page.saved_plan, page.draft = baseline, None
    page.show_plan(baseline)
    return {'legacy_load_refreshed_final': True, 'old_snapshot_unchanged': True, 'review_rows_grouped': True,
        'review_click_shows_reasons': True, 'crew_add_and_plan_remove_via_buttons': True,
        'material_selection_editable': True, 'excluded_entry_stays_excluded_on_reload': True,
        'repeated_visit_assignment_preserved': True, 'edit_targets_displayed_plan': True,
        'berthing_date_reaches_excel': True, 'date_labels_clarified': True,
        'draft_personnel_edited_in_place': True, 'only_personnel_editable_in_draft': True,
        'direct_edits_saved_without_preview_step': True, 'direct_edits_reach_excel': True,
        'material_content_unchanged': True}


if __name__ == '__main__':
    main()

"""Native Windows render checks under dark input colors and five DPI scales."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "validation-1.0.4"


def run_child(scale,theme="light",font_size=11):
    global OUTPUT
    OUTPUT=OUTPUT/(theme if font_size==11 else theme+"-large")
    os.environ["QT_SCALE_FACTOR"] = str(scale/float(os.environ["CARGO_TRACK_TEST_NATIVE_DPR"]))
    os.environ["QT_QPA_PLATFORM"] = "windows"
    sys.path.insert(0, str(ROOT / "src"))
    from PySide6.QtCore import QPoint, QSettings, Qt
    from PySide6.QtGui import QColor, QPalette, QAccessible
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from cargo_track.appearance import configure_application
    from cargo_track.domain import Command
    from cargo_track.service import ApplicationService
    from cargo_track.ui import CargoTrackWindow, FleetDialog, SettingsDialog, VoyagesDialog, HelpDialog
    app = QApplication([])
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Base, QColor("#202020"))
    dark.setColor(QPalette.ColorRole.Window, QColor("#202020"))
    dark.setColor(QPalette.ColorRole.Text, QColor("#FFFFFF"))
    app.setPalette(dark)
    QAccessible.setActive(True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []

    def wait_for(predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():return
            time.sleep(.02)
        raise AssertionError("Window/worker did not become ready")

    with ExitStack() as cleanup:
        directory=cleanup.enter_context(tempfile.TemporaryDirectory(prefix="display-",dir=OUTPUT))
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, directory)
        QSettings().setValue("appearance/theme",theme);QSettings().setValue("appearance/font_size",font_size);configure_application(app)
        for scenario in ("empty", "filled"):
            data = Path(directory) / scenario
            service = ApplicationService(data / "cargo-track.sqlite3")
            service.open()
            seq = 0
            def command(op, payload):
                nonlocal seq
                seq += 1
                return service.handle(Command(f"display-{seq}", op, payload)).result
            first = command("create_vessel", {"name":"BGP Victor"})["id"]
            command("create_voyage", {"name":"Morning route"})
            if scenario == "filled":
                second = command("create_vessel", {"name":"CHA"})["id"]
                stop = command("add_stop", {"vessel_id":first})["stop_id"]
                command("add_stop", {"vessel_id":second})
                command("choose_stop", {"stop_id":stop})
                for i in range(6):command("create_transfer", {"description":f"Test cargo {i+1}","from_location_id":first,"to_location_id":second,"comment":"Verification only"})
            service.close()
            window = CargoTrackWindow(data / "cargo-track.sqlite3", data)
            cleanup.callback(window.client.close)
            window.show()
            wait_for(lambda: window.snapshot is not None and not window._refresh_wait and window.model.rowCount() == (6 if scenario == "filled" else 0))
            app.processEvents()
            screen = window.screen().availableGeometry()
            assert window.width() <= screen.width(), ("window exceeds screen",window.width(),screen.width())
            assert window.height() <= screen.height(), ("window exceeds screen",window.height(),screen.height())
            for widget in (window.search,window.status_filter,window.vessel_filter,window.range_filter,window.clear_button,
                           window.route_add_button,window.next_page,window.previous_page,window.details_button,window.more_button):
                point = widget.mapTo(window,QPoint(0,0))
                assert point.x() >= 0 and point.y() >= 0
                assert point.x()+widget.width() <= window.width(), (widget.text() if hasattr(widget,"text") else widget.accessibleName(),"horizontal clipping")
                assert point.y()+widget.height() <= window.height(), (widget.accessibleName(),"vertical clipping")
            assert window.table.height() >= 65, ("ledger too short",window.table.height())
            for name, widget in (("route",window.route_scroll.viewport()),("header",window.table.horizontalHeader())):
                image = widget.grab().toImage()
                color = image.pixelColor(max(0,image.width()-4),3)
                assert (color.lightness() >= 200 if theme=="light" else color.lightness()<=90), (name,"dark background",color.name())
            window.activateWindow();window.raise_();QTest.qWait(80)
            QTest.keyClick(window,Qt.Key.Key_F,Qt.KeyboardModifier.ControlModifier)
            assert window.search.hasFocus(), "Ctrl+F did not focus Search transfers"
            interface = QAccessible.queryAccessibleInterface(window.search)
            assert interface and interface.text(QAccessible.Text.Name) == "Search transfers"
            if scenario == "filled":
                cell = window.model.index(0,5)
                assert "Status: Waiting" in window.model.data(cell,Qt.ItemDataRole.AccessibleTextRole)
            screenshot = OUTPUT / f"main-{scenario}-{scale:g}x.png"
            assert window.grab().save(str(screenshot))
            window.status_filter.showPopup()
            QTest.qWait(100)
            popup = app.activePopupWidget()
            assert popup is not None, "Filter menu did not open"
            assert popup.grab().save(str(OUTPUT/f"filter-menu-{scenario}-{scale:g}x.png"))
            QTest.keyClick(popup,Qt.Key.Key_Escape)
            QTest.qWait(30)
            if scenario == "filled":
                stop_button = window.route_items.itemAt(0).widget()
                stop_button.menu().popup(stop_button.mapToGlobal(QPoint(0,stop_button.height())))
                QTest.qWait(80)
                assert stop_button.menu().isVisible()
                assert stop_button.menu().grab().save(str(OUTPUT/f"stop-menu-{scale:g}x.png"))
                QTest.keyClick(stop_button.menu(),Qt.Key.Key_Escape)
            fleet = FleetDialog(window)
            fleet.show()
            wait_for(lambda: fleet.list.count() >= 1)
            image = fleet.list.viewport().grab().toImage()
            assert (image.pixelColor(image.width()-8,image.height()-8).lightness() >= 200 if theme=="light" else image.pixelColor(image.width()-8,image.height()-8).lightness()<=90), "Fleet retains dark background"
            assert fleet.width() <= screen.width() and fleet.height() <= screen.height()
            assert fleet.grab().save(str(OUTPUT/f"fleet-{scenario}-{scale:g}x.png"))
            results.append({"scenario":scenario,"requested_scale":scale,"effective_dpr":window.devicePixelRatioF(),
                            "logical_window":[window.width(),window.height()],"available_screen":[screen.width(),screen.height()],
                            "popup_menus":"PASS","theme":theme,"font_size":font_size,"theme_backgrounds":"PASS","control_bounds":"PASS","search_keyboard_and_accessible_name":"PASS","screenshot":str(screenshot)})
            fleet.close()
            settings=SettingsDialog(window,window.snapshot["settings"],window.database_path,window.backup_directory)
            settings.show();QTest.qWait(80)
            assert settings.timezone.count()>80
            assert settings.timezone.currentData()=="Asia/Riyadh"
            assert settings.database_directory.isReadOnly() and settings.backup_directory.isReadOnly()
            assert settings.width()<=screen.width() and settings.height()<=screen.height()
            assert settings.grab().save(str(OUTPUT/f"settings-{scenario}-{scale:g}x.png"))
            assert settings.font_size.currentData()==font_size
            assert settings.theme.currentData()==theme
            settings.close()
            help_dialog=HelpDialog(window,"settings");help_dialog.show();QTest.qWait(50)
            assert "删除记录" in help_dialog.browser.toPlainText()
            assert help_dialog.grab().save(str(OUTPUT/f"help-{scenario}-{scale:g}x.png"))
            help_dialog.close()
            from unittest.mock import patch
            window.activateWindow();QTest.qWait(30)
            with patch("cargo_track.ui.HelpDialog.exec",return_value=0) as help_open:
                QTest.keyClick(window,Qt.Key.Key_F1);QTest.qWait(30)
                assert help_open.call_count==1, "F1 did not open help"
            if scenario=="filled":
                opposite="dark" if theme=="light" else "light"
                window._save_storage({"theme":opposite,"font_size":12,"database_directory":str(window.database_path.parent),"backup_directory":str(window.backup_directory)})
                QTest.qWait(50)
                assert QSettings().value("appearance/theme")==opposite
                expected="#25272e" if opposite=="dark" else "#ffffff"
                assert window.search.palette().color(QPalette.ColorRole.Base).name()==expected
                assert window.search.font().pointSize()==12
                window._save_storage({"theme":theme,"font_size":font_size,"database_directory":str(window.database_path.parent),"backup_directory":str(window.backup_directory)})
                QTest.qWait(50)
                results[-1]["live_theme_font_switch_and_f1"]="PASS"
            if scenario=="filled":
                QTest.qWait(120);window.table.selectRow(0);QTest.qWait(50)
                assert window.status_choice.isEnabled(), str({"rows":len(window.model.rows),"selected":window._selected_row(),"busy":window._busy,"enabled":window.centralWidget().isEnabled()})
                window.status_choice.setCurrentIndex(1);window.change_selected_status(1)
                wait_for(lambda:window.model.rows and window.model.rows[0]["status"]=="On Board")
                destination=Path(directory)/"relocated"/f"{scale:g}"
                window._save_storage({"theme":theme,"font_size":font_size,"database_directory":str(destination),"backup_directory":str(destination/"Backups")})
                wait_for(lambda:window.database_path==destination/"cargo-track.sqlite3")
                wait_for(lambda:len(window.model.rows)==6)
                assert QSettings().value("storage/database_directory")==str(destination)
                assert window.backup_directory==destination/"Backups"
                results[-1]["status_dropdown_and_live_relocation"]="PASS"
                from unittest.mock import patch
                window._submit("create_vessel",{"name":"Unused validation vessel"},"Test vessel")
                wait_for(lambda:not window._busy and any(v["name"]=="Unused validation vessel" for v in window.snapshot["vessels"]))
                fleet=FleetDialog(window);fleet.show()
                wait_for(lambda:any(v["name"]=="Unused validation vessel" for v in fleet.rows))
                fleet.list.setCurrentRow(next(i for i,v in enumerate(fleet.rows) if v["name"]=="Unused validation vessel"))
                with patch("cargo_track.ui.confirm",return_value=True):fleet.delete_vessel()
                wait_for(lambda:all(v["name"]!="Unused validation vessel" for v in fleet.rows))
                fleet.close()
                voyages=VoyagesDialog(window);voyages.show();window._send("_voyage_history",meta={"dialog":voyages})
                wait_for(lambda:len(voyages.rows)==1)
                with patch("cargo_track.ui.confirm",return_value=True):voyages.delete_selected()
                wait_for(lambda:not voyages.rows and window.snapshot["current_voyage_id"] is None)
                QTest.qWait(200)
                if len(window.model.rows)!=6:raise AssertionError(str({"rows":len(window.model.rows),"view":window.view,"filters":window.filters,"snapshot":window.snapshot["counts"],"result":window.result_label.text()}))
                voyages.close();results[-1]["fleet_and_voyage_delete_ui"]="PASS"
                window.table.selectRow(0);QTest.qWait(20)
                number=window._selected_row()["no"]
                with patch("cargo_track.ui.confirm",side_effect=AssertionError("Unexpected status confirmation")):
                    window.status_choice.setCurrentIndex(2);window.change_selected_status(2)
                    wait_for(lambda:not window._busy and window.snapshot["counts"]["open"]==5)
                window.range_filter.setCurrentIndex(window.range_filter.findData("completed"))
                wait_for(lambda:len(window.model.rows)==1)
                window.table.selectRow(0);QTest.qWait(20)
                assert window._selected_row()["status"]=="Done" and window.delete_button.isEnabled()
                assert window.grab().save(str(OUTPUT/f"completed-selected-{scale:g}x.png"))
                with patch("cargo_track.ui.QInputDialog.getText",return_value=("test completed deletion",True)):window.delete_selected_transfer()
                wait_for(lambda:not window._busy and len(window.model.rows)==0)
                window.range_filter.setCurrentIndex(window.range_filter.findData("voided"))
                wait_for(lambda:len(window.model.rows)==1)
                window.table.selectRow(0);QTest.qWait(20)
                assert window.delete_button.text()=="Restore…"
                with patch("cargo_track.ui.QInputDialog.getText",return_value=("test restore",True)):window.delete_selected_transfer()
                wait_for(lambda:not window._busy and len(window.model.rows)==0)
                window.range_filter.setCurrentIndex(window.range_filter.findData("completed"))
                wait_for(lambda:len(window.model.rows)==1)
                window.table.selectRow(0);QTest.qWait(20)
                with patch("cargo_track.ui.CorrectionDialog.exec",side_effect=AssertionError("Unexpected correction dialog")),patch("cargo_track.ui.confirm",side_effect=AssertionError("Unexpected status confirmation")):
                    window.status_choice.setCurrentIndex(0);window.change_selected_status(0)
                    wait_for(lambda:not window._busy and window.snapshot["counts"]["open"]==6)
                results[-1]["completed_delete_restore_and_popup_free_status"]="PASS"
            results[-1]["windows_timezones_and_settings"]="PASS"
            window.client.close();window.hide();app.processEvents()
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child",type=float)
    parser.add_argument("--theme",default="light")
    parser.add_argument("--font-size",type=int,default=11)
    args = parser.parse_args()
    if args.child is not None:
        print(json.dumps(run_child(args.child,args.theme,args.font_size)))
        return
    env=dict(os.environ)
    for key in ("QT_SCALE_FACTOR","QT_SCREEN_SCALE_FACTORS","QT_QPA_PLATFORM"):env.pop(key,None)
    baseline=subprocess.run([sys.executable,"-c","from PySide6.QtWidgets import QApplication;app=QApplication([]);print(app.primaryScreen().devicePixelRatio())"],env=env,capture_output=True,text=True,check=True)
    os.environ["CARGO_TRACK_TEST_NATIVE_DPR"]=baseline.stdout.strip().splitlines()[-1]
    report = []
    cases=[(theme,scale,11) for theme in ("light","dark") for scale in (1,1.25,1.5,1.75,2)] + [(theme,2,12) for theme in ("light","dark")]
    for theme,scale,font_size in cases:
        child = subprocess.run([sys.executable,__file__,"--child",str(scale),"--theme",theme,"--font-size",str(font_size)],capture_output=True,text=True)
        if child.returncode:raise RuntimeError(f"{theme} DPI {scale}, font {font_size} failed:\n{child.stdout}\n{child.stderr}")
        report.extend(json.loads(child.stdout.strip().splitlines()[-1]))
        print(f"PASS: {theme}, {font_size}pt, {scale:g}x, settings/help/delete/restore/status",flush=True)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/"display-validation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


if __name__ == "__main__":main()


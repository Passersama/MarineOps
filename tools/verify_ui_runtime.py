"""Launch the real Qt window offscreen, exercise one action and save a preview."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from cargo_track.domain import Command
from cargo_track.appearance import configure_application
from cargo_track.service import ApplicationService
from cargo_track.ui import CargoTrackWindow


def wait_for(app, predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.025)
    return False


def main() -> int:
    app = QApplication([])
    configure_application(app)
    with tempfile.TemporaryDirectory(prefix="cargo-track-ui-") as directory:
        data = Path(directory)
        service = ApplicationService(data / "ledger.sqlite3")
        service.open()
        sequence = 0

        def command(operation, payload):
            nonlocal sequence
            sequence += 1
            return service.handle(Command(f"smoke-{sequence}", operation, payload)).result

        shore = service.workspace_snapshot()["shore_location_id"]
        first = command("create_vessel", {"name": "BVC"})["id"]
        second = command("create_vessel", {"name": "CHA"})["id"]
        command("create_voyage", {"name": "Morning route"})
        stop = command("add_stop", {"vessel_id": first})["stop_id"]
        command("add_stop", {"vessel_id": second})
        command("choose_stop", {"stop_id": stop})
        for index, (description, source, target) in enumerate((
            ("Hydraulic pump", first, second),
            ("Control panel", first, shore),
            ("Cable drums", second, first),
            ("Tool cases", first, second),
            ("Filters", second, shore),
            ("Sensor kit", first, second),
        ), 1):
            command("create_transfer", {
                "description": description, "from_location_id": source,
                "to_location_id": target, "physical_id": f"CT-{index:03}", "comment": "",
            })
        service.close()

        window = CargoTrackWindow(data / "ledger.sqlite3", data)
        window.show()
        if not wait_for(app, lambda: window.model.rowCount() == 6 and not window._refresh_wait):
            window.client.close()
            raise RuntimeError("The Qt window did not load the seeded transfer rows.")
        if len(window.snapshot["stops"]) != 2 or window.snapshot["current_stop_id"] != stop:
            window.client.close()
            raise RuntimeError("The voyage and selected stop did not load into the real window.")

        preview = ROOT / "CargoTrack-UI-runtime.png"
        if not window.grab().save(str(preview)):
            window.client.close()
            raise RuntimeError("Qt could not save the runtime preview image.")

        row = window.model.row_at(0)
        number = row["no"]
        window._submit("pick_up", {"no": number, "expected_version": row["version"]}, "Smoke pickup saved.")
        if not wait_for(app, lambda: not window._busy and window.model.row_at(0)["status"] == "On Board"):
            window.client.close()
            raise RuntimeError("The worker did not complete and refresh the real pickup action.")
        window.client.close()
        if window.client.thread.isRunning():
            raise RuntimeError("The database worker did not stop cleanly.")
        print(f"PASS: real Qt window loaded 6 transfers; pickup #{number} saved and refreshed; screenshot={preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

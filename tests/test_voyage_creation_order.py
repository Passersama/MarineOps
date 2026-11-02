import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from PySide6.QtWidgets import QApplication
from cargo_track.domain import AppError, Command
from cargo_track.service import ApplicationService
from cargo_track.ui import NewVoyageDialog


class VoyageCreationOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = ApplicationService(Path(self.temp.name) / "cargo.sqlite3")
        self.service.open()

    def tearDown(self):
        self.service.close(); self.temp.cleanup()

    def command(self, operation, payload):
        return self.service.handle(Command(str(uuid4()), operation, payload)).result

    def test_create_order_repeated_visits_and_rollback(self):
        a = self.command("create_vessel", {"name": "Alpha"})["id"]
        b = self.command("create_vessel", {"name": "Beta"})["id"]
        old = self.command("create_voyage", {"name": "Old"})["voyage_id"]
        with self.assertRaises(AppError):
            self.command("create_voyage", {"name": "Invalid", "location_ids": [a, -1]})
        self.assertEqual(old, self.service.workspace_snapshot()["current_voyage_id"])
        self.command("create_voyage", {"name": "New", "location_ids": [a, b, a]})
        snap = self.service.workspace_snapshot()
        self.assertEqual([a,b,a], [s["vessel_id"] for s in snap["stops"]])
        self.assertEqual(3, len({s["id"] for s in snap["stops"]}))
        self.assertIsNone(snap["current_stop_id"])

    def test_failure_after_first_insert_rolls_back_voyage_and_cargo(self):
        a = self.command("create_vessel", {"name": "Alpha"})["id"]
        b = self.command("create_vessel", {"name": "Beta"})["id"]
        old = self.command("create_voyage", {"name": "Old", "location_ids": [a]})["voyage_id"]
        old_stop = self.service.workspace_snapshot()["stops"][0]["id"]
        self.command("choose_stop", {"stop_id": old_stop})
        cargo = self.command("create_transfer", {"description":"Crate", "from_location_id":a, "to_location_id":b})
        before = self.service.transfer_detail(cargo["no"])["row"]
        self.service.db.execute("CREATE TEMP TRIGGER fail_second_stop BEFORE INSERT ON voyage_stops WHEN NEW.position=2 BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(AppError):
            self.command("create_voyage", {"name":"Failed", "location_ids":[a,b]})
        snap = self.service.workspace_snapshot()
        self.assertEqual((old,old_stop), (snap["current_voyage_id"],snap["current_stop_id"]))
        self.assertEqual([old_stop], [s["id"] for s in snap["stops"]])
        self.assertEqual(before, self.service.transfer_detail(cargo["no"])["row"])
        self.assertEqual(["Old"], [v["name"] for v in self.service.voyage_history()])
        self.assertEqual("ok", self.service.db.execute("PRAGMA integrity_check").fetchone()[0])

    def test_stale_creation_cannot_replace_newer_voyage(self):
        a = self.command("create_vessel", {"name": "Alpha"})["id"]
        initial = self.service.workspace_snapshot()
        current = self.command("create_voyage", {"name": "Other"})["voyage_id"]
        with self.assertRaises(AppError) as caught:
            self.command("create_voyage", {"name": "Stale", "location_ids": [a],
                "expected_epoch": initial["dataset_epoch"], "expected_revision": initial["revision"]})
        self.assertEqual("ROUTE_CONFLICT", caught.exception.code)
        self.assertEqual(current, self.service.workspace_snapshot()["current_voyage_id"])
        self.assertEqual(["Other"], [v["name"] for v in self.service.voyage_history()])

    def test_dialog_orders_visits(self):
        a = self.command("create_vessel", {"name": "Alpha"})["id"]
        b = self.command("create_vessel", {"name": "Beta"})["id"]
        dialog = NewVoyageDialog(None, self.service.workspace_snapshot()["locations"])
        dialog.name.setText("Trip")
        for identifier in (a,b,a):
            dialog.locations.setCurrentIndex(dialog.locations.findData(identifier));dialog.add_stop()
        dialog.move_stop(-1)
        self.assertEqual([a,a,b], dialog.payload()["location_ids"])
        dialog.close()

if __name__ == "__main__": unittest.main()

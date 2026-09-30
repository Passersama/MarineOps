from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from cargo_track.domain import AppError, Command
from cargo_track.service import ApplicationService
from cargo_track.schema import check_integrity


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = ApplicationService(self.root / "ledger.sqlite3")
        self.service.open()
        self.counter = 0

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def command(self, operation, payload, command_id=None):
        self.counter += 1
        return self.service.handle(Command(command_id or f"test-{self.counter}", operation, payload))

    def vessel(self, name):
        return self.command("create_vessel", {"name": name}).result["id"]

    def transfer(self, description="Crate", source=None, destination=None):
        shore = self.service.workspace_snapshot()["shore_location_id"]
        return self.command("create_transfer", {
            "description": description,
            "from_location_id": source or shore,
            "to_location_id": destination or shore,
            "physical_id": "",
            "comment": "",
        }).result

    def test_idempotent_command_and_reused_id_protection(self):
        result = self.command("create_vessel", {"name": "North Star"}, "same-id")
        repeated = self.command("create_vessel", {"name": "North Star"}, "same-id")
        self.assertEqual(result.result, repeated.result)
        self.assertEqual(1, len(self.service.list_vessels()))
        with self.assertRaises(AppError) as caught:
            self.service.handle(Command("same-id", "create_vessel", {"name": "Different"}))
        self.assertEqual("COMMAND_ID_REUSED", caught.exception.code)

    def test_status_transitions_require_physical_confirmation_and_set_local_date(self):
        ship = self.vessel("Al Noor")
        result = self.transfer(source=ship)
        with self.assertRaises(AppError) as caught:
            self.command("pick_up", {"no": result["no"], "expected_version": 0})
        self.assertEqual("LOCATION_CONFIRMATION_REQUIRED", caught.exception.code)
        self.command("pick_up", {"no": result["no"], "expected_version": 0, "confirmed_location": True})
        delivered = self.command("deliver", {"no": result["no"], "expected_version": 1, "confirmed_location": True})
        self.assertEqual("Done", delivered.result["status"])
        self.assertRegex(delivered.result["completed_date"], r"^\d{8}$")

    def test_following_segment_requires_delivery_and_route_reason_for_discontinuity(self):
        first, second, third = self.vessel("A"), self.vessel("B"), self.vessel("C")
        created = self.transfer(source=first, destination=second)
        with self.assertRaises(AppError) as caught:
            self.command("create_transfer", {"cargo_id": created["cargo_id"], "description": "Next", "from_location_id": second, "to_location_id": third})
        self.assertEqual("PREDECESSOR_NOT_DONE", caught.exception.code)
        self.command("pick_up", {"no": created["no"], "expected_version": 0, "confirmed_location": True})
        self.command("deliver", {"no": created["no"], "expected_version": 1, "confirmed_location": True})
        with self.assertRaises(AppError) as caught:
            self.command("create_transfer", {"cargo_id": created["cargo_id"], "description": "Next", "from_location_id": first, "to_location_id": third})
        self.assertEqual("ROUTE_DISCONTINUITY", caught.exception.code)
        following = self.command("create_transfer", {"cargo_id": created["cargo_id"], "description": "Next", "from_location_id": first, "to_location_id": third, "route_reason": "Cargo moved ashore between legs"})
        self.assertEqual(created["no"], self.service.transfer_detail(following.result["no"])["row"]["predecessor_no"])

    def test_on_board_transfer_cannot_be_voided_and_audit_is_immutable(self):
        result = self.transfer()
        self.command("pick_up", {"no": result["no"], "expected_version": 0, "confirmed_location": True})
        with self.assertRaises(AppError) as caught:
            self.command("void_transfer", {"no": result["no"], "expected_version": 1, "reason": "wrong"})
        self.assertEqual("ON_BOARD_MUST_BE_RESOLVED", caught.exception.code)
        with self.assertRaises(Exception):
            self.service.db.execute("UPDATE audit_events SET reason='changed' WHERE id=1")

    def test_voyage_history_is_read_only_and_can_be_copied(self):
        ship_a, ship_b = self.vessel("Route A"), self.vessel("Route B")
        self.command("create_voyage", {"name": "Spring"})
        self.command("add_stop", {"vessel_id": ship_a})
        self.command("add_stop", {"vessel_id": ship_b})
        snapshot = self.service.workspace_snapshot()
        ids = [row["id"] for row in snapshot["stops"]]
        self.command("choose_stop", {"stop_id": ids[0]})
        self.command("reorder_stops", {"stop_ids": ids[::-1]})
        old_id = snapshot["current_voyage_id"]
        self.command("create_voyage", {"name": "Summer"})
        with self.assertRaises(AppError) as caught:
            self.command("set_current_voyage", {"voyage_id": old_id})
        self.assertEqual("VOYAGE_ARCHIVED", caught.exception.code)
        self.command("copy_voyage", {"name": "Spring copy", "voyage_id": old_id})
        route = self.service.workspace_snapshot()["stops"]
        self.assertEqual(["Route B", "Route A"], [row["vessel_name_snapshot"] for row in route])
        self.assertTrue(next(row for row in self.service.voyage_history() if row["id"] == old_id)["archived"])

    def test_export_escapes_formula_text_and_backup_restore_is_validated(self):
        row = self.transfer(description="=1+1")
        csv_path = self.root / "ledger.csv"
        self.service.export_to(csv_path, "all", {"range": "all"}, "csv", True)
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            lines = list(csv.reader(stream))
        self.assertEqual("'=1+1", lines[1][2])
        backup = self.root / "backup.sqlite3"
        self.service.create_backup(backup)
        self.transfer(description="second")
        preview = self.service.inspect_backup(backup)
        self.assertEqual(1, preview["counts"]["transfer_legs"])
        restored = self.service.restore_backup(backup)
        self.assertEqual(1, restored["counts"]["transfer_legs"])
        self.assertEqual(1, self.service.workspace_snapshot()["counts"]["all"])
        self.assertTrue(Path(restored["safety_copy"]).is_file())
        self.assertEqual([], check_integrity(str(self.root / "ledger.sqlite3")))

    def test_ten_thousand_completed_transfers_can_be_queried_and_exported(self):
        import time
        shore = self.service.workspace_snapshot()["shore_location_id"]
        now = "2026-09-30T12:00:00+00:00"
        self.service.db.execute("BEGIN")
        try:
            self.service.db.executemany(
                "INSERT INTO cargo(cargo_tag,default_description,physical_id,created_utc,updated_utc) VALUES(?,?,?,?,?)",
                ((f"C-{number:06d}", f"Historical cargo {number}", None, now, now) for number in range(1, 10001)),
            )
            self.service.db.executemany("""INSERT INTO transfer_legs(cargo_id,predecessor_no,from_location_id,from_name_snapshot,
                to_location_id,to_name_snapshot,description,comment,status,is_void,version,created_utc,updated_utc,
                completed_utc,completed_date,completed_tz) VALUES(?,NULL,?,'On Shore',?,'On Shore',?,'','Done',0,0,?,?,?,'20260930','Asia/Riyadh')""",
                ((number, shore, shore, f"Historical cargo {number}", now, now, now) for number in range(1, 10001)),
            )
            self.service.db.commit()
        except Exception:
            self.service.db.rollback()
            raise
        started = time.monotonic()
        results = self.service.query_transfers("all", {"range": "completed"}, limit=200)
        exported = self.service.export_rows("all", {"range": "completed"}, True)
        elapsed = time.monotonic() - started
        self.assertEqual(10000, results["total"])
        self.assertEqual(200, len(results["rows"]))
        self.assertEqual(10000, len(exported))
        self.assertLess(elapsed, 15, f"10,000-row query and export took {elapsed:.1f}s")

    def test_newer_schema_is_rejected_without_schema_mutation(self):
        self.service.close()
        import sqlite3
        path = self.root / "future.sqlite3"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE schema_meta(id INTEGER PRIMARY KEY, version INTEGER NOT NULL)")
        db.execute("INSERT INTO schema_meta VALUES(1, 99)")
        db.commit(); db.close()
        other = ApplicationService(path)
        with self.assertRaises(Exception):
            other.open()
        conn = sqlite3.connect(path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertEqual({"schema_meta"}, tables)

    def test_unreadable_backup_is_rejected_without_touching_current_ledger(self):
        original = self.transfer(description="Keep this cargo")
        broken = self.root / "not-a-database.sqlite3"
        broken.write_bytes(b"not a sqlite database")
        with self.assertRaises(AppError) as caught:
            self.service.inspect_backup(broken)
        self.assertEqual("BACKUP_INVALID", caught.exception.code)
        self.assertEqual(1, self.service.workspace_snapshot()["counts"]["all"])
        self.assertEqual(original["no"], self.service.query_transfers("all", {"range": "open"})["rows"][0]["no"])


if __name__ == "__main__":
    unittest.main()

import tempfile,unittest,sqlite3
from pathlib import Path
from unittest.mock import patch
from cargo_track.service import ApplicationService
from cargo_track.domain import Command,AppError

class SettingsDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.service=ApplicationService(self.root/"original.sqlite3");self.service.open();self.counter=0
    def tearDown(self):self.service.close();self.temp.cleanup()
    def cmd(self,op,p):
        self.counter+=1;return self.service.handle(Command(str(self.counter),op,p)).result
    def test_current_voyage_delete_clears_state_and_retains_audit_and_cargo(self):
        vessel=self.cmd("create_vessel",{"name":"Victor"})["id"]
        voyage=self.cmd("create_voyage",{"name":"Route"})["voyage_id"]
        self.cmd("add_stop",{"vessel_id":vessel})
        self.cmd("delete_voyage",{"voyage_id":voyage})
        state=self.service.workspace_snapshot();self.assertIsNone(state["current_voyage_id"]);self.assertIsNone(state["current_stop_id"]);self.assertEqual(self.service.voyage_history(),[])
        self.assertEqual(self.service.db.execute("SELECT count(*) FROM voyage_stops").fetchone()[0],1)
        with self.assertRaises(AppError):self.cmd("copy_voyage",{"voyage_id":voyage,"name":"Copy"})
    def test_historical_voyage_delete_and_deleted_vessel_name_reuse(self):
        v=self.cmd("create_voyage",{"name":"Old"})["voyage_id"];self.cmd("create_voyage",{"name":"New"});self.cmd("delete_voyage",{"voyage_id":v});self.assertEqual(len(self.service.voyage_history()),1)
        vessel=self.cmd("create_vessel",{"name":"Victor"})["id"];self.cmd("delete_vessel",{"id":vessel});self.assertEqual(self.service.list_vessels(),[])
        self.assertNotEqual(self.cmd("create_vessel",{"name":"Victor"})["id"],vessel)
        with self.assertRaises(AppError):self.cmd("set_vessel_active",{"id":vessel,"active":True})
    def test_vessel_in_current_route_cannot_be_deleted(self):
        vessel=self.cmd("create_vessel",{"name":"Victor"})["id"];self.cmd("create_voyage",{"name":"Route"});self.cmd("add_stop",{"vessel_id":vessel})
        with self.assertRaises(AppError):self.cmd("delete_vessel",{"id":vessel})
        self.assertEqual(len(self.service.list_vessels()),1)
    def test_relocation_retains_records_and_original_and_refuses_existing(self):
        self.cmd("create_vessel",{"name":"Victor"});target=self.root/"moved"/"cargo-track.sqlite3";new=self.service.relocated_service(target)
        try:self.assertEqual(len(new.list_vessels()),1);self.assertTrue(self.service.path.exists());self.assertNotEqual(new.dataset_epoch,self.service.dataset_epoch)
        finally:new.close()
        before=target.read_bytes()
        with self.assertRaises(AppError):self.service.relocated_service(target)
        self.assertEqual(before,target.read_bytes())
    def test_relocation_open_failure_keeps_original_usable(self):
        self.cmd("create_vessel",{"name":"Victor"});target=self.root/"moved.sqlite3"
        with patch.object(ApplicationService,"open",side_effect=OSError("injected open failure")):
            with self.assertRaises(OSError):self.service.relocated_service(target)
        self.assertFalse(target.exists());self.assertEqual(len(self.service.list_vessels()),1)

    def test_vessel_with_unfinished_transfer_is_protected_and_done_history_survives(self):
        vessel=self.cmd("create_vessel",{"name":"Victor"})["id"];shore=self.service.workspace_snapshot()["shore_location_id"]
        no=self.cmd("create_transfer",{"description":"Box","from_location_id":vessel,"to_location_id":shore})["no"]
        with self.assertRaises(AppError):self.cmd("delete_vessel",{"id":vessel})
        row=self.service.transfer_detail(no)["row"];self.cmd("pick_up",{"no":no,"expected_version":row["version"],"confirmed_location":True})
        row=self.service.transfer_detail(no)["row"];self.cmd("deliver",{"no":no,"expected_version":row["version"],"confirmed_location":True})
        self.cmd("delete_vessel",{"id":vessel});detail=self.service.transfer_detail(no)
        self.assertEqual(detail["row"]["from_name"],"Victor");self.assertEqual(detail["row"]["status"],"Done")
        self.service.close();self.service.open();self.assertEqual(self.service.list_vessels(),[])
    def test_relocation_backup_failure_leaves_no_destination(self):
        target=self.root/"moved.sqlite3"
        with patch.object(self.service,"create_backup",side_effect=OSError("disk full")):
            with self.assertRaises(OSError):self.service.relocated_service(target)
        self.assertFalse(target.exists());self.assertIsNotNone(self.service.connection)

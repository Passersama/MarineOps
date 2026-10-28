"""Reproduce saved plans becoming blank after executing their selected Cargo."""
import copy
import unittest
from unittest.mock import patch

from cargo_track.berth_plan import generate_plan
from cargo_track.personnel_cargo import read_cargo
from cargo_track.coordination import workspace_files
import test_dashboard as fixtures


class DashboardCargoIndependenceTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.DashboardTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def save(self,legacy=False):
        source=self.f.personnel.planning_source(read_cargo(self.f.cargo.path))
        plan=generate_plan(source,self.f.personnel.crew_records(self.f.list_id,source),[2],
                           '2026-10-12',self.f.personnel.port_name(source),mode='Final',personnel_plan_id=self.f.list_id)
        plan['personnel_context']=self.f.personnel.context(self.f.list_id)
        if legacy:
            plan.pop('personnel_dependencies');plan.pop('personnel_dependency_hash')
        self.assertFalse(plan['issues']);self.saved=self.f.personnel.save_berth(plan,True)
        return self.saved
    def pickup(self):self.f.command('pick_up',{'no':2,'expected_version':0,'confirmed_location':True})
    def ready(self):
        value=self.f.read()['personnel'];self.assertEqual('ready',value['status'],value['message'])
        self.assertEqual((3,2),(value['boarding'],value['leaving']));return value
    def test_selected_cargo_pickup_and_delivery_do_not_hide_personnel(self):
        self.save();self.pickup();self.ready()
        self.f.command('deliver',{'no':2,'expected_version':1,'confirmed_location':True});self.ready()
    def test_existing_plan_before_separate_fingerprints_is_supported_read_only(self):
        self.save(legacy=True);self.pickup()
        paths=(self.f.cargo.path,self.f.personnel.path);before=[p.read_bytes() for p in paths]
        self.ready();self.assertEqual(before,[p.read_bytes() for p in paths])
    def test_legacy_cargo_progress_and_roster_change_refresh_current_crew(self):
        self.save(legacy=True);self.pickup();row=self.f.personnel.passenger(self.f.ids[0])
        with patch.object(self.f.personnel,'_sync_crew_plans'):
            self.f.personnel.edit_crew_entry(row['id'],{**row,'position':'Updated role'},row['version'])
        result=self.ready();self.assertEqual('Updated Role',next(r['position'] for r in result['rows'] if r['task_id']==row['id']))
    def test_crew_write_after_cargo_progress_saves_new_current_version(self):
        self.save(legacy=True);self.pickup();row=self.f.personnel.passenger(self.f.ids[0])
        self.f.personnel.edit_crew_entry(row['id'],{**row,'position':'Updated role'},row['version'])
        latest=self.f.personnel.latest_berth(self.saved['family_id'])
        self.assertEqual(2,latest['version']);self.assertIn('personnel_dependency_hash',latest)
        self.assertEqual(latest['id'],self.ready()['selected_id'])
    def test_route_change_still_blocks_personnel_in_new_and_legacy_plans(self):
        self.save();legacy=copy.deepcopy(self.saved);legacy.pop('personnel_dependencies');legacy.pop('personnel_dependency_hash')
        self.f.command('add_stop',{'vessel_id':self.f.vessels['HB6']})
        from cargo_track.personnel_cargo import crew_source_matches
        source=read_cargo(self.f.cargo.path)
        for plan in (self.saved,legacy):self.assertFalse(crew_source_matches(plan,source))
        self.assertEqual('stale',self.f.read()['personnel']['status'])
    def test_missing_legacy_command_receipt_does_not_bypass_stale_check(self):
        self.save(legacy=True);self.pickup()
        self.f.cargo.db.execute('DELETE FROM command_receipts WHERE revision=?',(self.f.cargo.workspace_snapshot()['revision'],))
        self.assertEqual('stale',self.f.read()['personnel']['status'])
    def test_restore_generation_and_other_ledger_identity_still_block(self):
        self.save();self.pickup()
        from cargo_track.personnel_cargo import crew_source_matches
        source=read_cargo(self.f.cargo.path);source['ledger_identity']='another-ledger'
        self.assertFalse(crew_source_matches(self.saved,source))
        workspace_files.invalidate(self.f.cargo.path)
        self.assertEqual('stale',self.f.read()['personnel']['status'])
    def test_explicit_historical_version_does_not_silently_follow_roster(self):
        self.save(legacy=True);self.pickup();row=self.f.personnel.passenger(self.f.ids[0])
        with patch.object(self.f.personnel,'_sync_crew_plans'):
            self.f.personnel.edit_crew_entry(row['id'],{**row,'position':'Changed'},row['version'])
        self.assertEqual('stale',self.f.read(self.saved['id'])['personnel']['status'])

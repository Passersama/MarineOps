"""Data integrity and bounded-history regressions from the architecture audit."""
import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_personnel as fixtures
import test_frontend as frontend
from cargo_track.crew_plan_sync import refresh_crew_plan
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_import import PersonnelError
from cargo_track.plan_store import latest_family_payloads, version_summaries


class ArchitectureDataTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PersonnelTests();self.f.setUp()
        self.identifier=self.f.passenger()
    def tearDown(self):self.f.tearDown()
    def saved(self):
        plan=self.f.generate(mode='Final')
        plan['personnel_context']=self.f.service.context(self.f.plan)
        return self.f.service.save_berth(plan,True)
    def test_unexpected_cargo_exception_rolls_back_without_worker_help(self):
        before=self.f.cargo.workspace_snapshot()['revision']
        with patch.object(self.f.cargo,'_audit',side_effect=RuntimeError('Unexpected failure')):
            with self.assertRaises(RuntimeError):self.f.command('create_vessel',{'name':'Uncommitted vessel'})
        self.assertFalse(self.f.cargo.db.in_transaction)
        self.assertIsNone(self.f.cargo.db.execute("SELECT id FROM locations WHERE name='Uncommitted vessel'").fetchone())
        self.assertEqual(before,self.f.cargo.workspace_snapshot()['revision'])
        self.f.command('create_vessel',{'name':'Next operation works'})
    def test_metadata_transaction_does_not_scan_passenger_payloads(self):
        traced=[];self.f.service.db.set_trace_callback(traced.append)
        self.f.service.rename_plan(self.f.plan,'Renamed crew','Crew change')
        self.f.service.db.set_trace_callback(None)
        reads=[q.casefold() for q in traced if q.lstrip().casefold().startswith('select')]
        self.assertFalse(any('from passengers' in q for q in reads),reads)
    def test_payload_change_without_version_change_is_still_tracked(self):
        original=self.saved();record=self.f.service.passenger(self.identifier)
        data={k:v for k,v in record.items() if k in __import__('cargo_track.personnel_service',fromlist=['FIELDS']).FIELDS}
        data['position']='Chief Engineer'
        with self.f.service.atomic():
            self.f.service.db.execute('UPDATE passengers SET payload=? WHERE id=?',(json.dumps(data),self.identifier))
        latest=self.f.service.latest_berth(original['family_id'])
        self.assertEqual(2,latest['version'])
        self.assertEqual('Chief Engineer',next(t['position'] for s in latest['stops'] for t in s['drop_passengers']))
    def test_rolled_back_tracking_does_not_leak_to_next_transaction(self):
        with patch.object(self.f.service,'_sync_crew_plans',side_effect=RuntimeError('Failure')):
            with self.assertRaises(RuntimeError):
                self.f.service.edit_crew_entry(self.identifier,{**self.f.service.passenger(self.identifier),'position':'Failed'},0)
        other=self.f.service.create_plan('Unrelated list','2026-10-06')
        with patch.object(self.f.service,'_sync_crew_plans') as sync:
            self.f.service.add_passenger(other,self.f.record(name='Other person'))
        self.assertEqual({other},sync.call_args.args[0])
    def test_latest_family_is_version_order_even_when_clock_moves_backwards(self):
        first=self.saved()
        with patch('cargo_track.personnel_service.now',return_value='2001-01-01T00:00:00+00:00'):
            second=self.f.service.save_berth(self.f.generate(mode='Final'),False,first['family_id'])
        self.assertEqual(second['id'],latest_family_payloads(self.f.service.db,{self.f.plan})[0]['id'])
        self.f.service.clear_berth_history([second['id']])
        self.assertEqual(first['id'],latest_family_payloads(self.f.service.db,{self.f.plan})[0]['id'])
    def test_history_summaries_have_no_roster_payload_and_selection_decodes_one(self):
        first=self.saved()
        with patch('cargo_track.plan_store.json.loads',side_effect=AssertionError('Metadata must not decode snapshots')):
            summary=version_summaries(self.f.service.db)
        self.assertEqual(first['id'],summary[0]['id']);self.assertNotIn('stops',summary[0])
        with patch('cargo_track.plan_store.json.loads',wraps=json.loads) as decode:
            value=self.f.service.berth_version(first['id'])
        self.assertEqual(first,value);self.assertEqual(1,decode.call_count)
    def test_excluded_crew_does_not_add_unrequested_destination_call(self):
        original=self.saved()
        original['task_selections']={'Passengers:'+self.identifier:{'state':'user_excluded','reason':'Not on this trip'}}
        source=self.f.service.planning_source(self.f.snapshot)
        destination=self.f.command('create_vessel',{'name':'Excluded destination'})['id']
        from cargo_track.personnel_cargo import read_cargo
        source=read_cargo(self.f.cargo_path)
        people=self.f.service.crew_records(self.f.plan,source)
        people[0].update(to_id=destination,to_name='Excluded destination')
        refreshed=refresh_crew_plan(original,source,people,self.f.service.context(self.f.plan))
        self.assertFalse(any(s['vessel_id']==destination for s in refreshed['stops']))
        self.assertNotIn('Passengers:'+self.identifier,refreshed['included'])
    def test_restore_keeps_tracking_and_adds_optional_indexes_to_legacy_backup(self):
        self.saved();backup=self.f.root/'legacy.sqlite3'
        self.f.service.backup(backup)
        db=sqlite3.connect(backup)
        try:
            for index in ('passengers_plan','personnel_history_task','berth_created'):db.execute('DROP INDEX '+index)
            db.commit()
        finally:db.close()
        self.f.service.restore(backup)
        row=self.f.service.passenger(self.identifier)
        self.f.service.edit_crew_entry(self.identifier,{**row,'position':'After Restore'},row['version'])
        self.assertEqual(2,max(p['version'] for p in self.f.service.berth_versions()))
        query=list(self.f.service.db.execute('EXPLAIN QUERY PLAN SELECT id FROM passengers WHERE plan_id=?',(self.f.plan,)))
        self.assertTrue(any('passengers_plan' in r[3] for r in query),query)
        PersonnelService.validate_file(self.f.service.path)
    def test_malformed_draft_cannot_make_live_database_unreadable(self):
        self.saved();before=self.f.service.berth_versions()
        draft=self.f.generate(mode='Final');draft.pop('stops');draft['transport_contract']={}
        with self.assertRaises(PersonnelError):self.f.service.save_berth(draft,False)
        self.assertEqual(before,self.f.service.berth_versions())
        PersonnelService.validate_file(self.f.service.path)


class ArchitectureEditorTests(unittest.TestCase):
    setUpClass=classmethod(frontend.FrontendTests.setUpClass.__func__)
    setUp=frontend.FrontendTests.setUp
    tearDown=frontend.FrontendTests.tearDown
    wait=frontend.FrontendTests.wait
    draft=frontend.FrontendTests.draft
    def test_build_copies_route_once_instead_of_once_per_person_and_stop(self):
        builder=self.draft()
        with patch.object(builder,'route_snapshot',wraps=builder.route_snapshot) as snapshot:
            plan=builder.build()
        self.assertFalse(plan['issues']);self.assertLessEqual(snapshot.call_count,1)


class ArchitectureDashboardTests(unittest.TestCase):
    def test_automatic_dashboard_uses_newest_family_version_after_clock_rollback(self):
        from test_dashboard import DashboardTests
        fixture=DashboardTests();fixture.setUp()
        try:
            with patch('cargo_track.personnel_service.now',return_value='2001-01-01T00:00:00+00:00'):
                newest=fixture.personnel.save_berth(copy.deepcopy(fixture.saved),False,fixture.saved['family_id'])
            self.assertEqual(newest['id'],fixture.read()['personnel']['selected_id'])
            self.assertEqual(fixture.saved['id'],fixture.read(fixture.saved['id'])['personnel']['selected_id'])
        finally:fixture.tearDown()

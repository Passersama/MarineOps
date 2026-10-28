import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cargo_track.domain import Command, AppError
from cargo_track.service import ApplicationService
from cargo_track.personnel_service import PersonnelService
from cargo_track.personnel_cargo import read_cargo
from cargo_track.berth_plan import generate_plan, export_plan
from openpyxl import load_workbook


class SharedPortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cargo = ApplicationService(self.root / 'cargo-track.sqlite3')
        self.cargo.open()
        self.personnel = PersonnelService(self.root / 'personnel-transfer.sqlite3')
        self.counter = 0

    def tearDown(self):
        self.personnel.close()
        self.cargo.close()
        self.temp.cleanup()

    def command(self, operation, payload):
        self.counter += 1
        return self.cargo.handle(Command('shared-port-' + str(self.counter), operation, payload)).result

    def test_one_location_rename_reaches_cargo_and_personnel_and_survives_restart(self):
        shore = self.cargo.workspace_snapshot()['shore_location_id']
        vessel = self.command('create_vessel', {'name':'Test Vessel'})['id']
        no = self.command('create_transfer', {'description':'Box', 'from_location_id':shore,
                                           'to_location_id':vessel})['no']
        raw_before = dict(self.cargo.repo.leg(no))
        self.command('set_setting', {'key':'port_name', 'value':'Jubail Port'})
        self.assertEqual('Jubail Port', self.cargo.transfer_detail(no)['row']['from_name'])
        self.assertEqual(raw_before, dict(self.cargo.repo.leg(no)))
        snapshot = read_cargo(self.cargo.path)
        for name in ('On Shore', 'xxPort', 'xx port', 'Jubail Port'):
            record = self.personnel.bind_record({'name':'Person', 'position':'Engineer', 'date':'2026-10-07',
                     'from_name':name, 'to_name':'Test Vessel', 'direction':'Transfer'}, snapshot)
            self.assertEqual(shore, record['from_id'])
            self.assertFalse(record['issues'])
        self.assertEqual('Jubail Port', self.personnel.port_name(snapshot))
        self.cargo.close()
        self.cargo.open()
        self.assertEqual(shore, self.cargo.workspace_snapshot()['shore_location_id'])
        self.assertEqual('Jubail Port', self.cargo.workspace_snapshot()['settings']['port_name'])
        self.assertEqual(1, self.cargo.db.execute("SELECT count(*) FROM locations WHERE kind='SHORE'").fetchone()[0])

    def test_delivered_confirmed_location_uses_port_and_retains_original_evidence(self):
        shore = self.cargo.workspace_snapshot()['shore_location_id']
        vessel = self.command('create_vessel', {'name':'Test Vessel'})['id']
        no = self.command('create_transfer', {'description':'Box', 'from_location_id':vessel,
                                           'to_location_id':shore})['no']
        self.command('pick_up', {'no':no, 'expected_version':0, 'confirmed_location':True})
        self.command('deliver', {'no':no, 'expected_version':1, 'confirmed_location':True})
        completed = dict(self.cargo.repo.leg(no))
        self.command('set_setting', {'key':'port_name', 'value':'Shared Port'})
        detail = self.cargo.transfer_detail(no)
        self.assertEqual('Shared Port', detail['location']['label'])
        self.assertEqual('Shared Port', detail['row']['cargo_location']['label'])
        self.assertEqual('Shared Port', detail['legs'][0]['to'])
        self.assertEqual(completed, dict(self.cargo.repo.leg(no)))

    def test_invalid_name_rolls_back_setting_location_and_revision(self):
        vessel = self.command('create_vessel', {'name':'Taken Name'})['id']
        before = self.cargo.workspace_snapshot()
        for name in ('', '  ', 'Taken Name', 'x' * 121):
            with self.assertRaises(AppError):
                self.command('set_setting', {'key':'port_name', 'value':name})
            after = self.cargo.workspace_snapshot()
            self.assertEqual(before['settings'], after['settings'])
            self.assertEqual(before['locations'], after['locations'])
            self.assertEqual(before['revision'], after['revision'])

    def test_legacy_on_shore_is_migrated_without_new_location_or_leg_changes(self):
        shore = self.cargo.workspace_snapshot()['shore_location_id']
        no = self.command('create_transfer', {'description':'Legacy', 'from_location_id':shore,
                                           'to_location_id':shore})['no']
        raw = dict(self.cargo.repo.leg(no))
        self.cargo.close()
        conn = sqlite3.connect(self.cargo.path)
        conn.execute("DELETE FROM settings WHERE key='port_name'")
        conn.execute("UPDATE locations SET name='On Shore',name_key='on shore' WHERE kind='SHORE'")
        conn.commit()
        conn.close()
        self.cargo.open()
        snapshot = self.cargo.workspace_snapshot()
        self.assertEqual(shore, snapshot['shore_location_id'])
        self.assertEqual('xx port', snapshot['settings']['port_name'])
        self.assertEqual(raw, dict(self.cargo.repo.leg(no)))

    def test_saved_plan_keeps_port_snapshot_while_new_plan_and_excel_use_shared_name(self):
        vessel = self.command('create_vessel', {'name':'Test Vessel'})['id']
        self.command('create_voyage', {'name':'Route'})
        self.command('add_stop', {'vessel_id':vessel})
        plan_id = self.personnel.create_plan('Crew', '2026-10-07')
        snapshot = read_cargo(self.cargo.path)
        person = self.personnel.bind_record({'name':'Person', 'position':'Engineer', 'date':'2026-10-07',
                    'direction':'Sign-off', 'vessel':'Test Vessel'}, snapshot)
        self.personnel.add_passenger(plan_id, person)
        def generate():
            source = read_cargo(self.cargo.path)
            port = next(r for r in source['locations'] if r['kind'] == 'SHORE')
            source['stops'].append({'id':'plan:port','vessel_id':port['id'],'vessel_name_snapshot':port['name']})
            return generate_plan(source, self.personnel.crew_records(plan_id, source), [], '2026-10-07',
                                 self.personnel.port_name(source), mode='Final', personnel_plan_id=plan_id)
        old = self.personnel.save_berth(generate(), published=True)
        frozen = copy.deepcopy(old)
        self.command('set_setting', {'key':'port_name', 'value':'Unified Port'})
        new = self.personnel.save_berth(generate(), published=True)
        self.assertEqual('xx port', old['stops'][-1]['name'])
        self.assertEqual('Unified Port', new['stops'][-1]['name'])
        self.assertEqual('Unified Port', new['stops'][-1]['drop_passengers'][0]['to_name'])
        self.assertIn(frozen, self.personnel.berth_versions())
        export = self.root / 'new-plan.xlsx'
        export_plan(new, export)
        book = load_workbook(export, read_only=True)
        try:
            values = [str(cell.value) for sheet in book for row in sheet for cell in row if cell.value is not None]
            self.assertIn('Unified Port', values)
            self.assertFalse(any('On Shore' in v for v in values))
        finally:
            book.close()


if __name__ == '__main__':
    unittest.main()

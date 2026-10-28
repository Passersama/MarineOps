import csv
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from openpyxl import load_workbook
from cargo_track.domain import Command
from cargo_track.service import ApplicationService
from cargo_track.models import TransferTableModel


class DisplayNumberTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = ApplicationService(self.root / 'cargo.sqlite3')
        self.service.open()
        self.sequence = 0
        shore = self.service.workspace_snapshot()['shore_location_id']
        vessel = self.command('create_vessel', {'name':'Test Vessel'})['id']
        self.ids = [self.command('create_transfer', {'description':name, 'from_location_id':shore,
            'to_location_id':vessel})['no'] for name in ('Other', 'Keep Alpha', 'Keep Bravo')]

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def command(self, operation, payload):
        self.sequence += 1
        return self.service.handle(Command('number-test-' + str(self.sequence), operation, payload)).result

    def test_filter_restarts_display_number_without_changing_record_identity(self):
        filtered = self.service.query_transfers('all', {'query':'Keep'})
        model = TransferTableModel()
        model.replace(filtered['rows'], filtered['offset'])
        self.assertEqual(['1','2'], [model.data(model.index(i,0)) for i in range(2)])
        self.assertEqual(self.ids[1:], [r['no'] for r in model.rows])
        self.assertEqual(['C-000002','C-000003'], [r['cargo_tag'] for r in model.rows])
        target = model.data(model.index(1,0), Qt.ItemDataRole.UserRole)
        self.command('pick_up', {'no':target['no'], 'expected_version':target['version'], 'confirmed_location':True})
        self.assertEqual('Waiting', self.service.transfer_detail(self.ids[1])['row']['status'])
        self.assertEqual('On Board', self.service.transfer_detail(self.ids[2])['row']['status'])

    def test_paging_continues_within_filtered_result_then_new_filter_restarts(self):
        model = TransferTableModel()
        result = self.service.query_transfers('all', {'query':'Keep'}, limit=1, offset=1)
        model.replace(result['rows'], result['offset'])
        self.assertEqual('2', model.data(model.index(0,0)))
        result = self.service.query_transfers('all', {'query':'Bravo'}, limit=1)
        model.replace(result['rows'], result['offset'])
        self.assertEqual('1', model.data(model.index(0,0)))
        self.assertEqual('C-000003', model.row_at(0)['cargo_tag'])

    def test_csv_and_excel_number_filtered_sorted_rows_from_one(self):
        before = self.service.path.read_bytes()
        for fmt in ('csv','xlsx'):
            path = self.root / ('view.' + fmt)
            self.service.export_to(path, 'all', {'query':'Keep'}, fmt, order_column=2, descending=True)
            if fmt == 'csv':
                with path.open(encoding='utf-8-sig', newline='') as stream:
                    rows = list(csv.reader(stream))[1:]
            else:
                book = load_workbook(path, read_only=True)
                try:
                    rows = list(book.active.values)[1:]
                finally:
                    book.close()
            self.assertEqual(['1','2'], [str(row[0]) for row in rows])
            self.assertEqual(['C-000003','C-000002'], [row[1] for row in rows])
        self.assertEqual(before, self.service.path.read_bytes())


if __name__ == '__main__':
    unittest.main()

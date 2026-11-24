import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sync_treasury_sheets as treasury


class TreasurySheetsTests(unittest.TestCase):
    def test_unapproved_bytes_rejected_before_parser(self):
        rid = next(iter(treasury.SOURCES))
        with patch.object(treasury, 'download', return_value=b'wrong xlsx'), patch.object(treasury, 'parse_workbook') as parser:
            with self.assertRaisesRegex(ValueError, 'independent review'):
                treasury.fresh(rid, None)
            parser.assert_not_called()

    def test_first_enable_only_when_entire_group_prepared(self):
        catalog = {'datasets': [{'id': treasury.DATASET, 'license_id': 'CC0-1.0',
            'organization': {'name': 'valsts-kase'}, 'resources': [
            {'id': rid, 'url': treasury.source_url(rid), 'format': 'XLSX'} for rid in treasury.SOURCES]}]}
        from publish_budget_estimates import json_bytes
        with patch.object(treasury, 'fetch_pages', return_value=json_bytes(catalog)):
            self.assertEqual(treasury.standby(), {})
        r = catalog['datasets'][0]['resources'][0]
        rid = r['id']
        r['local_preview'] = {**treasury.identity(rid), 'total': sum(v[-1] for v in treasury.sheets_for(rid).values()),
                              'convertedAt': '2026-01-01T09:00:00+00:00',
                              'reportSheets': [{'id':'dati'}]}
        with patch.object(treasury, 'fetch_pages', return_value=json_bytes(catalog)):
            with self.assertRaisesRegex(ValueError, 'Incomplete previously published Treasury worksheets'):
                treasury.standby()

import json
import pathlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sync_reviewed_xlsx as review
from publish_budget_estimates import json_bytes


def fixture():
    datasets = {}
    for rid, (dsid, url, *_) in review.SOURCES.items():
        datasets.setdefault(dsid, {'id': dsid, 'license_id': 'CC0-1.0',
                                   'organization': {'name': 'valsts-kase'}, 'resources': []})
        datasets[dsid]['resources'].append({'id': rid, 'url': url, 'format': 'XLSX'})
    datasets['unrelated'] = {'id': 'unrelated', 'resources': [{'id': 'baseline',
                                                               'local_preview': {'old': True}}]}
    return {'datasets': list(datasets.values())}


def fake_asset(rid, *_):
    meta = {**review.provenance(rid), 'convertedAt': '2026-01-10T11:11:11+00:00'}
    encoded = json_bytes({'schemaVersion': 1, 'resourceId': rid, **meta, 'sheets': [],
                          **({'sourceSubtotal': review.SUBTOTAL} if rid == review.FOOTER else {})})
    digest = review.sha(encoded)
    return {'path': review.asset_path(rid, digest), 'sha256': digest, 'total': review.SOURCES[rid][5],
            **meta}, encoded


class ReviewedTests(unittest.TestCase):
    def test_exact_decimal_no_float_and_municipal_whole(self):
        element = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                '<v>4754.1400000000003</v></c>')
        self.assertEqual(review.amount(element, 'decimal'), '4754.1400000000003')
        with self.assertRaises(ValueError):
            review.amount(element, 'number')

    def test_footer_requires_exact_provenance(self):
        element = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
                                ' r="F31030"><f>SUBTOTAL(9,F2:F31029)</f><v>28885561868</v></c>')
        self.assertEqual(review.verify_footer({5: element}), review.SUBTOTAL)
        with self.assertRaises(ValueError):
            review.verify_footer({5: ET.fromstring('<c r="F31030" />')})

    def test_source_digest_checked_before_parsing(self):
        with patch.object(review, 'download', return_value=b'<html>unapproved</html>'), \
             patch.object(review, 'parse_workbook') as parser:
            with self.assertRaisesRegex(ValueError, 'independent review'):
                review.fresh_resource(review.FEB, None)
            parser.assert_not_called()

    def test_failed_refresh_and_failed_catalog_swap_leave_previous_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            cp = root / 'public/data/catalog.json'
            cp.parent.mkdir(parents=True)
            initial = json_bytes(fixture())
            cp.write_bytes(initial)
            with patch.object(review, 'fresh_resource', side_effect=OSError('failed source')), \
                 patch.object(review, 'fetch_pages', return_value=initial):
                self.assertEqual(review.sync(root=root, allow_standby=True), {})
                self.assertEqual(cp.read_bytes(), initial)
            actual = review.atomic_bytes
            def fail_catalog(path, content):
                if path == cp:
                    raise OSError('locked catalog')
                return actual(path, content)
            with patch.object(review, 'fresh_resource', side_effect=fake_asset), \
                 patch.object(review, 'atomic_bytes', side_effect=fail_catalog):
                with self.assertRaisesRegex(OSError, 'locked'):
                    review.sync(root=root)
            self.assertEqual(cp.read_bytes(), initial)
            self.assertEqual(list((root / 'public' / review.DIR).glob('*.json')), [])
            with patch.object(review, 'fresh_resource', side_effect=fake_asset):
                self.assertEqual(len(review.sync(root=root)), 7)
            self.assertEqual(json.loads(cp.read_bytes())['datasets'][-1]['resources'][0]['local_preview'],
                             {'old': True})

    def test_partial_prior_group_refuses_to_build(self):
        prior = fixture()
        review.find_resources(prior)[review.FEB]['local_preview'] = fake_asset(review.FEB)[0]
        with patch.object(review, 'fetch_pages', return_value=json_bytes(prior)):
            with self.assertRaisesRegex(ValueError, 'No complete reviewed'):
                review.obtain_standby()

    def test_forged_standby_tables_rejected_even_with_matching_payload_hash(self):
        prior = fixture()
        approved = {}
        for rid, res in review.find_resources(prior).items():
            meta, payload = fake_asset(rid)
            data = json.loads(payload)
            content = {k:v for k,v in data.items() if k in ('sheets', 'sourceSubtotal')}
            approved[rid] = review.sha(json_bytes(content))
            if rid == review.FEB:
                data['sheets'] = [{'unaudited': 'changed'}]
                payload = json_bytes(data)
                meta['sha256'] = review.sha(payload)
                meta['path'] = review.asset_path(rid, meta['sha256'])
            res['local_preview'] = meta
        def get(path, _):
            return json_bytes(prior) if path == 'data/catalog.json' else payloads[path]
        payloads = {fake_asset(rid)[0]['path']: fake_asset(rid)[1] for rid in review.SOURCES if rid != review.FEB}
        payloads[meta['path']] = payload
        with patch.object(review, 'fetch_pages', side_effect=get), patch.object(review, 'NORMALIZED', approved):
            with self.assertRaisesRegex(ValueError, 'reviewed normalized'):
                review.obtain_standby()

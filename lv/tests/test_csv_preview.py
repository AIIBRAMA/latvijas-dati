"""Exercise reviewed CSV import through its local publication entry point."""
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_csv_preview as m

DATASET = 'a0000000-0000-0000-0000-000000000001'
RESOURCE = 'b0000000-0000-0000-0000-000000000001'


def encode(rows):
    target = io.StringIO(newline='')
    csv.writer(target, delimiter=';', lineterminator='\r\n').writerows(rows)
    return target.getvalue().encode('utf-8-sig')


def fixture(data, *, headers=('Gads', 'Kods', 'Vērtība'), pad=1, count=1,
            dataset=DATASET, resource=RESOURCE):
    return m.ReviewedSource(dataset, resource, 'fixture.csv',
                            hashlib.sha256(data).hexdigest(), headers, pad, count)


def decoded(sheet):
    return [[sheet['fields'][i]['dictionary'][value] if value is not None else ''
             for i, value in enumerate(row)] for row in sheet['rows']]


class ParserTest(unittest.TestCase):
    def test_preserves_quoted_semicolon_multiline_blank_zero_and_leading_zero(self):
        row = ['2024', '001', 'a; "<tag>"\r\nb']
        other = ['', '0', '']
        data = encode([['Gads', 'Kods', 'Vērtība', ''], [*row, ''], [*other, ''], ['', '', '', '']])
        parsed = m.parse_csv(data, fixture(data, count=2))
        self.assertEqual(decoded(parsed), [row, other])

    def test_source_bytes_change_requires_review(self):
        data = encode([['Gads', 'Kods', 'Vērtība', ''], ['2024', '001', 'a', '']])
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            m.parse_csv(data + b'\r\n', fixture(data))

    def test_rejects_layout_type_and_size_failures(self):
        header = ['Gads', 'Kods', 'Vērtība', '']
        cases = [
            (encode([header, ['2024', '001', 'a']]), 'width', {}),
            (encode([header, ['2024', '001', 'a', '000']]), 'unlabelled', {}),
            (encode([header, ['2024', '001', '\u202eabc', '']]), 'control', {}),
            (encode([header, ['2024', '001', 'a' * 257, '']]), 'limit', {}),
            (encode([header, ['2024', '001', 'a', '']]), 'count changed', {'count': 2}),
            (encode([['Gads', 'ｇａｄｓ', 'Vērtība', ''], ['2024', '001', 'a', '']]), 'unique after', {'headers': ('Gads', 'ｇａｄｓ', 'Vērtība')}),
            (b'<html>error page</html>', 'header layout', {}),
            (b'a' * (m.MAX_SOURCE + 1), 'byte limit', {}),
        ]
        for data, message, params in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                m.parse_csv(data, fixture(data, **params))

    def test_record_limit_counts_blank_source_rows(self):
        data = encode([['Gads', 'Kods', 'Vērtība', ''], ['', '', '', ''],
                       ['', '', '', ''], ['2024', '001', 'a', '']])
        with patch.object(m, 'MAX_ROWS', 2), self.assertRaisesRegex(ValueError, 'record limit'):
            m.parse_csv(data, fixture(data))


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inbox = self.root / 'sources'
        self.inbox.mkdir()
        self.catalog_path = self.root / 'public/data/catalog.json'
        self.data = encode([['Gads', 'Kods', 'Vērtība', ''], ['2024', '001', 'a', '']])
        self.sources = [fixture(self.data), fixture(self.data, resource='b0000000-0000-0000-0000-000000000002')]
        self.sources = [replace(s, table_sha256=m.sha256(m.json_bytes(m.parse_csv(self.data, s)))) for s in self.sources]
        self.previous_pointer = {'sourceFormat': 'XLSX', 'path': 'old-verified-preview.json'}
        self.datasets = [{'id': DATASET, 'organization': {'name': 'iub'}, 'license_id': 'CC0-1.0',
                          'resources': [{'id': s.resource_id, 'url': s.url, 'format': 'CSV'} for s in self.sources]
                          + [{'id': 'other', 'local_preview': self.previous_pointer}]}]
        self.catalog_path.parent.mkdir(parents=True)
        self.save_catalog()
        for source in self.sources:
            (self.inbox / f'{source.resource_id}.csv').write_bytes(self.data)

    def save_catalog(self):
        self.catalog_path.write_text(json.dumps({'datasets': self.datasets}))

    def do_sync(self):
        return m.sync(self.root, self.inbox, sources=self.sources)

    def test_success_replay_and_unrelated_preview_unchanged(self):
        self.assertEqual(len(self.do_sync()), 2)
        published = self.catalog_path.read_bytes()
        target = json.loads(published)['datasets'][0]['resources']
        self.assertEqual(target[2]['local_preview'], self.previous_pointer)
        for source, record in zip(self.sources, target):
            preview = record['local_preview']
            self.assertEqual(preview['sourceFormat'], 'CSV')
            self.assertEqual(preview['licenseId'], 'CC0-1.0')
            payload = json.loads((self.root / 'public' / preview['path']).read_bytes())
            self.assertEqual(payload['sourceUrl'], source.url)
            self.assertEqual(payload['sourceSha256'], source.sha256)
            self.assertEqual(payload['convertedAt'], preview['convertedAt'])
            self.assertEqual(decoded(payload['sheets'][0]), [['2024', '001', 'a']])
        self.do_sync()
        self.assertEqual(self.catalog_path.read_bytes(), published)

    def test_failed_last_source_preserves_all_previously_published_bytes(self):
        self.do_sync()
        before = {p: p.read_bytes() for p in (self.root / 'public').rglob('*.json')}
        (self.inbox / f'{self.sources[-1].resource_id}.csv').write_bytes(b'wrong upstream')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            self.do_sync()
        self.assertEqual({p: p.read_bytes() for p in (self.root / 'public').rglob('*.json')}, before)

    def test_changed_source_url_license_or_other_preview_writes_nothing(self):
        dataset = self.datasets[0]
        original = dataset['resources'][0].copy()
        for changed, message in [
            ({'url': 'https://other.example/fixture.csv'}, 'address or format'),
            ({'format': 'HTML'}, 'address or format'),
            ({'local_preview': self.previous_pointer}, 'another preview type'),
        ]:
            dataset['resources'][0] = {**original, **changed}
            self.save_catalog()
            before = self.catalog_path.read_bytes()
            with self.assertRaisesRegex(ValueError, message):
                self.do_sync()
            self.assertEqual(self.catalog_path.read_bytes(), before)
            self.assertFalse((self.root / 'public/data/csv').exists())
        dataset['resources'][0] = original
        dataset['license_id'] = 'other'
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, 'publisher or license'):
            self.do_sync()

    def test_valid_datastore_candidate_is_not_replaced(self):
        self.datasets[0]['resources'][0]['datastore_active'] = True
        self.save_catalog()
        self.assertEqual(self.do_sync(), [(self.sources[1].resource_id, 1)])
        target = json.loads(self.catalog_path.read_bytes())['datasets'][0]['resources']
        self.assertNotIn('local_preview', target[0])

    def make_published(self):
        self.do_sync()
        manifest = json.loads(self.catalog_path.read_bytes())
        previews = [r['local_preview'] for r in manifest['datasets'][0]['resources'][:2]]
        encoded = {p['path']: (self.root / 'public' / p['path']).read_bytes() for p in previews}
        self.save_catalog()  # A fresh run has just rebuilt the base catalogue.
        return manifest, previews, encoded

    def run_standby(self, manifest, files):
        with patch.object(m, 'download', side_effect=TimeoutError('read timeout')), \
             patch.object(m, 'fetch_pages', side_effect=lambda path, limit: m.json_bytes(manifest) if path == 'data/catalog.json' else files[path]):
            return m.sync(self.root, sources=self.sources, allow_standby=True)

    def test_timeout_first_launch_is_only_allowed_if_published_catalogue_proves_absence(self):
        clean = self.catalog_path.read_bytes()
        self.assertEqual(self.run_standby(json.loads(clean), {}), [])
        self.assertEqual(self.catalog_path.read_bytes(), clean)
        with patch.object(m, 'download', side_effect=TimeoutError), patch.object(m, 'fetch_pages', side_effect=OSError):
            with self.assertRaises(OSError):
                m.sync(self.root, sources=self.sources, allow_standby=True)

    def test_standby_retains_both_exact_files_and_marks_catalogue(self):
        manifest, _, files = self.make_published()
        self.assertEqual(len(self.run_standby(manifest, files)), 2)
        for resource in json.loads(self.catalog_path.read_bytes())['datasets'][0]['resources'][:2]:
            prev = resource['local_preview']
            self.assertTrue(prev['snapshotFallback'])
            self.assertEqual(prev['snapshotFallbackReason'], 'source-unavailable')
            self.assertEqual((self.root / 'public' / prev['path']).read_bytes(), files[prev['path']])

    def test_standby_partial_or_forged_fails_closed(self):
        manifest, previews, files = self.make_published()
        clean = self.catalog_path.read_bytes()
        missing = manifest['datasets'][0]['resources'][1].pop('local_preview')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.run_standby(manifest, files)
        manifest['datasets'][0]['resources'][1]['local_preview'] = missing
        p = previews[0]
        body = json.loads(files[p['path']])
        body['sheets'][0]['fields'][1]['dictionary'][0] = '002'
        files[p['path']] = m.json_bytes(body)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.run_standby(manifest, files)
        p['sha256'] = m.sha256(files[p['path']])
        with self.assertRaisesRegex(ValueError, 'independently reviewed'):
            self.run_standby(manifest, files)
        self.assertEqual(self.catalog_path.read_bytes(), clean)

    def test_content_review_failure_blocks_strict_run(self):
        with patch.object(m, 'download', return_value=b'new, unreviewed source'), patch.object(m, 'fetch_pages') as fetch:
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                m.sync(self.root, sources=self.sources)
            fetch.assert_not_called()

    def test_changed_bytes_skip_first_launch_or_restore_both_with_review_flag(self):
        initial = json.loads(self.catalog_path.read_bytes())
        with patch.object(m, 'download', return_value=b'new, unreviewed source'), \
             patch.object(m, 'fetch_pages', return_value=m.json_bytes(initial)):
            self.assertEqual(m.sync(self.root, sources=self.sources, allow_standby=True), [])
        manifest, _, files = self.make_published()
        with patch.object(m, 'download', return_value=b'new, unreviewed source'), \
             patch.object(m, 'fetch_pages', side_effect=lambda path, limit: m.json_bytes(manifest) if path == 'data/catalog.json' else files[path]):
            self.assertEqual(len(m.sync(self.root, sources=self.sources, allow_standby=True)), 2)
        for resource in json.loads(self.catalog_path.read_bytes())['datasets'][0]['resources'][:2]:
            preview = resource['local_preview']
            self.assertEqual(preview['snapshotFallbackReason'], 'source-changed')
            self.assertEqual((self.root / 'public' / preview['path']).read_bytes(), files[preview['path']])


if __name__ == '__main__':
    unittest.main()

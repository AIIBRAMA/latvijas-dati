"""Exercise the official-to-cache transition through the publication entry point."""
import copy
import gzip
import json
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import budget_estimate_fallback as fallback
import publish_budget_estimates as publish
from sync_budget_estimates import NUMERIC_LABELS, SOURCE_FIELDS
sys.path.pop(0)

OLD = '2025-09-28T12:00:00+00:00'
NEW = '2026-01-03T12:00:00+00:00'


def complete_snapshot(checked=OLD, source=b'complete unfiltered original', years=(2025, 2026)):
    sha = fallback.sha256(source)
    snapshot = {'sourceFormat': 'JSON', 'sourceUrl': publish.SOURCE_URL,
                'sourceSha256': sha, 'convertedAt': checked, 'sourceCheckedAt': checked,
                'total': len(years), 'partitions': []}
    assets = {}
    for year in years:
        path = f'data/json/{publish.RESOURCE_ID}-v1-{sha[:16]}-{year}.json'
        fields = [({'id': NUMERIC_LABELS[key], 'sourceId': key, 'type': 'number'} if key in NUMERIC_LABELS
                   else {'id': key, 'type': 'text', 'dictionary': ['Ādaži']}) for key in SOURCE_FIELDS]
        row = [year if key == 'gads' else -0.1 if key == 'vertiba' else 0 for key in SOURCE_FIELDS]
        sheet = {'name': 'Valsts budžeta tāmes', 'cachedFormulaCount': 0,
                 'fields': fields, 'rows': [row], 'total': 1}
        payload = {'schemaVersion': 1, 'resourceId': publish.RESOURCE_ID,
                   'sourceFormat': 'JSON', 'sourceUrl': publish.SOURCE_URL,
                   'sourceSha256': sha, 'convertedAt': checked, 'sheets': [sheet]}
        content = publish.json_bytes(payload)
        assets[path] = content
        snapshot['partitions'].append({'label': str(year), 'path': path, 'total': 1,
                                       'sha256': fallback.sha256(content)})
    return snapshot, assets


def catalog(preview=None):
    resource = {'id': publish.RESOURCE_ID, 'url': publish.SOURCE_URL}
    if preview is not None:
        resource['local_preview'] = preview
    return {'datasets': [{'id': publish.DATASET, 'resources': [resource]},
                         {'id': 'unrelated-dataset', 'resources': [{'id': 'unrelated-resource'}]}]}


class FallbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'lv'
        self.data = self.root / 'public/data'
        self.data.mkdir(parents=True)
        self.catalog = self.data / 'catalog.json'
        self.catalog.write_bytes(publish.json_bytes(catalog()))
        self.seed = self.root / 'fixtures/budget-estimates'
        self.seed.mkdir(parents=True)
        self.manifest, self.source_assets = complete_snapshot()
        self.pack_assets()
        self.download = patch.object(publish, 'download', side_effect=URLError(TimeoutError('timeout'))).start()
        self.page = patch.object(fallback, 'fetch_pages', return_value=publish.json_bytes(catalog())).start()
        self.addCleanup(patch.stopall)

    def pack_assets(self):
        for part in self.manifest['partitions']:
            path = part['path']
            packed = gzip.compress(self.source_assets[path], mtime=0)
            (self.seed / (Path(path).name + '.gz')).write_bytes(packed)
            part['compressedSha256'] = fallback.sha256(packed)
        (self.seed / 'manifest.json').write_bytes(publish.json_bytes(self.manifest))

    def assert_saved(self, expected_assets):
        for path, encoded in expected_assets.items():
            self.assertEqual((self.root / 'public' / path).read_bytes(), encoded)
        self.assertEqual(json.loads(self.catalog.read_bytes())['datasets'][1], catalog()['datasets'][1])

    def test_timeout_publishes_exact_verified_seed_with_original_date_and_counts(self):
        with patch.object(publish, 'parse_budget_estimates') as parse:
            result = publish.publish(root=self.root)
            parse.assert_not_called()
        self.download.assert_called_once_with(publish.SOURCE_URL)
        self.assertTrue(result['snapshotFallback'])
        self.assertEqual(result['sourceCheckedAt'], OLD)
        self.assertEqual(result['convertedAt'], OLD)
        self.assertEqual(result['total'], 2)
        self.assert_saved(self.source_assets)

    def test_verified_newer_publication_takes_precedence_and_does_not_become_fresh(self):
        latest, assets = complete_snapshot(NEW, b'latest complete official original', (2025, 2026, 2027))
        self.page.side_effect = lambda path, _lim: (
            publish.json_bytes(catalog(latest)) if path == 'data/catalog.json' else assets[path]
        )
        result = publish.publish(root=self.root)
        self.assertTrue(result['snapshotFallback'])
        self.assertEqual(result['sourceCheckedAt'], NEW)
        self.assertEqual(result['total'], 3)
        self.assertNotEqual(result['sourceSha256'], self.manifest['sourceSha256'])
        self.assert_saved(assets)

    def test_corrupt_seed_leaves_catalog_unchanged(self):
        before = self.catalog.read_bytes()
        part = self.manifest['partitions'][0]
        (self.seed / (Path(part['path']).name + '.gz')).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'compressed checksum'):
            publish.publish(root=self.root)
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertFalse((self.data / 'json').exists())

    def test_bad_year_is_rejected_even_with_plausible_checksums(self):
        before = self.catalog.read_bytes()
        part = self.manifest['partitions'][0]
        entry = json.loads(self.source_assets[part['path']])
        entry['sheets'][0]['rows'][0][0] = 2099
        self.source_assets[part['path']] = publish.json_bytes(entry)
        part['sha256'] = fallback.sha256(self.source_assets[part['path']])
        self.pack_assets()
        with self.assertRaisesRegex(ValueError, 'invalid value or year'):
            publish.publish(root=self.root)
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertFalse((self.data / 'json').exists())

    def test_public_catalog_cannot_read_arbitrary_path_even_on_official_timeout(self):
        latest, assets = complete_snapshot(NEW)
        latest['partitions'][0]['path'] = 'https://elsewhere.invalid/malicious.json'
        self.page.side_effect = lambda path, _lim: (
            publish.json_bytes(catalog(latest)) if path == 'data/catalog.json' else assets[path]
        )
        with self.assertRaisesRegex(ValueError, 'unexpected partition path'):
            publish.publish(root=self.root)
        self.page.assert_called_once_with('data/catalog.json', fallback.MAX_CATALOG)

    def test_no_fallback_if_official_response_is_invalid_or_access_is_denied(self):
        before = self.catalog.read_bytes()
        for exc in (ValueError('new schema'), HTTPError(publish.SOURCE_URL, 403, 'Forbidden', {}, None),
                    URLError(ssl.SSLCertVerificationError('Unexpected pin'))):
            self.download.side_effect = exc
            with self.subTest(exc=exc), self.assertRaises(type(exc)):
                publish.publish(root=self.root)
            self.assertEqual(self.catalog.read_bytes(), before)
        self.download.side_effect = None
        self.download.return_value = b'{"api":"wrong"}'
        with self.assertRaises(ValueError):
            publish.publish(root=self.root)
        self.page.assert_not_called()
        self.assertEqual(self.catalog.read_bytes(), before)

    def test_fresh_official_result_replaces_fallback_with_checked_date(self):
        fallback_preview = publish.publish(root=self.root)
        self.download.side_effect = None
        self.download.return_value = b'new complete official'
        fixture, assets = complete_snapshot()
        original = [json.loads(assets[fixture['partitions'][0]['path']])['sheets'][0]]
        with patch.object(publish, 'parse_budget_estimates', return_value=original):
            fresh = publish.publish(root=self.root)
        self.assertNotIn('snapshotFallback', fresh)
        self.assertGreater(fallback.timestamp(fresh['sourceCheckedAt']), fallback.timestamp(OLD))
        self.assertEqual(fresh['total'], 1)
        self.assertNotEqual(fallback_preview['sourceSha256'], fresh['sourceSha256'])
        self.assertTrue(all(not (self.root / 'public' / p).exists() for p in self.source_assets))


if __name__ == '__main__':
    unittest.main()

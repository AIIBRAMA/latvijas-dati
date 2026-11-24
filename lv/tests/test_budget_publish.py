"""Offline publication-boundary tests; no network or GitHub access."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import publish_budget_estimates as module
sys.path.pop(0)
REPO = SCRIPTS.parents[1]


def sheets():
    return [{'name': 'Tāmes', 'fields': [
        {'id': 'Gads', 'type': 'number'},
        {'id': 'iestades_kods', 'type': 'text', 'dictionary': ['001', '002', 'unused']},
        {'id': 'Summa', 'type': 'number'}],
        'rows': [[2025, 0, 12.5], [2026, 1, -25], [2025, None, 0]], 'total': 3}]


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'lv'
        self.data = self.root / 'public/data'
        (self.data / 'json').mkdir(parents=True)
        (self.data / 'xlsx').mkdir()
        self.old = self.data / 'json' / f'{module.RESOURCE_ID}-v1-previous-2025.json'
        self.old.write_text('{"old":"keep on failure"}', encoding='utf-8')
        self.other = self.data / 'json/unrelated-resource.json'
        self.other.write_text('{"unrelated":true}', encoding='utf-8')
        (self.data / 'xlsx/previous.xlsx.json').write_text('{"xlsx":true}', encoding='utf-8')
        self.catalog_path = self.data / 'catalog.json'
        self.catalog = {'datasets': [{'id': module.DATASET, 'resources': [
            {'id': module.RESOURCE_ID, 'url': module.SOURCE_URL, 'format': 'JSON',
             'local_preview': {'sourceFormat': 'JSON', 'partitions': [
                 {'label': '2025', 'path': 'data/json/' + self.old.name, 'total': 1}]}}
        ]}, {'id': 'another-dataset', 'resources': [{'id': 'another-resource',
                                                  'local_preview': {'path': 'data/xlsx/previous.xlsx.json'}}]}]}
        self.catalog_path.write_text(json.dumps(self.catalog), encoding='utf-8')
        self.source_dir = Path(self.directory.name) / 'source'
        self.source_dir.mkdir()
        self.source = b'offline wrapper test; parsing boundary is explicitly stubbed'
        (self.source_dir / f'{module.RESOURCE_ID}.json').write_bytes(self.source)
        self.parse = patch.object(module, 'parse_budget_estimates', side_effect=lambda _: sheets()).start()
        self.addCleanup(patch.stopall)
        self.network = patch.object(module, 'download', side_effect=AssertionError('No live download in offline tests')).start()

    def snapshot(self):
        return {str(p.relative_to(self.data)): p.read_bytes()
                for p in self.data.rglob('*') if p.is_file()}

    def publish(self):
        return module.publish(self.source_dir, root=self.root)

    def test_partitions_preserve_all_rows_and_compact_dictionaries(self):
        preview = self.publish()
        self.assertEqual(preview['sourceFormat'], 'JSON')
        self.assertNotIn('path', preview)
        self.assertEqual(preview['total'], 3)
        self.assertEqual([p['label'] for p in preview['partitions']], ['2026', '2025'])
        self.assertEqual([p['total'] for p in preview['partitions']], [1, 2])
        sha = hashlib.sha256(self.source).hexdigest()
        decoded = []
        for part in preview['partitions']:
            self.assertEqual(part['path'], f'data/json/{module.RESOURCE_ID}-v1-{sha[:16]}-{part["label"]}.json')
            payload = json.loads((self.root / 'public' / part['path']).read_text(encoding='utf-8'))
            self.assertEqual(payload['schemaVersion'], 1)
            self.assertEqual(payload['sourceSha256'], sha)
            self.assertEqual(payload['resourceId'], module.RESOURCE_ID)
            self.assertEqual(payload['sourceUrl'], module.SOURCE_URL)
            sheet = payload['sheets'][0]
            self.assertNotIn('unused', sheet['fields'][1]['dictionary'])
            for row in sheet['rows']:
                decoded.append([row[0], None if row[1] is None else sheet['fields'][1]['dictionary'][row[1]], row[2]])
        self.assertEqual(sorted(decoded, key=lambda r: (r[0], str(r[1]))),
                         [[2025, '001', 12.5], [2025, None, 0], [2026, '002', -25]])
        saved = json.loads(self.catalog_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['datasets'][0]['resources'][0]['local_preview'], preview)
        self.assertEqual(saved['datasets'][1], self.catalog['datasets'][1])
        self.assertFalse(self.old.exists())
        self.assertTrue(self.other.exists())
        self.assertTrue((self.data / 'xlsx/previous.xlsx.json').exists())
        self.network.assert_not_called()
        self.parse.assert_called_once_with(self.source)

    def test_parse_failure_keeps_catalog_and_every_previous_preview(self):
        before = self.snapshot()
        self.parse.side_effect = ValueError('Schema changed')
        with self.assertRaisesRegex(ValueError, 'Schema changed'):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_changed_source_url_stops_before_reading_or_download(self):
        self.catalog['datasets'][0]['resources'][0]['url'] = module.SOURCE_URL + '?gads=2026'
        self.catalog_path.write_text(json.dumps(self.catalog), encoding='utf-8')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'URL changed'):
            self.publish()
        self.parse.assert_not_called()
        self.network.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_source_size_bound_applies_to_offline_bytes(self):
        before = self.snapshot()
        with patch.object(module, 'MAX_DOWNLOAD', len(self.source) - 1):
            with self.assertRaisesRegex(ValueError, 'source exceeds'):
                self.publish()
        self.parse.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_later_oversize_partition_removes_new_files_not_previous_previews(self):
        source_sheets = sheets()
        source_sheets[0]['fields'][1]['dictionary'][0] = 'large' * 1000
        self.parse.side_effect = lambda _: copy.deepcopy(source_sheets)
        before = self.snapshot()
        with patch.object(module, 'MAX_PREVIEW', 2000):
            with self.assertRaisesRegex(ValueError, 'year 2025 exceeds'):
                self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_catalog_commit_failure_removes_only_new_unreferenced_files(self):
        before = self.snapshot()
        real_write = module.atomic_bytes
        def fail_catalog(path, content):
            if path == self.catalog_path:
                raise OSError('catalog write denied')
            return real_write(path, content)
        with patch.object(module, 'atomic_bytes', side_effect=fail_catalog):
            with self.assertRaisesRegex(OSError, 'catalog write denied'):
                self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_repeat_source_preserves_cached_files_even_when_catalog_commit_fails(self):
        first = self.publish()
        repeated = self.publish()
        self.assertEqual(first['convertedAt'], repeated['convertedAt'])
        for part in repeated['partitions']:
            payload = json.loads((self.root / 'public' / part['path']).read_text(encoding='utf-8'))
            self.assertEqual(payload['convertedAt'], repeated['convertedAt'])
        before = self.snapshot()
        with patch.object(module, 'atomic_bytes', side_effect=OSError('catalog write denied')) as write:
            with self.assertRaisesRegex(OSError, 'catalog write denied'):
                self.publish()
            self.assertEqual(write.call_count, 1)
            self.assertEqual(write.call_args.args[0], self.catalog_path)
        self.assertEqual(self.snapshot(), before)
        module.atomic_bytes(self.catalog_path, b'complete public asset')
        self.assertEqual(self.catalog_path.stat().st_mode & 0o777, 0o644)

    def test_conflicting_cache_is_rejected_without_overwriting(self):
        self.publish()
        cached = next((self.data / 'json').glob(f'{module.RESOURCE_ID}-*-2026.json'))
        altered = json.loads(cached.read_text(encoding='utf-8'))
        altered['sheets'][0]['rows'][0][2] = 999
        cached.write_text(json.dumps(altered), encoding='utf-8')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_invalid_year_and_dictionary_fail_without_silently_dropping_rows(self):
        for value in (None, True, 2025.5, '2025', 2201):
            source_sheets = sheets()
            source_sheets[0]['rows'][0][0] = value
            self.parse.side_effect = lambda _, s=source_sheets: copy.deepcopy(s)
            before = self.snapshot()
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'invalid year'):
                self.publish()
            self.assertEqual(self.snapshot(), before)
        source_sheets = sheets()
        source_sheets[0]['rows'][0][1] = -1
        self.parse.side_effect = lambda _: copy.deepcopy(source_sheets)
        with self.assertRaisesRegex(ValueError, 'dictionary index'):
            self.publish()

    def test_empty_or_inconsistent_conversion_is_not_published(self):
        for bad in ([], [{**sheets()[0], 'total': 999}], [{**sheets()[0], 'rows': [], 'total': 0}]):
            self.parse.side_effect = None
            self.parse.return_value = bad
            before = self.snapshot()
            with self.subTest(value=bad), self.assertRaisesRegex(ValueError, 'Empty or inconsistent'):
                self.publish()
            self.assertEqual(self.snapshot(), before)

    def test_duplicate_catalog_target_is_rejected(self):
        self.catalog['datasets'][0]['resources'].append(copy.deepcopy(self.catalog['datasets'][0]['resources'][0]))
        self.catalog_path.write_text(json.dumps(self.catalog), encoding='utf-8')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_cli_source_dir_uses_exact_resource_filename(self):
        with patch.object(module, 'ROOT', self.root):
            module.main(['--source-dir', str(self.source_dir)])
        self.network.assert_not_called()
        self.assertEqual(self.parse.call_args.args, (self.source,))

    def test_live_entry_point_uses_exact_reviewed_endpoint(self):
        self.network.side_effect = None
        self.network.return_value = self.source
        module.publish(root=self.root)
        self.network.assert_called_once_with(module.SOURCE_URL)

    def test_atomic_file_failure_keeps_destination_and_removes_temp_file(self):
        before = self.snapshot()
        with patch.object(module.os, 'replace', side_effect=OSError('replace failed')):
            with self.assertRaisesRegex(OSError, 'replace failed'):
                module.atomic_bytes(self.catalog_path, b'new content')
        self.assertEqual(self.snapshot(), before)


class SyncEntrypointTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('npm'), 'npm required for shell entrypoint test')
    def test_common_sync_stops_at_failed_converter_and_preserves_xlsx_command(self):
        package = json.loads((REPO / 'package.json').read_text(encoding='utf-8'))
        self.assertEqual(package['scripts']['sync:xlsx'], 'python3 lv/scripts/sync_xlsx.py')
        expected = ['lv/scripts/sync_catalog.py', 'lv/scripts/sync_xlsx.py',
                    'lv/scripts/publish_budget_estimates.py', 'lv/scripts/sync_annual_xlsx.py',
                    'lv/scripts/sync_csv_preview.py']
        self.assertEqual(package['scripts']['sync:csv'], 'python3 lv/scripts/sync_csv_preview.py')
        self.assertIn('lv/scripts/sync_csv_preview.py --allow-standby', package['scripts']['sync'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'package.json').write_text(json.dumps(package), encoding='utf-8')
            fake = root / 'python3'
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$SYNC_TEST_LOG"\n'
                            'if [ "$1" = "$SYNC_TEST_FAIL" ]; then exit 17; fi\n', encoding='utf-8')
            fake.chmod(0o700)
            log = root / 'calls.txt'
            for failure, called in [(expected[0], expected[:1]), (expected[1], expected[:2]),
                                    (expected[2], expected[:3]), (expected[3], expected[:4]),
                                    (expected[4], expected), ('', expected)]:
                log.unlink(missing_ok=True)
                env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ.get('PATH', ''),
                       'SYNC_TEST_LOG': str(log), 'SYNC_TEST_FAIL': failure}
                result = subprocess.run(['npm', 'run', 'sync', '--silent'], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=30)
                with self.subTest(failure=failure):
                    self.assertEqual(result.returncode, 17 if failure else 0)
                    self.assertEqual(log.read_text(encoding='utf-8').splitlines(), called)

    def test_pages_sync_precedes_build_and_artifact_without_continue_on_error(self):
        workflow = (REPO / '.github/workflows/pages.yml').read_text(encoding='utf-8')
        self.assertLess(workflow.index('- run: npm run sync'), workflow.index('- run: npm run build'))
        self.assertLess(workflow.index('- run: npm run build'), workflow.index('upload-pages-artifact'))
        self.assertNotIn('continue-on-error', workflow)
        self.assertIn('needs: build', workflow)
        self.assertIn('python3 -m unittest discover', workflow)


if __name__ == '__main__':
    unittest.main()

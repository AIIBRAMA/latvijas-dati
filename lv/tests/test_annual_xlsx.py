"""Offline workbook, standalone sync, and publication invariants for annual reports."""
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import sync_annual_xlsx as annual
sys.path.pop(0)

M = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
SAMPLE = next(iter(annual.RESOURCES))


def workbook(resource=SAMPLE, *, headers=None, changed_year=None, extra=False, duplicate=False):
    _, sheet, year, usual_headers = annual.info(resource)
    headers = usual_headers if headers is None else headers

    def text(address, value):
        return f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'

    first = ''.join(text(f'{chr(65 + i)}1', h) for i, h in enumerate(headers))
    year = str(year if changed_year is None else changed_year)
    second = (text('A2', year) + text('B2', 'Pārbaudes novads') + text('D2', '00000000123')
              + text('G2', 'Pamatdati') + text('K2', '001.0.') + '<c r="M2"><v>-23.5</v></c>')
    if extra:
        second += text('N2', 'Nezaudēt šo nezināmo vērtību')
    if duplicate:
        second += text('D2', 'Dublikāts')
    worksheet = (
        f'<worksheet xmlns="{M}"><sheetData><row r="1">{first}</row>'
        f'<row r="2">{second}</row><row r="3">{text("A3", year)}<c r="M3"><v>0</v></c></row>'
        f'<row r="4">{text("A4", year)}</row><row r="5"><c r="M5"/></row></sheetData></worksheet>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr('xl/workbook.xml', f'<workbook xmlns="{M}" xmlns:r="{R}"><sheets>'
                     f'<sheet name="{sheet}" r:id="rId1"/></sheets></workbook>')
        out.writestr('xl/_rels/workbook.xml.rels',
                     '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        out.writestr('xl/worksheets/sheet1.xml', worksheet)
    return buf.getvalue()


def catalog():
    return {'datasets': [
        {'id': annual.DATASET, 'license_id': 'CC0-1.0', 'organization': {'name': 'valsts-kase'},
         'resources': [{'id': resource_id, 'url': annual.info(resource_id)[0], 'format': 'XLSX'}
                       for resource_id in annual.RESOURCES]},
        {'id': 'approved-budget', 'resources': [
            {'id': 'approved', 'local_preview': {'sourceFormat': 'JSON', 'path': 'data/json/tames'}}]},
    ]}


class AnnualTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.catalog = self.root / 'public/data/catalog.json'
        self.catalog.parent.mkdir(parents=True)
        self.catalog.write_bytes(annual.json_bytes(catalog()))
        self.source = self.root / 'sources'
        self.source.mkdir()
        self.reviewed = {}
        patcher = patch.object(annual, 'REVIEWED_SOURCE', self.reviewed)
        patcher.start()
        self.addCleanup(patcher.stop)
        for rid in annual.RESOURCES:
            content = workbook(rid)
            (self.source / f'{rid}.xlsx').write_bytes(content)
            self.reviewed[rid] = (annual.sha(content),)

    def test_exact_original_amount_and_registration(self):
        parsed = annual.parse_workbook(workbook(), SAMPLE)
        self.assertEqual(parsed['total'], 3)
        self.assertEqual([row[-1] for row in parsed['rows']], [-23.5, 0, None])
        self.assertEqual(parsed['fields'][3]['dictionary'], ['00000000123'])
        self.assertEqual(parsed['fields'][10]['dictionary'], ['001.0.'])
        self.assertEqual(parsed['fields'][-1]['sourceId'], 'Summa_EUR')

    def test_observed_municipal_label_exception_is_reversible(self):
        rid = annual.MUNICIPAL_2025_HEADER
        parsed = annual.parse_workbook(workbook(rid), rid)
        self.assertEqual(parsed['fields'][1]['id'], 'Novads')
        self.assertEqual(parsed['fields'][1]['sourceId'], 'Ministrija')
        self.assertEqual(parsed['fields'][1]['dictionary'], ['Pārbaudes novads'])

    def test_reject_a_changed_year_header_or_stray_data(self):
        for bad in (workbook(changed_year=2024), workbook(headers=('Secret',)),
                    workbook(extra=True), workbook(duplicate=True)):
            with self.assertRaises(ValueError):
                annual.parse_workbook(bad, SAMPLE)

    def test_preserves_unrelated_budget_catalog_and_writes_all_twelve(self):
        previews = annual.sync(self.source, root=self.root)
        self.assertEqual(set(previews), set(annual.RESOURCES))
        doc = json.loads(self.catalog.read_bytes())
        self.assertEqual(doc['datasets'][1], catalog()['datasets'][1])
        for rid, item in previews.items():
            asset = (self.root / 'public' / item['path']).read_bytes()
            self.assertEqual(annual.sha(asset), item['sha256'])
            self.assertEqual(item['total'], 3)
            annual.validate_cached(rid, item, asset)

    def test_failure_before_first_release_preserves_approved_budget(self):
        before = self.catalog.read_bytes()
        with patch.object(annual, 'download', side_effect=TimeoutError('new annual source')),                 patch.object(annual, 'fetch_pages', return_value=before):
            result = annual.sync(root=self.root, allow_standby=True)
        self.assertEqual(result, {})
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertFalse((self.root / 'public' / annual.DIR).exists())

    def test_one_bad_workbook_restores_only_the_verified_full_previous_release(self):
        first = annual.sync(self.source, root=self.root)
        previous = self.catalog.read_bytes()
        self.catalog.write_bytes(annual.json_bytes(catalog()))

        def serve(path, limit):
            if path == 'data/catalog.json':
                return previous
            return (self.root / 'public' / path).read_bytes()

        with patch.object(annual, 'download', side_effect=TimeoutError('unavailable')),                 patch.object(annual, 'fetch_pages', side_effect=serve):
            recovered = annual.sync(root=self.root, allow_standby=True)
        self.assertEqual(set(recovered), set(first))
        self.assertTrue(all(recovered[rid]['snapshotFallback'] for rid in first))
        self.assertEqual([x['convertedAt'] for x in recovered.values()],
                         [x['convertedAt'] for x in first.values()])

    def test_suspicious_standby_never_fetches_another_host(self):
        annual.sync(self.source, root=self.root)
        previous = json.loads(self.catalog.read_bytes())
        previous['datasets'][0]['resources'][0]['local_preview']['path'] = 'https://other.example/a.json'
        self.catalog.write_bytes(annual.json_bytes(catalog()))
        before = self.catalog.read_bytes()
        with patch.object(annual, 'download', side_effect=TimeoutError('unavailable')),                 patch.object(annual, 'fetch_pages', return_value=annual.json_bytes(previous)) as net,                 self.assertRaisesRegex(ValueError, 'Invalid annual preview URL'):
            annual.sync(root=self.root, allow_standby=True)
        self.assertEqual(self.catalog.read_bytes(), before)
        net.assert_called_once_with('data/catalog.json', annual.MAX_CATALOG)

    def test_strict_malformed_workbook_does_not_publish_anything_new(self):
        rid = list(annual.RESOURCES)[-1]
        (self.source / f'{rid}.xlsx').write_bytes(b'not a workbook')
        self.reviewed[rid] = (annual.sha(b'not a workbook'),)
        before = self.catalog.read_bytes()
        with self.assertRaises(zipfile.BadZipFile):
            annual.sync(self.source, root=self.root, allow_standby=True)
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertFalse((self.root / 'public' / annual.DIR).exists())

    def test_same_schema_changed_source_is_not_auto_approved(self):
        original = self.catalog.read_bytes()
        (self.source / f'{SAMPLE}.xlsx').write_bytes(workbook(SAMPLE) + b'changed content')
        with self.assertRaisesRegex(ValueError, 'SHA-256 changed; independent review required'):
            annual.sync(self.source, root=self.root)
        self.assertEqual(self.catalog.read_bytes(), original)

    def test_repeat_same_reviewed_sources_does_not_conflict(self):
        first = annual.sync(self.source, root=self.root)
        again = annual.sync(self.source, root=self.root)
        self.assertEqual([a['sourceSha256'] for a in first.values()], [a['sourceSha256'] for a in again.values()])
        self.assertEqual(len(list((self.root / 'public' / annual.DIR).glob('*.json'))), len(annual.RESOURCES))


if __name__ == '__main__':
    unittest.main()

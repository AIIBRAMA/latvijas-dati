import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_treasury_monthly as m

CATALOG = {'datasets': []}
for rid, (profile, did, url, *_) in m.SOURCES.items():
    ds = next((d for d in CATALOG['datasets'] if d['id'] == did), None)
    if not ds:
        ds = {'id': did, 'organization': {'name': 'valsts-kase'}, 'license_id': 'CC0-1.0', 'resources': []}
        CATALOG['datasets'].append(ds)
    ds['resources'].append({'id': rid, 'url': url, 'format': 'XLSX'})

MODERN = next(k for k, v in m.SOURCES.items() if v[0] == m.COMPENSATION)
URI = m.NS['m']


class Tests(unittest.TestCase):
    def test_pins_cover_every_one_of_51_parts_and_311788_rows(self):
        self.assertEqual(set(m.SOURCES), set(m.NORMALIZED))
        for rid, spec in m.SOURCES.items():
            self.assertEqual(set(spec[-1]), set(m.NORMALIZED[rid]))
            self.assertEqual(sum(b[1] for b in spec[-1].values()),
                             sum(b[4] - b[3] + 1 for b in spec[-1].values()))
        self.assertEqual(sum(len(v[-1]) for v in m.SOURCES.values()), 51)
        self.assertEqual(sum(b[1] for v in m.SOURCES.values() for b in v[-1].values()), 311788)

    def test_formula_or_duplicate_coordinates_rejected(self):
        def rows(body):
            file = f'<worksheet xmlns="{URI}"><sheetData><row r="1">{body}</row></sheetData></worksheet>'
            return list(m.xml_rows(io.BytesIO(file.encode()), []))
        for bad in ('<c r="A1"><f>1+1</f><v>2</v></c>',
                    '<c r="A1"><v>0</v></c><c r="A1"><v>0</v></c>',
                    '<c r="A2"><v>0</v></c>', '<c r="A1" t="s"><v>1</v></c>'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rows(bad)
        self.assertEqual(rows('<c r="A1"><v>7.7188489999999996</v></c>'),
                         [(1, {0: ('n', '7.7188489999999996')})])

    def test_institution_annual_plans_cannot_be_mixed_with_actuals(self):
        v = [None] * 39
        v[:5] = ['2026', 'F260228', '28.02.2026', '#', '#']
        v[-13], v[-2], v[-1] = m.PLAN_TYPES[0], 'Euro', '-1.23456'
        m.validate_scope(m.COMPENSATION, 'AD', '2026', '#', v)
        for i, bad in ((1, 'F260229'), (2, '29.02.2026'), (3, '2'), (38, None), (37, 'USD')):
            altered = v[:]
            altered[i] = bad
            with self.subTest(i=i), self.assertRaises(ValueError):
                m.validate_scope(m.COMPENSATION, 'AD', '2026', '#', altered)
        with self.assertRaises(ValueError):
            m.validate_scope(m.COMPENSATION, 'AD', '2026', '2', v)

    def test_blanks_in_compensation_ekk_are_preserved_but_not_generalized(self):
        m.validate_scope(m.COMPENSATION, 'EKK', '2026', None, [None, 'K100', 'Vērtība'])
        for profile, cells in [(m.EXECUTION, [None, 'K100', 'Vērtība']),
                               (m.COMPENSATION, ['100', 'K100', 'Vērtība']),
                               (m.COMPENSATION, [None, 'K100', None])]:
            with self.assertRaises(ValueError):
                m.validate_scope(profile, 'EKK', '2026', None, cells)

    def test_raim_retains_original_has_no_known_currency(self):
        rid = next(k for k, v in m.SOURCES.items() if v[0] == m.RAIM)
        self.assertEqual(m.identity(rid)['reportScope'], {'from': '2009', 'through': '2025'})
        self.assertNotIn('currency', m.identity(rid))
        v = ['Rīga', '0010000', '1', '2', '0', '0', '2', '7.7188489999999996', '31.12.2013.']
        m.validate_scope(m.RAIM, 'Sheet1', None, None, v)
        for i, bad in ((1, '10000'), (8, '31.12.2026.'), (8, '2013-12-31')):
            altered = v[:]
            altered[i] = bad
            with self.assertRaises(ValueError):
                m.validate_scope(m.RAIM, 'Sheet1', None, None, altered)

    def test_first_outage_preserves_catalog_and_subsequent_mixed_group_fails(self):
        empty_catalog = m.json_bytes(CATALOG)
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, 'fresh', side_effect=TimeoutError):
            root = Path(tmp)
            cp = root / 'public/data/catalog.json'
            cp.parent.mkdir(parents=True)
            cp.write_bytes(empty_catalog)
            with patch.object(m, 'fetch_pages', return_value=empty_catalog):
                self.assertEqual(m.sync(root=root, allow_standby=True), {})
            self.assertEqual(cp.read_bytes(), empty_catalog)
            bad = json.loads(empty_catalog)
            selected = m.selected(bad)
            selected[MODERN]['local_preview'] = m.identity(MODERN)
            with patch.object(m, 'fetch_pages', return_value=m.json_bytes(bad)), self.assertRaises(ValueError):
                m.sync(root=root, allow_standby=True)
            self.assertEqual(cp.read_bytes(), empty_catalog)

    def test_unexpected_source_change_cannot_publish_during_standalone_run(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, 'download', return_value=b'new workbook'):
            root = Path(tmp)
            cp = root / 'public/data/catalog.json'
            cp.parent.mkdir(parents=True)
            before = m.json_bytes(CATALOG)
            cp.write_bytes(before)
            with self.assertRaisesRegex(ValueError, 'changed'):
                m.sync(root=root)
            self.assertEqual(cp.read_bytes(), before)

    def test_cross_source_prior_paths_rejected_before_fetch(self):
        bad = json.loads(m.json_bytes(CATALOG))
        rr = m.selected(bad)
        for rid, res in rr.items():
            parts = [m.pointer(rid, sid, '1' * 64) for sid in m.SOURCES[rid][-1]]
            res['local_preview'] = {**m.identity(rid), 'convertedAt': '2026-11-24T11:55:00+00:00',
                                    'reportSheets': parts, 'total': sum(p['total'] for p in parts)}
        r = next(iter(rr.values()))
        r['local_preview']['reportSheets'][0]['path'] = '../../other.json'
        with patch.object(m, 'fetch_pages', return_value=m.json_bytes(bad)) as fetch:
            with self.assertRaisesRegex(ValueError, 'pointer'):
                m.standby(m.selected(CATALOG))
            fetch.assert_called_once()

    def test_verified_prior_snapshot_retained_byte_for_byte(self):
        rid = next(k for k, v in m.SOURCES.items() if v[0] == m.RAIM)
        source = m.SOURCES[rid]
        sid = 'saistibas'
        time = '2026-11-24T11:55:00+00:00'
        table = {'test-only': 'validated by independent normalized digest'}
        blob = m.json_bytes({'schemaVersion': 1, 'resourceId': rid, 'reportSheet': sid,
                             'convertedAt': time, **m.identity(rid), 'sheets': [table]})
        p = m.pointer(rid, sid, m.sha(blob))
        prior = json.loads(m.json_bytes(CATALOG))
        for ds in prior['datasets']:
            for res in ds['resources']:
                if res['id'] == rid:
                    res['local_preview'] = {**m.identity(rid), 'convertedAt': time,
                                             'reportSheets': [p], 'total': p['total']}
        def fetch(path, limit):
            if path == 'data/catalog.json':
                return m.json_bytes(prior)
            self.assertEqual(path, p['path'])
            return blob
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, 'SOURCES', {rid: source}), \
                patch.object(m, 'NORMALIZED', {rid: {sid: m.sha(m.json_bytes(table))}}), \
                patch.object(m, 'fresh', side_effect=ValueError('upstream changed')), \
                patch.object(m, 'fetch_pages', side_effect=fetch):
            root = Path(tmp)
            cp = root / 'public/data/catalog.json'
            cp.parent.mkdir(parents=True)
            cp.write_bytes(m.json_bytes(CATALOG))
            result = m.sync(root=root, allow_standby=True)
            self.assertTrue(result[rid]['snapshotFallback'])
            self.assertEqual((root / 'public' / p['path']).read_bytes(), blob)
            self.assertEqual(result[rid]['convertedAt'], time)

"""Keep the public non-IUB CSV profile isolated from existing publishers."""
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sync_csv_preview import ReviewedSource, reviewed_resources, parse_csv, provenance, SOURCES


class OtherCsvTests(unittest.TestCase):
    def fixture(self, body='Gads,Kods\n2024,00060\n'):
        raw = body.encode()
        source = ReviewedSource('test-dataset-id', 'test-resource-id', 'test.csv',
                                hashlib.sha256(raw).hexdigest(), ('Gads','Kods'), 0, 1,
                                organization='test-publisher', publisher='Testa iestāde', delimiter=',')
        dataset = {'id': source.dataset_id, 'organization': {'name': source.organization},
                   'license_id': 'CC0-1.0', 'resources': [{'id': source.resource_id,
                                                          'url': source.url, 'format': 'CSV'}]}
        return raw, source, dataset

    def test_profile_retains_official_publisher_and_code(self):
        raw, spec, dataset = self.fixture()
        self.assertEqual(provenance(spec, 'now')['publisher'], 'Testa iestāde')
        sheet = parse_csv(raw, spec)
        self.assertEqual(sheet['fields'][1]['dictionary'], ['00060'])
        self.assertEqual(reviewed_resources({'datasets': [dataset]}, [spec])[spec.resource_id]['url'], spec.url)
        self.assertTrue(all(s.organization == 'iub' and s.delimiter == ';' for s in SOURCES))

    def test_profile_rejects_ineligible_catalog_mismatch(self):
        _raw, spec, ds = self.fixture()
        catalog = {'datasets': [ds]}
        ds['organization']['name'] = 'iub'
        with self.assertRaisesRegex(ValueError, 'publisher or license'):
            reviewed_resources(catalog, [spec])
        ds['organization']['name'] = spec.organization
        ds['license_id'] = 'CC-BY'
        with self.assertRaisesRegex(ValueError, 'publisher or license'):
            reviewed_resources(catalog, [spec])
        ds['license_id'] = 'CC0-1.0'
        ds['resources'][0]['url'] = 'https://example.test/not-the-source.csv'
        with self.assertRaisesRegex(ValueError, 'source address or format'):
            reviewed_resources(catalog, [spec])

    def test_quoted_delimiter_supported_and_width_checked(self):
        raw, spec, _ = self.fixture('Gads,Kods\n2024,"00,060"\n')
        self.assertEqual(parse_csv(raw, spec)['fields'][1]['dictionary'], ['00,060'])
        raw, spec, _ = self.fixture('Gads,Kods\n2024,00060,extra\n')
        with self.assertRaisesRegex(ValueError, 'width'):
            parse_csv(raw, spec)

    def test_reviewed_cp1257_title_keeps_bytes_and_validates_caption(self):
        caption = 'Mērījumu apkopojums ēkās'
        text = caption + ';\nGads;Kods\n2024;00060\n'
        raw = text.encode('cp1257')
        self.assertEqual(raw.decode('cp1257').encode('cp1257'), raw)
        _, spec, _ = self.fixture()
        spec = replace(spec, sha256=hashlib.sha256(raw).hexdigest(), delimiter=';',
                       encoding='cp1257', preamble=(caption, ''))
        output = parse_csv(raw, spec)
        self.assertEqual(output['sourceCaption'], caption)
        self.assertEqual(output['total'], 1)
        self.assertEqual(output['fields'][1]['dictionary'], ['00060'])
        with self.assertRaisesRegex(ValueError, 'title row changed'):
            parse_csv(raw, replace(spec, preamble=('wrong title', '')))
        with self.assertRaisesRegex(ValueError, 'Unsupported reviewed CSV'):
            parse_csv(raw, replace(spec, encoding='cp1252'))

"""Deterministic tests for the reviewed public JSON schema; no upstream calls."""
import io
import json
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import sync_budget_estimates as estimates


def record(**changes):
    row = {field: '' for field in estimates.SOURCE_FIELDS}
    row.update(gads='2026', vertiba='10000.00', iestade='Pārbaudes iestāde',
               iestades_kods='0069', funkcijas_kods='02100', resursu_avota_kods='01',
               saistibu_veida_kods='0000000000', tames_nr='P00126001', tips='IZDEVUMI',
               parakstits='23.12.2025')
    row.update(changes)
    return row


def payload(*records, ensure_ascii=False, **extra):
    return json.dumps({'api': 'valsts_budzeta_tames', 'dati': records, **extra},
                      ensure_ascii=ensure_ascii).encode('utf-8')


def decoded(sheet, row, key):
    index = next(i for i, f in enumerate(sheet['fields']) if f['id'] == key)
    value = sheet['rows'][row][index]
    return sheet['fields'][index]['dictionary'][value] if value is not None and 'dictionary' in sheet['fields'][index] else value


class FakeResponse(io.BytesIO):
    def __init__(self, body=b'{}', *, url=estimates.SOURCE_URL, status=200,
                 content_type='application/json; charset=UTF-8', length=None, encoding=None):
        super().__init__(body)
        self.url = url
        self.status = status
        self.headers = Message()
        if content_type is not None:
            self.headers['Content-Type'] = content_type
        if length is not None:
            self.headers['Content-Length'] = str(length)
        if encoding is not None:
            self.headers['Content-Encoding'] = encoding

    def geturl(self):
        return self.url


class EstimateParsingTests(unittest.TestCase):
    def test_real_shaped_response_keeps_codes_dates_and_numeric_amount(self):
        data = payload(record(), record(gads='2025', vertiba=' -17208.35 '),
                       record(vertiba='0.00', projekts=None), record(vertiba=''))
        sheet, = estimates.parse_budget_estimates(data)
        self.assertEqual(sheet['name'], 'Valsts budžeta tāmes')
        self.assertEqual(sheet['total'], 4)
        self.assertEqual(sheet['cachedFormulaCount'], 0)
        self.assertEqual(len(sheet['fields']), 25)
        self.assertEqual({f['id']: f['sourceId'] for f in sheet['fields'] if f['type'] == 'number'},
                         {'Gads': 'gads', 'Summa': 'vertiba'})
        self.assertEqual([decoded(sheet, i, 'Gads') for i in range(4)], [2026, 2025, 2026, 2026])
        self.assertEqual([decoded(sheet, i, 'Summa') for i in range(4)], [10000, -17208.35, 0, None])
        self.assertEqual(decoded(sheet, 0, 'iestades_kods'), '0069')
        self.assertEqual(decoded(sheet, 0, 'resursu_avota_kods'), '01')
        self.assertEqual(decoded(sheet, 0, 'saistibu_veida_kods'), '0000000000')
        self.assertEqual(decoded(sheet, 0, 'funkcijas_kods'), '02100')
        self.assertEqual(decoded(sheet, 0, 'parakstits'), '23.12.2025')
        self.assertEqual(decoded(sheet, 0, 'iestade'), 'Pārbaudes iestāde')
        self.assertEqual(decoded(sheet, 0, 'projekts'), '')
        self.assertIsNone(decoded(sheet, 2, 'projekts'))
        self.assertEqual(next(f for f in sheet['fields'] if f['id'] == 'iestades_kods')['dictionary'], ['0069'])

    def test_bounded_input_and_row_count(self):
        with patch.object(estimates, 'MAX_DOWNLOAD', 1):
            with self.assertRaisesRegex(ValueError, 'within the size limit'):
                estimates.parse_budget_estimates(payload(record()))
        with patch.object(estimates, 'MAX_ROWS', 1):
            with self.assertRaisesRegex(ValueError, 'row limit'):
                estimates.parse_budget_estimates(payload(record(), record()))

    def test_incomplete_or_unknown_schema_fails_closed(self):
        missing = record()
        del missing['gads']
        partial = payload(record(), filter={'gads': '2026'})
        duplicate = payload(record()).replace(b'"gads": "2026"', b'"gads": "2025", "gads": "2026"')
        cases = [
            (partial, 'Filtered data'),
            (payload(), 'missing or empty'),
            (payload(missing), 'schema changed'),
            (payload(record(new_column='new')), 'schema changed'),
            (payload(record(iestades_kods=69)), 'Expected budget-estimate text'),
            (payload(record(gads=True)), 'four-digit budget year'),
            (payload(record(vertiba='1 000,00')), 'finite budget amount'),
            (payload(record(vertiba='9007199254740992')), 'finite budget amount'),
            (payload(record(vertiba='1234567890123.0199')), 'lose numeric precision'),
            (payload(record(vertiba=float('nan'))), 'Non-finite JSON'),
            (payload(record(iestade='\udfff'), ensure_ascii=True), 'Invalid UTF-8 text'),
            (duplicate, 'Duplicate field'),
            (b'{"api":"different","dati":[]}', 'Unexpected'),
        ]
        for content, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                estimates.parse_budget_estimates(content)

    def test_cross_chunk_row_and_contiguous_integrity(self):
        # This valid row starts before the streaming buffer ends and finishes
        # after it. A second row verifies that columns/rows are not dropped.
        huge_prefix = b' ' * (128 * 1024 - 30)
        good = payload(record(projekts='Ā' * 300), record(vertiba='-1.25'))
        data = huge_prefix + good
        sheet, = estimates.parse_budget_estimates(data)
        self.assertEqual(sheet['total'], 2)
        self.assertEqual(decoded(sheet, 0, 'projekts'), 'Ā' * 300)
        self.assertEqual(decoded(sheet, 1, 'Summa'), -1.25)
        for incomplete in (data[:-20], data + b'{}', data[:-1] + b',"filter":{"gads":"2026"}}'):
            with self.subTest(ending=incomplete[-30:]), self.assertRaises(ValueError):
                estimates.parse_budget_estimates(incomplete)
        with patch.object(estimates, 'MAX_RECORD_CHARS', 128), self.assertRaisesRegex(ValueError, 'Oversized'):
            estimates.parse_budget_estimates(data)

    def test_empty_filter_is_equivalent_to_absent_filter(self):
        with_filter = payload(record(), filter={})
        self.assertEqual(estimates.parse_budget_estimates(with_filter),
                         estimates.parse_budget_estimates(payload(record())))


class DownloadTests(unittest.TestCase):
    def fetch(self, response):
        with patch.object(estimates.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = response
            result = estimates.download()
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, estimates.SOURCE_URL)
            self.assertEqual(request.get_header('Accept'), 'application/json')
            return result

    def test_official_endpoint_only_and_no_redirects(self):
        for url in ('https://other.example/api/v1/valsts_budzeta_tames',
                    estimates.SOURCE_URL.replace('https:', 'http:'),
                    estimates.SOURCE_URL + '?gads=%222026%22',
                    estimates.SOURCE_URL + '/extra'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                estimates.trusted_url(url)
        with self.assertRaisesRegex(ValueError, 'Redirect'):
            estimates.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example')
        with self.assertRaisesRegex(ValueError, 'exact unfiltered'):
            self.fetch(FakeResponse(url='https://other.example'))

    def test_status_encoding_content_and_length_are_checked(self):
        self.assertEqual(self.fetch(FakeResponse()), b'{}')
        for response, reason in [
            (FakeResponse(status=206), 'full HTTP 200'),
            (FakeResponse(content_type='text/html'), 'application/json'),
            (FakeResponse(encoding='gzip'), 'Unexpected content encoding'),
            (FakeResponse(length=3), 'truncated'),
        ]:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                self.fetch(response)
        with patch.object(estimates, 'MAX_DOWNLOAD', 1):
            for response in (FakeResponse(length=20), FakeResponse()):
                with self.assertRaisesRegex(ValueError, 'exceeds the size limit'):
                    self.fetch(response)


if __name__ == '__main__':
    unittest.main()

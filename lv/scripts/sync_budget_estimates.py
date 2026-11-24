"""Read the reviewed Valsts kase public budget-estimate API into local-preview sheets.

This is a build-time reader for one source, not a general JSON-to-table converter.
The official catalog publishes the dataset under CC0 1.0:
https://data.gov.lv/dati/lv/dataset/valsts-budzeta-tames
"""
import io
import json
import math
import re
import time
import urllib.request
from decimal import Decimal


DATASET = '0590c166-ab28-46b5-82e8-8f905295db4e'
RESOURCE_ID = '45368057-dfd7-4c56-9cac-5ca0e22ca086'
SOURCE_URL = 'https://opendata.kase.gov.lv/api/v1/valsts_budzeta_tames'
MAX_DOWNLOAD = 384 * 1024 * 1024
MAX_ROWS = 400_000
MAX_RECORD_CHARS = 1024 * 1024
MAX_TEXT_LENGTH = 16_384
MAX_SAFE_INTEGER = 2**53 - 1
READ_TIMEOUT = 30
DOWNLOAD_DEADLINE = 180
SOURCE_NAME = 'valsts_budzeta_tames'
SOURCE_FIELDS = (
    'gads', 'budzeta_tipa_kods', 'budzeta_tips', 'ministrijas_kods', 'ministrija',
    'iestades_kods', 'iestade', 'tames_nr', 'parakstits', 'progr_apaksprogr_kods',
    'progr_apaksprogramma', 'funkcijas_kods', 'funkcija', 'saistibu_veida_kods',
    'saistibu_veids', 'resursu_avota_kods', 'resursa_avots', 'projekta_kods', 'projekts',
    'tips', 'ekk_kods', 'ekk', 'vertiba', 'sak_budzets_kods', 'sakotnejais_budzets',
)
EXPECTED_FIELDS = set(SOURCE_FIELDS)
# Common preview filters and numeric-column renderer use these two names.
NUMERIC_LABELS = {'gads': 'Gads', 'vertiba': 'Summa'}
DECIMAL_STRING = re.compile(r'-?\d{1,16}(?:\.\d{1,12})?', re.ASCII)


def trusted_url(url):
    """Allow only the exact official endpoint, never a partial query or redirect."""
    if url != SOURCE_URL:
        raise ValueError('Budget estimates require the exact unfiltered official HTTPS source URL')
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect from the official budget-estimate source is not allowed')


def download(url=SOURCE_URL):
    """Download the unfiltered public API with an explicit time and size limit."""
    request = urllib.request.Request(trusted_url(url), headers={
        'Accept': 'application/json', 'Accept-Encoding': 'identity',
        'User-Agent': 'LatvijasDatiExplorer/1.1',
    })
    opener = urllib.request.build_opener(NoRedirect())
    deadline = time.monotonic() + DOWNLOAD_DEADLINE
    with opener.open(request, timeout=READ_TIMEOUT) as response:
        trusted_url(response.geturl())
        if response.status != 200:
            raise ValueError('Budget-estimate endpoint did not return a full HTTP 200 response')
        if response.headers.get_content_type() != 'application/json':
            raise ValueError('Budget-estimate endpoint did not return application/json')
        if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
            raise ValueError('Unexpected content encoding from the budget-estimate endpoint')
        length = response.headers.get('Content-Length')
        if length is not None:
            if not re.fullmatch(r'[0-9]{1,16}', length) or int(length) > MAX_DOWNLOAD:
                raise ValueError('Budget-estimate response exceeds the size limit or has invalid length')
            length = int(length)
        result = io.BytesIO()
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError('Budget-estimate download exceeded its time limit')
            chunk = response.read1(min(128 * 1024, MAX_DOWNLOAD - result.tell() + 1))
            if not chunk:
                break
            result.write(chunk)
            if result.tell() > MAX_DOWNLOAD:
                raise ValueError('Budget-estimate response exceeds the size limit')
        if length is not None and result.tell() != length:
            raise ValueError('Budget-estimate response was truncated')
    return result.getvalue()


def _object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f'Duplicate field {key!r} in budget-estimate JSON')
        obj[key] = value
    return obj


def _invalid_constant(constant):
    raise ValueError(f'Non-finite JSON number: {constant}')


def _year(value):
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{3}', value):
        return int(value)
    if type(value) is int and 1000 <= value <= 9999:
        return value
    raise ValueError('Expected a four-digit budget year')


def _amount(value):
    if isinstance(value, str):
        # The official API uses blank amounts and ASCII padding on negative
        # values. Preserve the distinction between absent and explicit zero.
        value = value.strip(' ')
        if not value:
            return None
        if DECIMAL_STRING.fullmatch(value):
            value = Decimal(value)
    elif type(value) is int:
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or abs(value) > MAX_SAFE_INTEGER:
        raise ValueError('Expected a finite budget amount in the browser-safe numeric range')
    if value == value.to_integral_value():
        return int(value)
    number = float(value)
    if not math.isfinite(number) or Decimal(str(number)) != value:
        raise ValueError('Budget amount would lose numeric precision in the browser')
    return number


class _Stream:
    """Bounded-buffer reader for individual values of the official JSON envelope."""

    def __init__(self, source):
        self.source = source
        self.decoder = json.JSONDecoder(parse_float=Decimal, parse_constant=_invalid_constant,
                                        object_pairs_hook=_object)
        self.buffer = ''
        self.pos = 0
        self.eof = False

    def refill(self):
        if self.eof:
            return
        self.buffer = self.buffer[self.pos:]
        self.pos = 0
        chunk = self.source.read(128 * 1024)
        self.eof = not chunk
        self.buffer += chunk

    def peek(self):
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos] in ' \t\r\n':
                self.pos += 1
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if self.eof:
                return ''
            self.refill()

    def take(self, expected):
        if self.peek() != expected:
            raise ValueError(f'Malformed budget-estimate JSON: expected {expected!r}')
        self.pos += 1

    def value(self, expected_opening):
        if self.peek() != expected_opening:
            raise ValueError('Unexpected budget-estimate JSON value')
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError as exc:
                if self.eof or len(self.buffer) - self.pos >= MAX_RECORD_CHARS:
                    raise ValueError('Invalid or oversized budget-estimate JSON value') from exc
                self.refill()
            else:
                if end - self.pos > MAX_RECORD_CHARS:
                    raise ValueError('Oversized budget-estimate JSON value')
                self.pos = end
                return value


def _records(content):
    """Yield records without holding parsed copies of the entire ~200 MiB source."""
    with io.TextIOWrapper(io.BytesIO(content), encoding='utf-8-sig') as source:
        stream = _Stream(source)
        stream.take('{')
        seen = set()
        if stream.peek() == '}':
            raise ValueError('Unexpected budget-estimate response envelope')
        while True:
            key = stream.value('"')
            if key not in {'api', 'dati', 'filter'} or key in seen:
                raise ValueError('Unexpected or duplicate field in budget-estimate response envelope')
            seen.add(key)
            stream.take(':')
            if key == 'api':
                if stream.value('"') != SOURCE_NAME:
                    raise ValueError('Unexpected budget-estimate response envelope')
            elif key == 'filter':
                if stream.peek() != '{' or stream.value('{') != {}:
                    raise ValueError('Filtered data cannot replace the full budget-estimate preview')
            else:
                stream.take('[')
                if stream.peek() != ']':
                    while True:
                        yield stream.value('{')
                        if stream.peek() == ']':
                            break
                        stream.take(',')
                stream.take(']')
            if stream.peek() == '}':
                break
            stream.take(',')
        stream.take('}')
        if stream.peek() or not {'api', 'dati'}.issubset(seen):
            raise ValueError('Unexpected budget-estimate response envelope')


def parse_budget_estimates(content):
    """Return one dictionary-encoded sheet from the full unfiltered JSON payload."""
    if not isinstance(content, bytes) or not content or len(content) > MAX_DOWNLOAD:
        raise ValueError('Budget-estimate data must be nonempty bytes within the size limit')
    fields, lookups = [], {}
    for source_id in SOURCE_FIELDS:
        if source_id in NUMERIC_LABELS:
            fields.append({'id': NUMERIC_LABELS[source_id], 'sourceId': source_id, 'type': 'number'})
        else:
            fields.append({'id': source_id, 'type': 'text', 'dictionary': []})
            lookups[source_id] = {}

    rows = []
    for index, record in enumerate(_records(content), 1):
        if index > MAX_ROWS:
            raise ValueError('Budget-estimate records exceed the row limit')
        if set(record) != EXPECTED_FIELDS:
            raise ValueError(f'Treasury budget-estimate schema changed at row {index}; manual review required')
        row = []
        for column, source_id in enumerate(SOURCE_FIELDS):
            value = record[source_id]
            if source_id == 'gads':
                row.append(_year(value))
            elif source_id == 'vertiba':
                row.append(_amount(value))
            elif value is None:
                row.append(None)
            else:
                # Codes are strings in the official source. Refuse an integer instead
                # of assuming its leading zeroes were never specified.
                if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH:
                    raise ValueError(f'Expected budget-estimate text in {source_id} at row {index}')
                try:
                    value.encode('utf-8')
                except UnicodeEncodeError as exc:
                    raise ValueError(f'Invalid UTF-8 text in {source_id} at row {index}') from exc
                dictionary = fields[column]['dictionary']
                lookup = lookups[source_id]
                encoded = lookup.get(value)
                if encoded is None:
                    encoded = len(dictionary)
                    lookup[value] = encoded
                    dictionary.append(value)
                row.append(encoded)
        rows.append(row)

    if not rows:
        raise ValueError('Budget-estimate records are missing or empty')
    return [{'name': 'Valsts budžeta tāmes', 'fields': fields, 'rows': rows,
             'total': len(rows), 'cachedFormulaCount': 0}]

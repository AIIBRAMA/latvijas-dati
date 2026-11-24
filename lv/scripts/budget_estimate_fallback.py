"""Verify complete, normalized Valsts kase budget previews during upstream outages."""
import gzip
import hashlib
import math
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

from sync_budget_estimates import (
    DATASET, RESOURCE_ID, SOURCE_URL, MAX_ROWS, MAX_SAFE_INTEGER, MAX_TEXT_LENGTH,
    NUMERIC_LABELS, SOURCE_FIELDS, NoRedirect,
)

PAGES_URL = 'https://aiibrama.github.io/latvijas-dati/'
MAX_CATALOG = 20 * 1024 * 1024
MAX_PREVIEW = 24 * 1024 * 1024
MAX_PACKED = 8 * 1024 * 1024
RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def transient(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_HTTP
    if isinstance(exc, urllib.error.URLError):
        exc = exc.reason
    return isinstance(exc, (TimeoutError, ConnectionError)) or (
        isinstance(exc, socket.gaierror) and exc.errno == socket.EAI_AGAIN
    )


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Budget snapshot is missing a timestamp')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Budget snapshot has an invalid timestamp')
    return parsed


def require_digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Budget snapshot has an invalid checksum')
    return value


def validate_payload(payload, manifest, partition):
    headers = {'schemaVersion': 1, 'resourceId': RESOURCE_ID, 'sourceFormat': 'JSON',
               'sourceUrl': SOURCE_URL, 'sourceSha256': manifest['sourceSha256'],
               'convertedAt': manifest['convertedAt']}
    if any(type(payload.get(k)) is not type(v) or payload[k] != v for k, v in headers.items()):
        raise ValueError('Budget snapshot has an inconsistent provenance')
    sheets = payload.get('sheets')
    if not isinstance(sheets, list) or len(sheets) != 1:
        raise ValueError('Budget snapshot must contain one normalized table')
    sheet = sheets[0]
    if sheet.get('name') != 'Valsts budžeta tāmes' or sheet.get('cachedFormulaCount') != 0:
        raise ValueError('Budget snapshot table identity does not match')
    fields, rows = sheet.get('fields'), sheet.get('rows')
    if not isinstance(fields, list) or [f.get('id') for f in fields] != [
        NUMERIC_LABELS.get(key, key) for key in SOURCE_FIELDS
    ]:
        raise ValueError('Budget snapshot has different fields')
    if not isinstance(rows, list) or len(rows) != partition['total'] or sheet.get('total') != len(rows):
        raise ValueError('Budget snapshot has inconsistent row counts')
    lookups = []
    for field, key in zip(fields, SOURCE_FIELDS):
        is_num = key in NUMERIC_LABELS
        if field.get('type') != ('number' if is_num else 'text') or (
            is_num and ('dictionary' in field or field.get('sourceId') != key)
        ):
            raise ValueError('Budget snapshot field type does not match')
        if not is_num:
            dictionary = field.get('dictionary')
            if not isinstance(dictionary, list) or any(
                not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH for value in dictionary
            ):
                raise ValueError('Budget snapshot has an invalid text dictionary')
            lookups.append((len(dictionary), key))
        else:
            lookups.append((None, key))
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ValueError('Budget snapshot has an incomplete row')
        for value, (size, key) in zip(row, lookups):
            if key == 'gads':
                ok = type(value) is int and value == int(partition['label'])
            elif value is None:
                ok = True
            elif key == 'vertiba':
                ok = type(value) in (int, float) and abs(value) <= MAX_SAFE_INTEGER and math.isfinite(value)
            else:
                ok = type(value) is int and 0 <= value < size
            if not ok:
                raise ValueError('Budget snapshot row has an invalid value or year')


def parse_json(value):
    import json

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError('Duplicate key in budget snapshot JSON')
            result[key] = item
        return result

    def constant(_):
        raise ValueError('Non-finite number in budget snapshot JSON')

    return json.loads(value, object_pairs_hook=unique, parse_constant=constant)


def validate_snapshot(manifest, read_part):
    if manifest.get('sourceUrl') != SOURCE_URL or manifest.get('sourceFormat') != 'JSON':
        raise ValueError('Budget snapshot is not from the reviewed official source')
    source_sha = require_digest(manifest.get('sourceSha256'))
    checked = timestamp(manifest.get('sourceCheckedAt'))
    if checked < timestamp(manifest.get('convertedAt')):
        raise ValueError('Budget snapshot was checked before being converted')
    partitions = manifest.get('partitions')
    if not isinstance(partitions, list) or not 0 < len(partitions) <= 15:
        raise ValueError('Budget snapshot has an invalid partition count')
    results, encountered_years, total = [], set(), 0
    for part in partitions:
        year = part.get('label')
        if not isinstance(year, str) or not re.fullmatch(r'[0-9]{4}', year) or (
            not 1900 <= int(year) <= 2200 or year in encountered_years
        ):
            raise ValueError('Budget snapshot has an invalid or duplicate year')
        encountered_years.add(year)
        expected_path = f'data/json/{RESOURCE_ID}-v1-{source_sha[:16]}-{year}.json'
        if part.get('path') != expected_path:
            raise ValueError('Budget snapshot has an unexpected partition path')
        if type(part.get('total')) is not int or not 0 < part['total'] <= MAX_ROWS:
            raise ValueError('Budget snapshot has an invalid partition row count')
        total += part['total']
        digest = require_digest(part.get('sha256'))
        data = read_part(part)
        if len(data) > MAX_PREVIEW or sha256(data) != digest:
            raise ValueError('Budget snapshot partition failed checksum or size verification')
        validate_payload(parse_json(data), manifest, part)
        results.append((expected_path, data))
    if type(manifest.get('total')) is not int or not 0 < total <= MAX_ROWS or total != manifest['total']:
        raise ValueError('Budget snapshot total does not match its year partitions')
    preview = {key: manifest[key] for key in ('sourceFormat', 'sourceUrl', 'sourceSha256',
                                               'sourceCheckedAt', 'convertedAt', 'total')}
    preview['partitions'] = [{key: part[key] for key in ('label', 'path', 'total', 'sha256')}
                             for part in partitions]
    preview['snapshotFallback'] = True
    return preview, results


def bounded_read(handle, limit):
    data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Budget snapshot exceeds the size limit')
    return data


def load_seed(directory):
    with (directory / 'manifest.json').open('rb') as handle:
        manifest = parse_json(bounded_read(handle, 16 * 1024))

    def read_part(part):
        target = directory / (PurePosixPath(part['path']).name + '.gz')
        with target.open('rb') as handle:
            compressed = bounded_read(handle, MAX_PACKED)
        if sha256(compressed) != require_digest(part.get('compressedSha256')):
            raise ValueError('Budget snapshot compressed checksum does not match')
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
            return bounded_read(handle, MAX_PREVIEW)

    return validate_snapshot(manifest, read_part)


def fetch_pages(path, limit):
    url = PAGES_URL + path
    request = urllib.request.Request(url, headers={'Accept': 'application/json',
                                                   'Accept-Encoding': 'identity',
                                                   'Cache-Control': 'no-cache'})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=5) as response:
        if (response.geturl() != url or response.status != 200 or
                response.headers.get_content_type() != 'application/json' or
                response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
            raise ValueError('Unrecognized response from the published budget snapshot')
        return bounded_read(response, limit)


def load_previous(baseline):
    try:
        catalog = parse_json(fetch_pages('data/catalog.json', MAX_CATALOG))
        datasets = [item for item in catalog['datasets'] if item.get('id') == DATASET]
        if len(datasets) != 1:
            return None
        resources = [item for item in datasets[0]['resources'] if item.get('id') == RESOURCE_ID]
        if len(resources) != 1 or resources[0].get('url') != SOURCE_URL:
            return None
        prior = resources[0].get('local_preview')
        if not prior or 'sourceCheckedAt' not in prior:
            return None
        if timestamp(prior['sourceCheckedAt']) <= timestamp(baseline['sourceCheckedAt']):
            return None
        return validate_snapshot(prior, lambda part: fetch_pages(part['path'], MAX_PREVIEW))
    except urllib.error.HTTPError as exc:
        if exc.code == 404 or transient(exc):
            return None
        raise
    except OSError as exc:
        if transient(exc):
            return None
        raise

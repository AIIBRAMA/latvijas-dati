"""Convert explicitly reviewed, aggregate CSV files to the local preview format.

Only the reviewed public bytes are eligible for republication. A changed source
requires fresh review, but never removes an existing preview or changes the live
DataStore, XLSX or JSON publication paths. Use one sync process per checkout.
"""
import argparse
import csv
import hashlib
import io
import json
import unicodedata
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from budget_estimate_fallback import MAX_CATALOG, fetch_pages, parse_json, require_digest, timestamp, transient
from publish_budget_estimates import atomic_bytes, exactly_one, json_bytes

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE = 1024 * 1024
MAX_PREVIEW = 2 * 1024 * 1024
MAX_ROWS = 5_000
MAX_COLUMNS = 32
MAX_CELL = 256


@dataclass(frozen=True)
class ReviewedSource:
    dataset_id: str
    resource_id: str
    slug: str
    sha256: str
    headers: tuple[str, ...]
    empty_tail_columns: int
    row_count: int
    table_sha256: str | None = None
    organization: str = 'iub'
    publisher: str = 'Iepirkumu uzraudzības birojs'
    delimiter: str = ';'
    encoding: str = 'utf-8-sig'
    preamble: tuple[str, ...] | None = None

    @property
    def url(self):
        return (f'https://data.gov.lv/dati/dataset/{self.dataset_id}'
                f'/resource/{self.resource_id}/download/{self.slug}')


SOURCES = (
    ReviewedSource(
        '51c57e13-312c-44e7-98b6-4bd26802e0e7', 'da897dfc-5b65-40c6-a8c8-d4ca530fa411',
        'pasttju_finanstie_2019.g.1.-4.cet.csv',
        'a057384f4b1b02dcf2604d901de0c65e8bbe8fbcb9a7e7f6b8a10308eebe3f6a',
        ('Gads', 'Ceturksnis', 'Mēnesis',
         'Paziņojums par finansējuma saņēmēja iepirkuma procedūru (skaits)',
         'Paziņojums par finansējuma saņēmēja iepirkuma procedūras pārtraukšanu vai grozījumiem (skaits)',
         'Paziņojums par iepirkuma procedūras rezultātiem (skaits)',
         'Rezultātu paziņojumos norādītā līgumcena (EUR bez PVN)'),
        5, 48, 'c255aca1151c7c5e2bde86453cb6cc9d69705172d442f2a3d4a4e9616ebc6474',
    ),
    ReviewedSource(
        '492363ea-1545-4879-a241-5ce674258d57', '7f70b0fe-835c-4682-9306-66f64f757fba',
        'publikaciju-statistika-izsludinasana-pil-2021-1-cet.csv',
        '1fbb91c24943f496ff90b615ea85b25910073d7258ddbea6dc5a9ef43fd15006',
        ('Gads', 'Ce-turksnis', 'Mēnesis', 'Iepirkuma veids', 'Pēc līgum-cenu sliekšņa',
         'Iepriek-šējais informa-tīvais paziņo-jums (skaits)',
         'Paziņo-jums par plānoto līgumu 9. panta kārtībā (skaits)',
         'Paziņo-jums par metu konkursu (skaits)', 'Paziņojums par līgumu (skaits)',
         'Paziņo-jums par sociāla-jiem un citiem īpašiem pakalpo-jumiem - iepriek-šējais informa-tīvais paziņo-jums (skaits)',
         'Paziņo-jums par sociāla-jiem un citiem īpašiem pakalpo-jumiem - paziņo-jums par līgumu (skaits)',
         'Paziņo-jums par izmai-ņām vai papildu informā-ciju (skaits)'),
        3, 351, '3eab5f4b1f5cfc0e1fd02b23892c8fe10b6040b4ab743798471343e82a2bf0dc',
    ),
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SourceChanged(ValueError):
    """The known public source no longer matches the reviewed bytes."""


def download(source):
    req = urllib.request.Request(source.url, headers={'User-Agent': 'LatvijasDatiExplorer/1.1'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
        if response.status != 200 or response.headers.get_content_type() != 'text/csv':
            raise ValueError('Reviewed CSV endpoint returned an unexpected response')
        return response.read(MAX_SOURCE + 1)


def validate_text(value, limit):
    if len(value) > limit:
        raise ValueError('CSV text limit exceeded')
    if any(unicodedata.category(c) in {'Cc', 'Cf'} and c not in '\r\n\t' for c in value):
        raise ValueError('CSV contains an unsupported control character')


def parse_csv(content, source):
    if len(content) > MAX_SOURCE:
        raise ValueError('CSV byte limit exceeded')
    if hashlib.sha256(content).hexdigest() != source.sha256:
        raise SourceChanged(f'Reviewed CSV bytes changed; source requires review: {source.resource_id}')
    if source.encoding not in ('utf-8-sig', 'cp1257') or source.delimiter not in (';', ',', '\t'):
        raise ValueError('Unsupported reviewed CSV encoding or delimiter')
    text = content.decode(source.encoding, errors='strict')
    raw = csv.reader(io.StringIO(text, newline=''), delimiter=source.delimiter, strict=True)
    if source.preamble is not None:
        if (not source.preamble or not source.preamble[0] or len(source.preamble) > MAX_COLUMNS
                or any(source.preamble[1:]) or tuple(next(raw, [])) != source.preamble):
            raise ValueError('Reviewed CSV title row changed')
        validate_text(source.preamble[0], MAX_CELL)
    header = next(raw, [])
    width = len(source.headers)
    if not 1 < width <= MAX_COLUMNS or len(header) > MAX_COLUMNS:
        raise ValueError('CSV column limit exceeded')
    expected = [*source.headers, *([''] * source.empty_tail_columns)]
    if header != expected:
        raise ValueError('Reviewed CSV header layout changed')
    normalized = [unicodedata.normalize('NFKC', value).strip().casefold() for value in source.headers]
    if any(not value for value in normalized) or len(set(normalized)) != width:
        raise ValueError('CSV headers must be unique after normalization')
    for label in source.headers:
        validate_text(label, MAX_CELL)

    rows = []
    dictionaries = [[] for _ in source.headers]
    lookups = [{} for _ in source.headers]
    for row_number, raw_row in enumerate(raw, 2):
        if row_number > MAX_ROWS + 1:
            raise ValueError('CSV record limit exceeded')
        if not raw_row:
            continue
        if len(raw_row) != len(expected):
            raise ValueError(f'CSV record {row_number} width does not match its header')
        if any(raw_row[width:]):
            raise ValueError(f'CSV record {row_number} has data in an unlabelled column')
        if not any(raw_row):
            continue
        row = []
        for i, value in enumerate(raw_row[:width]):
            validate_text(value, MAX_CELL)
            if value == '':
                row.append(None)
                continue
            if value not in lookups[i]:
                lookups[i][value] = len(dictionaries[i])
                dictionaries[i].append(value)
            row.append(lookups[i][value])
        rows.append(row)
    if not rows or len(rows) != source.row_count:
        raise ValueError('Reviewed CSV record count changed')
    sheet = {
        'name': 'Dati',
        'fields': [{'id': name, 'type': 'text', 'dictionary': dictionary}
                   for name, dictionary in zip(source.headers, dictionaries)],
        'rows': rows, 'total': len(rows), 'cachedFormulaCount': 0,
        **({'sourceCaption': source.preamble[0]} if source.preamble is not None else {}),
    }
    if source.table_sha256 is not None and sha256(json_bytes(sheet)) != source.table_sha256:
        raise ValueError('Reviewed CSV table digest differs from the expected conversion')
    return sheet


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def reviewed_resources(catalog, sources):
    selected = {}
    for source in sources:
        dataset = exactly_one(catalog['datasets'], 'id', source.dataset_id, 'CSV dataset')
        resource = exactly_one(dataset['resources'], 'id', source.resource_id, 'CSV resource')
        if (dataset.get('license_id') not in ('CC0-1.0', 'cc-zero') or dataset.get('private', False)
                or (dataset.get('organization') or {}).get('name') != source.organization):
            raise ValueError(f'Reviewed CSV publisher or license changed: {source.resource_id}')
        if resource.get('url') != source.url or resource.get('format') != 'CSV':
            raise ValueError(f'Reviewed CSV source address or format changed: {source.resource_id}')
        existing = resource.get('local_preview')
        if existing and existing.get('sourceFormat') != 'CSV':
            raise ValueError(f'Will not replace another preview type: {source.resource_id}')
        selected[source.resource_id] = resource
    return selected


def preview_path(source):
    return f'data/csv/{source.resource_id}-v1-{source.sha256}.json'


def provenance(source, converted_at):
    return {'sourceUrl': source.url, 'sourceFormat': 'CSV', 'sourceSha256': source.sha256,
            'convertedAt': converted_at, 'licenseId': 'CC0-1.0', 'publisher': source.publisher}


def prepare(selected, source_dir, sources, *, whole_group=False):
    """Build all candidate snapshots in memory before writing anything."""
    prepared = []
    for source in sources:
        resource = selected[source.resource_id]
        if not whole_group and resource.get('datastore_active') and not resource.get('local_preview'):
            continue
        if source_dir is not None:
            with (source_dir / f'{source.resource_id}.csv').open('rb') as handle:
                content = handle.read(MAX_SOURCE + 1)
        else:
            content = download(source)
        sheet = parse_csv(content, source)
        converted_at = datetime.now(timezone.utc).isoformat()
        path = preview_path(source)
        fields = provenance(source, converted_at)
        payload = {'schemaVersion': 1, 'resourceId': source.resource_id, **fields, 'sheets': [sheet]}
        if len(json_bytes(payload)) > MAX_PREVIEW:
            raise ValueError('CSV derived table exceeds its size limit')
        prepared.append((resource, path, payload, fields, sheet['total']))
    return prepared


def obtain_cached(selected, sources):
    previous = parse_json(fetch_pages('data/catalog.json', MAX_CATALOG))
    prior_resources = reviewed_resources(previous, sources)
    prior = {rid: r['local_preview'] for rid, r in prior_resources.items() if r.get('local_preview')}
    if not prior:
        if any(r.get('local_preview') for r in selected.values()):
            raise ValueError('Existing CSV previews cannot be verified in the published catalogue')
        return []  # First launch only: published catalogue demonstrably has neither preview.
    if set(prior) != set(selected):
        raise ValueError('Published CSV standby is incomplete; refusing partial preview coverage')
    prepared = []
    for source in sources:
        old = prior[source.resource_id]
        path = preview_path(source)
        if not isinstance(old, dict) or old.get('path') != path or old.get('total') != source.row_count:
            raise ValueError('Published CSV standby has an invalid path or row count')
        timestamp(old.get('convertedAt'))
        fields = provenance(source, old['convertedAt'])
        if any(old.get(k) != v for k, v in fields.items()):
            raise ValueError('Published CSV standby has unexpected provenance')
        digest = require_digest(old.get('sha256'))
        encoded = fetch_pages(path, MAX_PREVIEW)
        if sha256(encoded) != digest:
            raise ValueError('Published CSV standby has an invalid payload checksum')
        payload = parse_json(encoded)
        sheets = payload.get('sheets')
        if (not isinstance(sheets, list) or len(sheets) != 1 or not source.table_sha256 or
                sha256(json_bytes(sheets[0])) != source.table_sha256 or
                json_bytes({'schemaVersion': 1, 'resourceId': source.resource_id, **fields, 'sheets': sheets}) != encoded):
            raise ValueError('Published CSV standby does not match the independently reviewed table')
        prepared.append((selected[source.resource_id], path, payload, fields, source.row_count))
    return prepared


def sync(root, source_dir=None, *, sources=SOURCES, allow_standby=False):
    public = root / 'public'
    catalog_path = public / 'data/catalog.json'
    catalog = json.loads(catalog_path.read_bytes())
    selected = reviewed_resources(catalog, sources)
    fallback = False
    try:
        prepared = prepare(selected, source_dir, sources, whole_group=allow_standby)
    except (OSError, SourceChanged) as exc:
        if not allow_standby or source_dir is not None or not (isinstance(exc, SourceChanged) or transient(exc)):
            raise
        fallback_reason = 'source-changed' if isinstance(exc, SourceChanged) else 'source-unavailable'
        print(f'::warning::Reviewed CSV sources not updated ({fallback_reason}): {exc}', flush=True)
        prepared = obtain_cached(selected, sources)
        fallback = True
        if not prepared:
            print('::warning::No previously published CSV previews; continuing without this first release.', flush=True)
    # Existing content-addressed targets with matching data keep their time stamp.
    # Refuse to overwrite an unexpected file identity or a manually corrupted copy.
    writes = []
    for resource, path, payload, fields, total in prepared:
        target = public / path
        if target.exists():
            previous = json.loads(target.read_bytes())
            previous_time = previous.get('convertedAt')
            if not isinstance(previous_time, str) or not previous_time:
                raise ValueError(f'Existing CSV snapshot missing provenance: {resource["id"]}')
            if not fallback:
                payload['convertedAt'] = fields['convertedAt'] = previous_time
            if previous != payload:
                raise ValueError(f'Existing CSV snapshot differs from reviewed contents: {resource["id"]}')
        else:
            writes.append((target, json_bytes(payload)))
        resource['local_preview'] = {'path': path, **fields, 'total': total, 'sha256': sha256(json_bytes(payload))}
        if fallback:
            resource['local_preview']['snapshotFallback'] = True
            resource['local_preview']['snapshotFallbackReason'] = fallback_reason
    for target, content in writes:
        atomic_bytes(target, content)
    if prepared:
        atomic_bytes(catalog_path, json_bytes(catalog))
    return [(resource['id'], total) for resource, _, _, _, total in prepared]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, help='Use reviewed CSV files named RESOURCE_ID.csv')
    parser.add_argument('--allow-standby', action='store_true', help='Allow both verified published previews during an outage')
    args = parser.parse_args()
    for resource_id, rows in sync(ROOT, args.source_dir, allow_standby=args.allow_standby):
        print(f'{resource_id}: {rows} reviewed CSV rows', flush=True)


if __name__ == '__main__':
    main()

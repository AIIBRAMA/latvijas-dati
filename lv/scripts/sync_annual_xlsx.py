"""Publish a reviewed set of twelve Treasury annual reports; no workbook code is executed."""
import argparse
import hashlib
import io
import json
import math
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from budget_estimate_fallback import MAX_CATALOG, fetch_pages, parse_json, timestamp
from publish_budget_estimates import atomic_bytes, cleanup_created, json_bytes
from sync_xlsx import NS, REL, cell_value, col_index, download

ROOT = Path(__file__).resolve().parents[1]
DATASET = 'c4db2159-7852-4551-bd59-46d92cd74b12'
SCHEMA = 'treasury-annual-v1'
DIR = 'data/annual-xlsx'
MAX_ARCHIVE = 8 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_PREVIEW = 12 * 1024 * 1024
MAX_ROWS = 150000
MAX_TEXT = 4096
MAX_SAFE_INTEGER = 2**53 - 1

# Resource ID, exact official filename stem, exact reviewed workbook sheet.
RESOURCES = {
    '48655b77-67ce-4a73-b9b1-aca1991331bb': ('2025_2_pb_ad', 'Report 1'),
    '7f95a16c-d46e-42b1-be7d-7b2f246c61e2': ('2025_2_sb_ad', 'Report 1'),
    '007c52c5-37f6-4853-8938-bbc2b0377fb3': ('2025_2_zd_ad', 'Report 1'),
    '26c433ab-4586-4686-9aba-1bd40a8d8d4b': ('2025_2_dnaf_ad', '2_DNAF_Min'),
    'bd0aa72f-700b-499c-a0f2-38f50248e50d': ('2025_2_pb_pasv_ad', 'Report 1'),
    '33daad60-2455-4459-97be-226c9cf493aa': ('2025_2_zd_pasv_ad', '2ZD_Pasv'),
    'bc290f5d-9aad-40b5-aca5-1ed8e2d3c39f': ('2024_2_pb_ad', '2024'),
    'baa32f0e-bed5-465e-8f8a-aada435664e0': ('2024_2_sb_ad', '2024'),
    'eec434b6-cfae-4612-a970-0db8a5e43fe3': ('2024_2_zd_ad', 'ZD_2024'),
    'e4e5b2bd-5b3e-4fb8-bb57-7ae73048ceef': ('2024_2_dnaf_ad', '2024'),
    '23702889-ed10-46df-a1e2-9bc716707502': ('2024_2_pb_pasv_ad', '2024'),
    '5e0a0a4c-bf22-4243-9621-934798e6c663': ('2024_2_zd_pasv_ad', '2ZD_Pasv_2024'),
}
# Digests of complete official workbooks reviewed for schema, publication and EUR sums.
# First entry is the current approved source; retain old validated digests only
# if they should remain eligible as a clearly dated prior publication.
REVIEWED_SOURCE = {
    '48655b77-67ce-4a73-b9b1-aca1991331bb': ('010a9115351f2de86ca95f29b0a00fa14a03d1f8db2fc3b600dea0187b1e67c9',),
    '7f95a16c-d46e-42b1-be7d-7b2f246c61e2': ('218d686f1c3b779e413e15dfc98a52763b3f683a2cb073475ccdbee6a75a7b08',),
    '007c52c5-37f6-4853-8938-bbc2b0377fb3': ('304fe910af9218b88b1cf300ed96fbbe522954b68164504aac5cb4d7422e68da',),
    '26c433ab-4586-4686-9aba-1bd40a8d8d4b': ('8526f4e3b59fda4fa5aa3d42993dfaa0efd1836d848acdde4f7f692d792e4973',),
    'bd0aa72f-700b-499c-a0f2-38f50248e50d': ('9c81ff31741d6dcb63142d8f12de6afd5ff2dd5bc8c278058fcd315fb969ffbf',),
    '33daad60-2455-4459-97be-226c9cf493aa': ('7319b3a2599a48fcf39af295136f7e74c0c124ec86f9da4a078c56ba0bc3ac1a',),
    'bc290f5d-9aad-40b5-aca5-1ed8e2d3c39f': ('dfc9e256cd0c937b1addf2247d5687ff1d4ebf35c72ff86f2222a07bd1e164a1',),
    'baa32f0e-bed5-465e-8f8a-aada435664e0': ('3276c6b3af4178bbf29199b5bf05c9833dfa6098912c25f2a928b6ae94b29a8d',),
    'eec434b6-cfae-4612-a970-0db8a5e43fe3': ('8eb060ee15e8d0ebdd324dec0518babc643d725fbfe4783c88156f90e742457d',),
    'e4e5b2bd-5b3e-4fb8-bb57-7ae73048ceef': ('c27fafb2e05f5461d8842738c9ea9cfbaa699fad3da26817c9ccd4d304f70c46',),
    '23702889-ed10-46df-a1e2-9bc716707502': ('e6e93403106ace4eeecf5e527b49008becff7379bf481132980ffde15714db44',),
    '5e0a0a4c-bf22-4243-9621-934798e6c663': ('3fb3fd0f5b8a0905ed0141427d5420fdd02ccaef0df34ac424480d0c36b89564',),
}
# The 2025 municipal main-budget workbook labels its municipality column
# 'Ministrija' despite every row and the source metadata describing municipalities.
MUNICIPAL_2025_HEADER = 'bd0aa72f-700b-499c-a0f2-38f50248e50d'
SUBSEQUENT_COLUMNS = ('Iestade', 'Iestades_Reg_Nr', 'Budzets_Veidlapas_nosaukums',
                      'Programma_Apaksprogramma', 'Tips', 'Funkcija_zemakais', 'Funkcija_Liela',
                      'ien_izd', 'EKK', 'EKK_nosaukums', 'Summa_EUR')


def info(resource_id):
    file, sheet = RESOURCES[resource_id]
    headers = ('Gads', 'Novads' if '_pasv_' in file and resource_id != MUNICIPAL_2025_HEADER else 'Ministrija',
               *SUBSEQUENT_COLUMNS)
    return (f'https://data.gov.lv/dati/dataset/{DATASET}/resource/{resource_id}/download/{file}.xlsx',
            sheet, int(file[:4]), headers)


def preview_fields(resource_id, headers):
    fields = [*headers[:-1], 'Summa']
    if resource_id == MUNICIPAL_2025_HEADER:
        fields[1] = 'Novads'
    return fields


def sha(data):
    return hashlib.sha256(data).hexdigest()


def exact_amount(cell, strings):
    if cell is None:
        return None
    value = cell_value(cell, strings)
    if value is None or value == '':
        return None
    if type(value) not in (int, float) or cell.get('t', 'n') != 'n':
        raise ValueError('Annual report sum must be an exact numeric amount from the workbook')
    try:
        exact = Decimal(cell.find('m:v', NS).text)
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError('Invalid annual report sum') from exc
    if not exact.is_finite() or abs(exact) > MAX_SAFE_INTEGER:
        raise ValueError('Unsafe annual report sum')
    if exact == exact.to_integral_value():
        return int(exact)
    as_number = float(exact)
    if Decimal(str(as_number)) != exact:
        raise ValueError('Annual report sum cannot be represented without losing its source value')
    return as_number


def parse_workbook(content, resource_id):
    _, sheet_name, year, headers = info(resource_id)
    if len(content) > MAX_ARCHIVE:
        raise ValueError('Annual workbook exceeds source size limit')
    with zipfile.ZipFile(io.BytesIO(content)) as book:
        items = book.infolist()
        names = [p.filename for p in items]
        if len(items) > 100 or len(set(names)) != len(items) or sum(p.file_size for p in items) > MAX_EXPANDED:
            raise ValueError('Annual workbook exceeds archive bounds or contains duplicate parts')
        basics = ('xl/workbook.xml', 'xl/_rels/workbook.xml.rels')
        if any(book.getinfo(p).file_size > 1024 * 1024 for p in basics):
            raise ValueError('Annual workbook XML metadata is unexpectedly large')
        w, rels = [ET.fromstring(book.read(p)) for p in basics]
        sheets = w.find('m:sheets', NS)
        if (sheets is None or len(sheets) != 1 or sheets[0].get('name') != sheet_name
                or sheets[0].get('state', 'visible') != 'visible'):
            raise ValueError('Annual workbook sheet layout changed; review needed')
        targets = [r.get('Target') for r in rels if r.get('Id') == sheets[0].get(REL)
                   and r.get('TargetMode') != 'External']
        if len(targets) != 1 or not re.fullmatch(r'/?(?:xl/)?worksheets/sheet[1-9][0-9]*\.xml', targets[0] or ''):
            raise ValueError('Invalid annual workbook worksheet relationship')
        target = targets[0].lstrip('/')
        if not target.startswith('xl/'):
            target = 'xl/' + target
        strings = []
        if 'xl/sharedStrings.xml' in names:
            with book.open('xl/sharedStrings.xml') as source:
                for _, element in ET.iterparse(source, events=('end',)):
                    if element.tag == '{' + NS['m'] + '}si':
                        entry = ''.join(x.text or '' for x in element.findall('.//m:t', NS))
                        if len(entry) > MAX_TEXT or len(strings) >= MAX_ROWS:
                            raise ValueError('Annual workbook shared-string limit exceeded')
                        strings.append(entry)
                        element.clear()
        found_header, rows, cached = False, [], 0
        lookup = [{} for _ in headers]
        with book.open(target) as source:
            for _, element in ET.iterparse(source, events=('end',)):
                tag = element.tag.rsplit('}', 1)[-1]
                if tag == 'mergeCell':
                    raise ValueError('Unexpected merged cells in annual workbook')
                if tag != 'row':
                    continue
                indexed = {}
                for cell in element.findall('m:c', NS):
                    address = cell.get('r', '')
                    index = col_index(address)
                    # All cell coordinates must belong to their enclosing row.
                    if address.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ') != element.get('r') or index in indexed:
                        raise ValueError('Invalid or duplicate annual worksheet cell')
                    indexed[index] = cell
                values = {i: cell_value(c, strings) for i, c in indexed.items()}
                if not any(v is not None and v != '' for v in values.values()):
                    element.clear()
                    continue
                if not found_header:
                    if tuple(values.get(i) for i in range(len(headers))) != headers or any(
                        c.find('m:f', NS) is not None for c in indexed.values()
                    ):
                        raise ValueError('Annual report columns changed; review needed')
                    found_header = True
                else:
                    if type(values.get(0)) not in (int, str) or str(values[0]) != str(year):
                        raise ValueError('Annual report contains a row outside its reviewed year')
                    row = [year]
                    for i in range(1, len(headers) - 1):
                        value = values.get(i)
                        if value is not None:
                            # Text identifiers must be stored as labels, preserving any leading zeros.
                            if i == 3 and not isinstance(value, str):
                                raise ValueError('Annual report registration number changed its source type')
                            value = str(value)
                            if len(value) > MAX_TEXT:
                                raise ValueError('Unexpectedly long text in annual workbook')
                            value = lookup[i].setdefault(value, len(lookup[i]))
                        row.append(value)
                    row.append(exact_amount(indexed.get(len(headers) - 1), strings))
                    rows.append(row)
                    cached += sum(c.find('m:f', NS) is not None for c in indexed.values())
                    if len(rows) > MAX_ROWS:
                        raise ValueError('Annual worksheet exceeds row limit')
                if any(i >= len(headers) and (v not in (None, '') or indexed[i].find('m:f', NS) is not None)
                       for i, v in values.items()):
                    raise ValueError('Unexpected data outside annual report columns')
                element.clear()
        if not found_header or not rows:
            raise ValueError('Annual workbook has no data')
        fields = [{'id': 'Gads', 'type': 'number'}]
        for i, name in enumerate(preview_fields(resource_id, headers)[1:-1], 1):
            field = {'id': name, 'type': 'text', 'dictionary': list(lookup[i])}
            if name != headers[i]:
                field['sourceId'] = headers[i]
            fields.append(field)
        fields.append({'id': 'Summa', 'sourceId': 'Summa_EUR', 'type': 'number'})
        return {'name': sheet_name, 'fields': fields, 'rows': rows, 'total': len(rows),
                'cachedFormulaCount': cached}


def preview_path(resource_id, source_sha, preview_sha):
    return f'{DIR}/{resource_id}-v1-{source_sha[:16]}-{preview_sha[:16]}.json'


def fresh_resource(resource_id, source_dir):
    source_url, _, year, _ = info(resource_id)
    if source_dir is None:
        content = download(source_url)
    else:
        with (source_dir / f'{resource_id}.xlsx').open('rb') as file:
            content = file.read(MAX_ARCHIVE + 1)
    source_sha = sha(content)
    if source_sha != REVIEWED_SOURCE[resource_id][0]:
        raise ValueError(f'Annual source {resource_id} SHA-256 changed; independent review required')
    sheet = parse_workbook(content, resource_id)
    converted_at = datetime.now(timezone.utc).isoformat()
    headers = {'sourceUrl': source_url, 'sourceFormat': 'XLSX', 'sourceSha256': source_sha,
               'convertedAt': converted_at, 'previewKind': SCHEMA, 'reportYear': year}
    payload = json_bytes({'schemaVersion': 1, 'resourceId': resource_id, **headers, 'sheets': [sheet]})
    if len(payload) > MAX_PREVIEW:
        raise ValueError('Annual browser preview exceeds size limit')
    preview_sha = sha(payload)
    return {'path': preview_path(resource_id, source_sha, preview_sha), **headers,
            'total': sheet['total'], 'sha256': preview_sha}, payload


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value)


def validate_cached(resource_id, preview, encoded):
    url, sheet_name, year, headers = info(resource_id)
    expected = {'sourceUrl': url, 'sourceFormat': 'XLSX', 'previewKind': SCHEMA, 'reportYear': year}
    if any(preview.get(k) != v for k, v in expected.items()) or (
        preview.get('sourceSha256') not in REVIEWED_SOURCE[resource_id] or not valid_hash(preview.get('sha256')) or
        preview['path'] != preview_path(resource_id, preview['sourceSha256'], preview['sha256']) or sha(encoded) != preview['sha256']
    ):
        raise ValueError('Annual standby copy metadata or checksum is invalid')
    timestamp(preview['convertedAt'])
    current = parse_json(encoded)
    if any(current.get(k) != v for k, v in {
        **expected, 'schemaVersion': 1, 'resourceId': resource_id,
        'sourceSha256': preview['sourceSha256'], 'convertedAt': preview['convertedAt'],
    }.items()):
        raise ValueError('Annual standby copy identity is invalid')
    sheets = current.get('sheets', [])
    if len(sheets) != 1 or sheets[0].get('name') != sheet_name:
        raise ValueError('Annual standby sheet identity is invalid')
    sheet = sheets[0]
    rows, fields = sheet.get('rows'), sheet.get('fields')
    if (not isinstance(rows, list) or not 0 < len(rows) <= MAX_ROWS or sheet.get('total') != len(rows)
            or preview.get('total') != len(rows) or not isinstance(fields, list)
            or [field.get('id') for field in fields] != preview_fields(resource_id, headers)
            or fields[-1].get('sourceId') != 'Summa_EUR'
            or (resource_id == MUNICIPAL_2025_HEADER and fields[1].get('sourceId') != 'Ministrija')):
        raise ValueError('Annual standby shape is invalid')
    for i, field in enumerate(fields):
        if i in (0, len(fields) - 1):
            if field.get('type') != 'number' or 'dictionary' in field:
                raise ValueError('Annual standby numeric field is invalid')
        else:
            dictionary = field.get('dictionary')
            if field.get('type') != 'text' or not isinstance(dictionary, list) or not all(
                isinstance(s, str) and len(s) <= MAX_TEXT for s in dictionary
            ):
                raise ValueError('Annual standby text dictionary is invalid')
    sizes = [len(field['dictionary']) for field in fields[1:-1]]
    for row in rows:
        if (not isinstance(row, list) or len(row) != len(fields) or type(row[0]) is not int or row[0] != year
                or any(value is not None and (type(value) is not int or not 0 <= value < size)
                       for value, size in zip(row[1:-1], sizes))):
            raise ValueError('Annual standby row contains invalid values or year')
        value = row[-1]
        if value is not None and (type(value) not in (int, float) or abs(value) > MAX_SAFE_INTEGER or not math.isfinite(value)):
            raise ValueError('Annual standby sum is invalid')


def obtain_cached():
    previous = parse_json(fetch_pages('data/catalog.json', MAX_CATALOG))
    datasets = [d for d in previous['datasets'] if d.get('id') == DATASET]
    if len(datasets) != 1:
        raise ValueError('Annual dataset missing from the published catalogue')
    previews = {}
    for resource in datasets[0]['resources']:
        preview = resource.get('local_preview')
        rid = resource.get('id')
        if rid in RESOURCES and isinstance(preview, dict) and preview.get('previewKind') == SCHEMA:
            if rid in previews:
                raise ValueError('Duplicate annual standby resource')
            previews[rid] = preview
    if not previews:  # Before first annual deployment only.
        return None
    if set(previews) != set(RESOURCES):
        raise ValueError('Annual standby snapshot is missing reports')
    results = {}
    for resource_id in RESOURCES:
        preview = previews[resource_id]
        # Whitelist the exact path before making the request.
        source_sha = preview.get('sourceSha256')
        preview_sha = preview.get('sha256')
        if (source_sha not in REVIEWED_SOURCE[resource_id] or not valid_hash(preview_sha) or
                preview.get('path') != preview_path(resource_id, source_sha, preview_sha)):
            raise ValueError('Invalid annual preview URL in standby manifest')
        encoded = fetch_pages(preview['path'], MAX_PREVIEW)
        validate_cached(resource_id, preview, encoded)
        results[resource_id] = ({**preview, 'snapshotFallback': True}, encoded)
    return results


def sync(source_dir=None, *, root=None, allow_standby=False):
    root = ROOT if root is None else Path(root)
    catalog_path = root / 'public/data/catalog.json'
    catalog = json.loads(catalog_path.read_bytes())
    candidates = [d for d in catalog['datasets'] if d.get('id') == DATASET]
    if len(candidates) != 1:
        raise ValueError('Missing or duplicate reviewed Treasury annual dataset')
    dataset = candidates[0]
    if (dataset.get('license_id') not in ('cc-zero', 'CC0-1.0') or dataset.get('private', False)
            or (dataset.get('organization') or {}).get('name') != 'valsts-kase'):
        raise ValueError('Treasury annual dataset is not explicitly verified public CC0')
    resources = {}
    for resource in dataset['resources']:
        resource_id = resource.get('id')
        if resource_id in RESOURCES:
            if resource_id in resources or resource.get('format', '').upper() != 'XLSX' or resource.get('url') != info(resource_id)[0]:
                raise ValueError('Treasury annual catalog resource details changed')
            resources[resource_id] = resource
    if set(resources) != set(RESOURCES):
        raise ValueError('Treasury annual catalog is missing reviewed resources')
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = dict(zip(RESOURCES, executor.map(lambda rid: fresh_resource(rid, source_dir), RESOURCES)))
    except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError) as exc:
        if not allow_standby or source_dir is not None:
            raise
        print(f'::warning::Annual Treasury reports not refreshed: {exc}', flush=True)
        results = obtain_cached()
        if results is None:
            print('::warning::No complete prior annual preview exists; publishing no new annual group, preserving budget pipeline.', flush=True)
            return {}
    out = root / 'public' / DIR
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix='.annual-stage-', dir=catalog_path.parent) as staging:
            staging = Path(staging)
            for resource_id, (preview, payload) in results.items():
                (staging / Path(preview['path']).name).write_bytes(payload)
                resources[resource_id]['local_preview'] = preview
            out.mkdir(parents=True, exist_ok=True)
            for preview, payload in results.values():
                path = root / 'public' / preview['path']
                if path.exists():
                    if path.stat().st_size != len(payload) or path.read_bytes() != payload:
                        raise ValueError('Existing content-addressed annual file conflicts; refusing to replace it')
                    continue
                os.replace(staging / path.name, path)
                created.append(path)
            atomic_bytes(catalog_path, json_bytes(catalog))
    except Exception:
        cleanup_created(created)
        raise
    keep = {Path(preview['path']).name for preview, _ in results.values()}
    for stale in out.glob('*-v1-*.json'):
        if stale.name not in keep:
            stale.unlink(missing_ok=True)
    print(f'{DATASET}: verified 12 annual worksheets, {sum(p["total"] for p, _ in results.values())} rows', flush=True)
    return {rid: p for rid, (p, _) in results.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Reviewed XLSX files named RESOURCE_ID.xlsx')
    parser.add_argument('--allow-standby', action='store_true', help='Allow a verified all-or-none standby')
    args = parser.parse_args()
    sync(args.source_dir, allow_standby=args.allow_standby)


if __name__ == '__main__':
    main()

"""Import two reviewed Treasury XLSX resources into typed, dictionary-encoded JSON.
Standard-library only; no formulas are executed. Reject changed/ambiguous layouts.
"""
import argparse
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = '8bd377ab-d7b4-4076-9898-f02d3f638144'
RESOURCES = ('a8a020c0-cfad-4600-b506-a568f2fa60d4', '09a0ba1c-ce3f-4752-b35c-f3779137ae72')
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
# Menesis_nr also contains the source marker '#'; preserve it as a label.
NUMERIC = {'Gads', 'Summa'}
REQUIRED = {'Gads', 'Menesis_nr', 'Iestade', 'Datu_valuta', 'Summa'}
MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_ROWS = 250000


def trusted_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'data.gov.lv' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('XLSX source must use https://data.gov.lv')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trusted_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    trusted_url(url)
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'LatvijasDatiExplorer/1.1'})
            with urllib.request.build_opener(SafeRedirect()).open(request, timeout=60) as response:
                content = response.read(MAX_DOWNLOAD + 1)
            if len(content) > MAX_DOWNLOAD:
                raise ValueError('XLSX file exceeds 32 MiB; manual review required')
            return content
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def col_index(reference):
    match = re.fullmatch(r'([A-Z]+)[1-9][0-9]*', reference)
    if not match:
        raise ValueError('Invalid cell reference')
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    if value > 128:
        raise ValueError('Unexpectedly wide worksheet; manual review required')
    return value - 1


def cell_value(cell, strings):
    kind = cell.get('t', 'n')
    value = cell.find('m:v', NS)
    if cell.find('m:f', NS) is not None and (value is None or value.text is None):
        raise ValueError('Formula without a cached result; cannot invent its value')
    if kind == 'e':
        raise ValueError('Spreadsheet error value found; manual review required')
    if kind == 'inlineStr':
        return ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
    if value is None or value.text is None:
        return None
    raw = value.text
    if kind == 's':
        return strings[int(raw)]
    if kind in ('str', 'd'):
        return raw
    if kind == 'b':
        return raw == '1'
    if kind != 'n':
        raise ValueError('Unsupported cell type: ' + kind)
    number = float(raw)
    if not math.isfinite(number):
        raise ValueError('Non-finite numeric value')
    return int(raw) if re.fullmatch(r'-?\d+', raw) else number


def parse_xlsx(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_EXPANDED:
            raise ValueError('Expanded XLSX exceeds 256 MiB')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            with archive.open('xl/sharedStrings.xml') as source:
                for _, element in ET.iterparse(source, events=('end',)):
                    if element.tag == '{' + NS['m'] + '}si':
                        strings.append(''.join(t.text or '' for t in element.findall('.//m:t', NS)))
                        element.clear()
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {r.get('Id'): r.get('Target') for r in rels if r.get('TargetMode') != 'External'}
        sheets = []
        for sheet in workbook.find('m:sheets', NS):
            # Do not silently skip hidden sheets in a reviewed source.
            if sheet.get('state', 'visible') != 'visible':
                raise ValueError('Hidden worksheet found; manual review required')
            target = targets[sheet.get(REL)]
            path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            if '..' in Path(path).parts or not path.startswith('xl/worksheets/'):
                raise ValueError('Unexpected worksheet path')
            headers = None
            rows = []
            formula_count = 0
            with archive.open(path) as source:
                for _, element in ET.iterparse(source, events=('end',)):
                    tag = element.tag.rsplit('}', 1)[-1]
                    if tag == 'mergeCell':
                        raise ValueError('Merged cells found; manual review required')
                    if tag != 'row':
                        continue
                    cells = {}
                    for cell in element.findall('m:c', NS):
                        index = col_index(cell.get('r', ''))
                        if index in cells:
                            raise ValueError('Duplicate cell reference')
                        cells[index] = cell_value(cell, strings)
                        formula_count += cell.find('m:f', NS) is not None
                    element.clear()
                    if not any(v is not None and v != '' for v in cells.values()):
                        continue
                    if headers is None:
                        headers = [cells.get(i) for i in range(max(cells) + 1)]
                        if any(not isinstance(h, str) or not h.strip() for h in headers) or len(set(headers)) != len(headers):
                            raise ValueError('Headers must be non-empty, unique strings')
                        if not REQUIRED.issubset(headers):
                            raise ValueError('Treasury schema changed: required columns missing')
                        continue
                    if any(i >= len(headers) and v is not None for i, v in cells.items()):
                        raise ValueError('Data outside header columns')
                    values = []
                    for i, header in enumerate(headers):
                        value = cells.get(i)
                        if header in NUMERIC and value is not None:
                            if isinstance(value, bool) or not isinstance(value, (int, float)):
                                raise ValueError('Expected numeric cell in ' + header)
                            if header in ('Gads', 'Menesis_nr') and value != int(value):
                                raise ValueError('Non-integral year or month')
                            if header == 'Menesis_nr' and not 1 <= value <= 12:
                                raise ValueError('Month outside 1–12')
                        elif value is not None and not isinstance(value, str):
                            # Codes/identifiers are labels, not measures; preserve integer precision.
                            value = str(value)
                        values.append(value)
                    rows.append(values)
                    if len(rows) > MAX_ROWS:
                        raise ValueError('Worksheet exceeds supported row limit')
            if not headers or not rows:
                raise ValueError('Empty worksheet; refusing an apparently successful empty import')
            fields = []
            for i, name in enumerate(headers):
                field = {'id': name, 'type': 'number' if name in NUMERIC else 'text'}
                if name not in NUMERIC:
                    dictionary, lookup = [], {}
                    for row in rows:
                        value = row[i]
                        if value is None:
                            continue
                        if value not in lookup:
                            lookup[value] = len(dictionary)
                            dictionary.append(value)
                        row[i] = lookup[value]
                    field['dictionary'] = dictionary
                fields.append(field)
            sheets.append({'name': sheet.get('name'), 'fields': fields, 'rows': rows,
                           'total': len(rows), 'cachedFormulaCount': formula_count})
        return sheets


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, help='Use previously downloaded files named RESOURCE_ID.xlsx for reproducible checks')
    args = parser.parse_args()
    catalog_path = ROOT / 'public/data/catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    dataset = next(d for d in catalog['datasets'] if d['id'] == DATASET)
    by_id = {r['id']: r for r in dataset['resources']}
    pending = []
    for resource_id in RESOURCES:
        resource = by_id[resource_id]
        trusted_url(resource['url'])
        content = (args.source_dir / f'{resource_id}.xlsx').read_bytes() if args.source_dir else download(resource['url'])
        if len(content) > MAX_DOWNLOAD:
            raise ValueError('XLSX source exceeds size limit')
        sheets = parse_xlsx(content)
        sha = hashlib.sha256(content).hexdigest()
        # Schema prefix makes cache identity change if converter representation changes.
        name = f'{resource_id}-v1-{sha[:16]}.json'
        converted_at = datetime.now(timezone.utc).isoformat()
        payload = {'schemaVersion': 1, 'resourceId': resource_id, 'sourceUrl': resource['url'],
                   'sourceSha256': sha, 'convertedAt': converted_at, 'sheets': sheets}
        output = ROOT / 'public/data/xlsx' / name
        atomic_json(output, payload)
        if output.stat().st_size > 24 * 1024 * 1024:
            raise ValueError('Converted file too large for browser upload; partitioning required')
        pending.append((resource, {'path': 'data/xlsx/' + name, 'sourceUrl': resource['url'],
                                  'sourceSha256': sha, 'convertedAt': converted_at,
                                  'total': sum(s['total'] for s in sheets)}))
        print(f'{resource_id}: {len(sheets)} sheets, {sum(s["total"] for s in sheets)} rows, {output.stat().st_size} JSON bytes', flush=True)
    for resource, preview in pending:
        resource['local_preview'] = preview
    atomic_json(catalog_path, catalog)
    # Catalog is replaced only after every required source passed conversion.
    keep = {Path(p['path']).name for _, p in pending}
    for path in (ROOT / 'public/data/xlsx').glob('*.json'):
        if path.name not in keep:
            path.unlink()


if __name__ == '__main__':
    main()

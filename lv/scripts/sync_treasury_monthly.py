"""Publish bounded, literal worksheets from five explicitly reviewed Treasury XLSX files."""
import argparse
import io
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from budget_estimate_fallback import MAX_CATALOG, fetch_pages, parse_json, timestamp
from publish_budget_estimates import atomic_bytes, cleanup_created, exactly_one, json_bytes
from sync_budget_estimates import NoRedirect
from sync_reviewed_xlsx import amount, sha
from sync_xlsx import NS, REL, col_index
from treasury_monthly_manifest import HEADERS, NORMALIZED, SOURCES

ROOT = Path(__file__).resolve().parents[1]
DIR = 'data/treasury-sheets'
KIND = 'treasury-sheets-v1'
RAIM = 'raim-liabilities'
EXECUTION = 'state-execution'
COMPENSATION = 'state-compensation'
MAX_ARCHIVE = 21 * 1024 * 1024
MAX_EXPANDED = 200 * 1024 * 1024
MAX_PREVIEW = 2 * 1024 * 1024
MAX_ROWS = 130_000
MAX_PART_ROWS = 15_000
EKK_HEADERS = ('EKK', 'Vienotais EKK - Key', 'EKK nosaukums')
MONTH_LABELS = ('Janvāris', 'Februāris', 'Marts', 'Aprīlis', 'Maijs', 'Jūnijs',
                'Jūlijs', 'Augusts', 'Septembris', 'Oktobris', 'Novembris', 'Decembris')
PLAN_TYPES = ('Finansēšanas plāns gadam ar izmaiņām', 'Finansēšanas plāna prognoze gadam')
EXEC_TYPES = ('Ieņēmumi', 'Izdevumi', 'Finansēšana')
NS_MAIN = '{' + NS['m'] + '}'


def download(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'LatvijasDatiExplorer/1.1',
                                              'Accept-Encoding': 'identity'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=35) as response:
        if (response.status != 200 or response.geturl() != url
                or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
            raise ValueError('Unexpected official Treasury download response')
        return response.read(MAX_ARCHIVE + 1)


def identity(rid):
    profile, _, url, digest, year, _ = SOURCES[rid]
    scope = {'year': year} if year else {'from': '2009', 'through': '2025'}
    return {'previewKind': KIND, 'reportProfile': profile, 'reportScope': scope,
            'sourceFormat': 'XLSX', 'sourceUrl': url, 'sourceSha256': digest}


def asset_path(rid, sid, digest):
    return f'{DIR}/{rid}-{sid}-v1-{digest}.json'


def root_nodes(handle, tag):
    """Stream typed children and detach completed XML rows from their sheetData."""
    stack = []
    for event, node in ET.iterparse(handle, events=('start', 'end')):
        if event == 'start':
            stack.append(node)
            continue
        if node.tag == NS_MAIN + 'mergeCell':
            raise ValueError('Unexpected merged Treasury cell')
        if node.tag == NS_MAIN + tag:
            yield node
            if len(stack) < 2:
                raise ValueError('Invalid Treasury workbook XML')
            stack[-2].remove(node)
            node.clear()
        stack.pop()


def xml_rows(handle, strings):
    last_row = 0
    for node in root_nodes(handle, 'row'):
        nr = int(node.get('r', '0'))
        if nr != last_row + 1 or nr > MAX_ROWS or node.get('hidden') in ('1', 'true'):
            raise ValueError('Unexpected row sequence, row limit or hidden Treasury values')
        last_row = nr
        seen, values = set(), {}
        for cell in node.findall('m:c', NS):
            coordinate = cell.get('r', '')
            match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]*)', coordinate)
            if not match or match[2] != str(nr):
                raise ValueError('Invalid Treasury cell coordinates')
            col = col_index(coordinate)
            if col in seen:
                raise ValueError('Duplicate Treasury cell')
            seen.add(col)
            if cell.find('m:f', NS) is not None:
                raise ValueError('Unexpected formula in reviewed Treasury source')
            kind = cell.get('t', 'n')
            raw = cell.findtext('m:v', namespaces=NS)
            if kind == 's':
                if not re.fullmatch(r'[0-9]{1,6}', raw or '') or int(raw) >= len(strings):
                    raise ValueError('Invalid Treasury shared-string index')
                value = strings[int(raw)]
            elif kind == 'n':
                value = amount(cell, 'decimal') if raw is not None else None
            elif kind == 'inlineStr':
                value = ''.join(x.text or '' for x in cell.findall('.//m:t', NS))
            else:
                raise ValueError('Unsupported Treasury cell type')
            if value not in ('', None):
                if len(value) > 4096:
                    raise ValueError('Treasury cell length exceeds limit')
                values[col] = (kind, value)
        yield nr, values


def headers_for(profile, sheet):
    return EKK_HEADERS if sheet == 'EKK' else HEADERS[profile]


def cells_for(profile, sheet, headers, cells):
    if any(i >= len(headers) for i in cells):
        raise ValueError('Unexpected unlabelled Treasury value')
    vals = [None] * len(headers)
    for i, (kind, value) in cells.items():
        if sheet == 'EKK':
            numeric = False
        else:
            numeric = (2 <= i <= 7) if profile == RAIM else i == len(headers) - 1
        if (kind == 'n') != numeric:
            raise ValueError('Treasury value type differs from the reviewed source')
        vals[i] = value
    return vals


def validate_scope(profile, sheet, year, month, vals):
    if sheet == 'EKK':
        # Compensation intentionally provides an empty EKK source-code column.
        if (not vals[1] or not vals[2] or (profile == EXECUTION and not vals[0])
                or (profile == COMPENSATION and vals[0] is not None)):
            raise ValueError('Unexpected EKK reference row')
        return
    if profile == RAIM:
        if (not vals[0] or not re.fullmatch(r'[0-9]{7}', vals[1] or '')
                or not re.fullmatch(r'31\.12\.(?:2009|201[0-9]|202[0-5])\.', vals[-1] or '')
                or any(v is None for v in vals[2:8])):
            raise ValueError('Unexpected RAIM municipality, date or measure')
        return
    i = 1 if profile == EXECUTION else 3
    expected_month_label = '#' if month == '#' else MONTH_LABELS[int(month) - 1]
    if (vals[0] != year or vals[i] != month or vals[i + 1] != expected_month_label
            or vals[-2] != 'Euro' or vals[-1] is None):
        raise ValueError('Unexpected Treasury year, month, currency or missing amount')
    kind = vals[-13]
    if profile == EXECUTION:
        if kind not in EXEC_TYPES:
            raise ValueError('Unexpected state-execution classification')
        return
    version, as_of = vals[1:3]
    if month != '#':
        if kind != 'Izdevumi' or version != '#' or as_of != '#':
            raise ValueError('Compensation plan unexpectedly appears in actuals')
    elif kind not in PLAN_TYPES or not re.fullmatch(r'[0-9]{2}\.[0-9]{2}\.[0-9]{4}', as_of or ''):
        raise ValueError('Unexpected compensation plan class or as-of date')
    else:
        day, mth, yyyy = map(int, as_of.split('.'))
        report_date = date(yyyy, mth, day)
        expected = (f'F{report_date:%y%m%d}' if kind == PLAN_TYPES[0] else 'P000000')
        if str(yyyy) != year or version != expected or (kind == PLAN_TYPES[1] and (mth, day) != (1, 1)):
            raise ValueError('Compensation plan version and date disagree')


def read_sheet(handle, strings, profile, year, sheet, blocks):
    headers = headers_for(profile, sheet)
    if sheet == 'EKK':
        kinds = ['text'] * len(headers)
    elif profile == RAIM:
        kinds = ['text', 'text', *(['decimal'] * 6), 'text']
    else:
        kinds = ['text'] * (len(headers) - 1) + ['decimal']
    table = None
    blockiter = iter(blocks)
    current = next(blockiter, None)
    tail = False
    populated = {}
    dates = set()
    last = 0
    for nr, cells in xml_rows(handle, strings):
        last = nr
        if nr == 1:
            if tuple(cells.get(i, (None, None))[1] for i in range(len(headers))) != headers or len(cells) != len(headers):
                raise ValueError('Treasury worksheet headings changed')
            continue
        if not current:
            if profile == RAIM or cells or tail:
                raise ValueError('Unexpected row after final reviewed Treasury range')
            tail = True
            continue
        sid, (_, count, month, first, end) = current
        if nr == first:
            if count != end - first + 1 or count > MAX_PART_ROWS:
                raise ValueError('Invalid reviewed Treasury part length')
            table = ([], [{} for _ in headers])
        if not first <= nr <= end or table is None or not cells:
            raise ValueError('Missing or out-of-range row within Treasury partition')
        vals = cells_for(profile, sheet, headers, cells)
        validate_scope(profile, sheet, year, month, vals)
        if profile == RAIM:
            dates.add(vals[-1])
        rows, dictionaries = table
        rows.append([None if v is None else dictionaries[i].setdefault(v, len(dictionaries[i]))
                     for i, v in enumerate(vals)])
        if nr == end:
            populated[sid] = {'name': sheet, 'total': count, 'cachedFormulaCount': 0,
                'fields': [{'id': label, 'type': kind, 'dictionary': list(dictionary)}
                           for label, kind, dictionary in zip(headers, kinds, dictionaries)],
                'rows': rows}
            table = None
            current = next(blockiter, None)
    if last == 0 or current or tail != (profile != RAIM):
        raise ValueError('Incomplete reviewed Treasury worksheet or terminal blank')
    if profile == RAIM and dates != {f'31.12.{y}.' for y in range(2009, 2026)}:
        raise ValueError('Incomplete RAIM date coverage')
    return populated


def parse_workbook(rid, content):
    if len(content) > MAX_ARCHIVE:
        raise ValueError('Treasury XLSX exceeds compressed limit')
    profile, _, _, _, year, specs = SOURCES[rid]
    expected = {v[0] for v in specs.values()}
    with zipfile.ZipFile(io.BytesIO(content)) as book:
        items = book.infolist()
        names = {x.filename for x in items}
        if (len(items) > 100 or len(names) != len(items)
                or sum(x.file_size for x in items) > MAX_EXPANDED):
            raise ValueError('Treasury XLSX exceeds expanded XML limits')
        paths = ('xl/workbook.xml', 'xl/_rels/workbook.xml.rels')
        if any(book.getinfo(p).file_size > 1024 * 1024 for p in paths):
            raise ValueError('Treasury XLSX metadata too large')
        workbook, rels = (ET.fromstring(book.read(p)) for p in paths)
        targets = {}
        for rel in rels:
            if rel.get('TargetMode') != 'External':
                key = rel.get('Id')
                if key in targets:
                    raise ValueError('Duplicate Treasury relationship')
                targets[key] = rel.get('Target')
        sheets = {}
        for worksheet in workbook.findall('m:sheets/m:sheet', NS):
            name = worksheet.get('name')
            target = targets.get(worksheet.get(REL))
            if (worksheet.get('state', 'visible') != 'visible' or name in sheets
                    or not re.fullmatch(r'/?(?:xl/)?worksheets/sheet[1-9][0-9]*\.xml', target or '')):
                raise ValueError('Invalid Treasury worksheet relationship')
            target = target.lstrip('/')
            sheets[name] = (target if target.startswith('xl/') else 'xl/' + target)
        if expected != sheets.keys() or len(set(sheets.values())) != len(expected):
            raise ValueError('Unexpected Treasury worksheets')
        with book.open('xl/sharedStrings.xml') as handle:
            strings = []
            for node in root_nodes(handle, 'si'):
                value = ''.join(text.text or '' for text in node.findall('.//m:t', NS))
                if len(value) > 4096 or len(strings) >= 45_000:
                    raise ValueError('Treasury shared strings exceed limits')
                strings.append(value)
        all_tables = {}
        for sheet, path in sheets.items():
            with book.open(path) as handle:
                all_tables.update(read_sheet(handle, strings, profile, year, sheet,
                                            [(sid,p) for sid,p in specs.items() if p[0] == sheet]))
    return {sid: all_tables[sid] for sid in specs}


def pointer(rid, sid, digest):
    name, count, month, _, _ = SOURCES[rid][-1][sid]
    p = {'id': sid, 'name': name, 'total': count, 'sha256': digest, 'path': asset_path(rid, sid, digest)}
    if month is not None:
        p['month'] = month
    return p


def fresh(rid, source_dir):
    if source_dir is None:
        content = download(SOURCES[rid][2])
    else:
        with (source_dir / f'{rid}.xlsx').open('rb') as handle:
            content = handle.read(MAX_ARCHIVE + 1)
    if len(content) > MAX_ARCHIVE or sha(content) != SOURCES[rid][3]:
        raise ValueError(f'Treasury original {rid} changed; independent review required')
    meta = {**identity(rid), 'convertedAt': datetime.now(timezone.utc).isoformat()}
    assets, pointers = {}, []
    for sid, table in parse_workbook(rid, content).items():
        if sha(json_bytes(table)) != NORMALIZED[rid][sid]:
            raise ValueError(f'Treasury part {sid} no longer matches independently reviewed output')
        blob = json_bytes({'schemaVersion': 1, 'resourceId': rid, 'reportSheet': sid, **meta, 'sheets': [table]})
        if len(blob) > MAX_PREVIEW:
            raise ValueError('Treasury part exceeds browser payload limit')
        p = pointer(rid, sid, sha(blob))
        pointers.append(p)
        assets[p['path']] = blob
    return {**meta, 'total': sum(p['total'] for p in pointers), 'reportSheets': pointers}, assets


def selected(catalog):
    result = {}
    for rid, (profile, did, url, _, _, _) in SOURCES.items():
        ds = exactly_one(catalog['datasets'], 'id', did, 'dataset')
        if (ds.get('license_id') not in ('CC0-1.0', 'cc-zero') or ds.get('private', False)
                or (ds.get('organization') or {}).get('name') != 'valsts-kase'):
            raise ValueError('Treasury dataset is not verified public CC0')
        res = exactly_one(ds['resources'], 'id', rid, 'resource')
        if res.get('url') != url or res.get('format') != 'XLSX':
            raise ValueError('Reviewed Treasury official link or format changed')
        if res.get('local_preview') and (res['local_preview'].get('previewKind') != KIND
                or res['local_preview'].get('reportProfile') != profile):
            raise ValueError('Refusing to replace a different Treasury preview')
        result[rid] = res
    return result


def standby(current):
    prior = selected(parse_json(fetch_pages('data/catalog.json', MAX_CATALOG)))
    if not any(r.get('local_preview') for r in prior.values()):
        if any(r.get('local_preview') for r in current.values()):
            raise ValueError('Previously selected Treasury group cannot be verified')
        return {}
    result = {}
    for rid, res in prior.items():
        preview = res.get('local_preview')
        meta = identity(rid)
        allowed = SOURCES[rid][-1]
        if (not isinstance(preview, dict) or any(preview.get(k) != v for k, v in meta.items())
                or preview.get('total') != sum(v[1] for v in allowed.values())):
            raise ValueError('Incomplete previously published Treasury group')
        converted = preview.get('convertedAt')
        timestamp(converted)
        pointers = preview.get('reportSheets')
        if (not isinstance(pointers, list) or any(not isinstance(p, dict) for p in pointers)
                or [x.get('id') for x in pointers] != list(allowed)):
            raise ValueError('Incomplete previously published Treasury parts')
        def verify(p):
            sid = p['id']
            digest = p.get('sha256')
            if (not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)
                    or p != pointer(rid, sid, digest)):
                raise ValueError('Invalid previously published Treasury part pointer')
            blob = fetch_pages(p['path'], MAX_PREVIEW)
            if len(blob) > MAX_PREVIEW or sha(blob) != digest:
                raise ValueError('Published Treasury part checksum mismatch')
            value = parse_json(blob)
            tables = value.get('sheets')
            if (not isinstance(tables, list) or len(tables) != 1
                    or sha(json_bytes(tables[0])) != NORMALIZED[rid][sid]
                    or value != {'schemaVersion': 1, 'resourceId': rid, 'reportSheet': sid,
                                 'convertedAt': converted, **meta, 'sheets': tables}):
                raise ValueError('Published Treasury part differs from independently reviewed contents')
            return p['path'], blob
        with ThreadPoolExecutor(max_workers=4) as pool:
            assets = dict(pool.map(verify, pointers))
        result[rid] = ({**preview, 'snapshotFallback': True}, assets)
    return result


def sync(source_dir=None, *, root=None, allow_standby=False):
    public = (ROOT if root is None else Path(root)) / 'public'
    cp = public / 'data/catalog.json'
    catalog = json.loads(cp.read_bytes())
    resources = selected(catalog)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = dict(zip(SOURCES, pool.map(lambda rid: fresh(rid, source_dir), SOURCES)))
    except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError) as exc:
        if not allow_standby or source_dir is not None:
            raise
        print(f'::warning::Reviewed Treasury monthly/RAIM source did not pass refresh: {exc}', flush=True)
        results = standby(resources)
        if not results:
            print('::warning::No previous monthly/RAIM group; keeping all other site data.', flush=True)
            return {}
    created, keep = [], set()
    try:
        for rid, (preview, assets) in results.items():
            for path, encoded in assets.items():
                keep.add(path)
                target = public / path
                if target.exists():
                    if target.stat().st_size != len(encoded) or target.read_bytes() != encoded:
                        raise ValueError('Existing Treasury part conflicts')
                else:
                    atomic_bytes(target, encoded)
                    created.append(target)
            resources[rid]['local_preview'] = preview
        atomic_bytes(cp, json_bytes(catalog))
    except Exception:
        cleanup_created(created)
        raise
    for rid in SOURCES:
        for entry in (public / DIR).glob(f'{rid}-*-v1-*.json'):
            if entry.relative_to(public).as_posix() not in keep:
                entry.unlink(missing_ok=True)
    print(f'Treasury monthly/RAIM originals: {len(results)}, assets: {len(keep)}, rows: '
          f'{sum(p["total"] for p, _ in results.values())}', flush=True)
    return {rid: p for rid, (p, _) in results.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--allow-standby', action='store_true')
    args = parser.parse_args()
    sync(args.source_dir, allow_standby=args.allow_standby)


if __name__ == '__main__':
    main()

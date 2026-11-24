"""Publish separately loaded, reviewed worksheets from official Treasury workbooks."""
import argparse
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from budget_estimate_fallback import MAX_CATALOG, fetch_pages, parse_json, timestamp
from publish_budget_estimates import atomic_bytes, cleanup_created, exactly_one, json_bytes
from sync_reviewed_xlsx import amount, download, sha
from sync_xlsx import NS, REL, cell_value, col_index

ROOT = Path(__file__).resolve().parents[1]
DATASET = '80e304db-bd31-40a5-a381-2e7c5d66af78'
DIR = 'data/treasury-sheets'
KIND = 'treasury-sheets-v1'
MAX_ARCHIVE = 2 * 1024 * 1024
MAX_EXPANDED = 18 * 1024 * 1024
MAX_PREVIEW = 4 * 1024 * 1024
MAX_ROWS = 7200
DATA_HEADERS = (
    'Gads', 'Menesis_Atslega', 'Menesis_nosaukums', 'Budzeta_tips_Atslega', 'Budzeta_tips_nosaukums',
    'Programma_Atslega', 'Programma_nosaukums', 'Apaksprogramma_Atslega', 'Apaksprogramma_nosaukums',
    'Buzeta_bloks', 'Funkcija_augstakais_limenis_Atslega', 'Funkcija_augstakais_limenis_Nosaukums',
    'Funkcija_zemakaja_limeni_Atslega', 'Funkcija_zemakaja_limeni_nosaukums', 'Saistibu_veids_Atslega',
    'Saistibu_veids_nosaukums', 'Projekta_arejais_kods_Atslega', 'Projekts_nosaukums', 'Klasifikacija',
    *(f'Vienotais_EKK_Atslega_{i}_limenis' for i in range(1, 9)), 'Vienotais_EKK_Nosaukums_8_limenis',
    'Likuma_griezuma_EKK', 'Konsolidacija', 'Datu_valuta', 'Summa',
)
EKK_HEADERS = ('EKK', 'Vienotais EKK - Key', 'EKK nosaukums')
# Resource ID: (report year, original SHA256, populated DATI rows, populated EKK rows).
SOURCES = {
    'd55ce40b-72d3-4d86-ab95-6cc978bf07f8': ('2026', 'c8ddbfd5918256c25b387257975ebad501a2c78eee9564ce1b45e5218f91306f', 5469, 450),
    '7df9fad3-131c-41a5-aae3-dfa15ea7a693': ('2025', 'a60fbcd93f061c2bc998985f16ac57a9d17a00336d04a3eed5fb9029be9af6a6', 6495, 449),
    '3bf87f2a-0b49-481a-bc09-86d9b09cd445': ('2024', 'e95a468bde75a49342af0319451bb20b2b03dacc1579873bd2ff1647135ff1e1', 6404, 447),
    '3052039f-5c69-42cc-a295-0aff6959dead': ('2022', '8e3bafb2323d122d5f4d558a90d2249f9a646d93df4ef39ea23e8dee2e186878', 6541, 447),
    '7d95c38f-a274-432a-b52f-1c90fe28190f': ('2021', 'bba242649fc91500f7fe12e34c26fd9c95e7123fd452619dbc43f6730a0edde2', 6609, 464),
    'ca75ebbc-bd58-47eb-b757-4555ad63f7bd': ('2020', '94ffa28e8a3d240f9564a4221fc6ddcc7a1b5749443e449d7bcc220f0b5448f2', 6552, 479),
    '20da8462-7e91-488e-a8ed-2b84e873d04a': ('2019', '6502db502c311820cd71e44085db0eec83dd7a4117a8d9955eefe2ef6bcebfe5', 6996, 481),
}
# Includes every table cell, excluding envelope with conversion timestamp.
NORMALIZED = {'d55ce40b-72d3-4d86-ab95-6cc978bf07f8': {'dati': '882979efbe111365cda869913f38224274b6444c2795496f6610b6e258c50608',
                                          'ekk': '8892a6cb718738b6a66b8c5c8ff9387520526b86c00355ef58a0a1861d1273ab'},
 '7df9fad3-131c-41a5-aae3-dfa15ea7a693': {'dati': '234ad4b0180b596e31b1de38ddd28f03eed3387a5f8dd748187c4157836eb0f6',
                                          'ekk': '9345f600f9a1bed31369996e9c2bce52b07349c6c90d9863351ef78ecbf5be52'},
 '3bf87f2a-0b49-481a-bc09-86d9b09cd445': {'dati': 'd8e9f6bbc855b84defad9a62f63d246c36450ad1bf916803e695360157a88599',
                                          'ekk': '1b09bcccdb89c3a291ddaed404dc3486a9be0336c46e2e69eda0ea4ee60304da'},
 '3052039f-5c69-42cc-a295-0aff6959dead': {'dati': '7c3fdcb302f8345b9796352e78874fe080df24ef3c8c3f6d0b8a96b4c563ad5b',
                                          'ekk': 'f45c66bc8f6d41e3dd198a502856a4fb50994465ec284f2001a50b07e4fdee2e'},
 '7d95c38f-a274-432a-b52f-1c90fe28190f': {'dati': 'defe597277b546a38069760bc807d56594b2b69b42067bc0ad759f61febd8e1d',
                                          'ekk': 'b79852adb5810ef28d115c5dd5b5e6972366ac79fffad34fff3738e966bffee2'},
 'ca75ebbc-bd58-47eb-b757-4555ad63f7bd': {'dati': 'f75ea4b9dfe3533f378de2674bc90a22c038ae15ad22a5c77fe38e2597139ffc',
                                          'ekk': '6cb6d8f33b67c22c2a53554cb6f9f1876ebddb2c9e83337acd2569e542a16707'},
 '20da8462-7e91-488e-a8ed-2b84e873d04a': {'dati': 'c3e1c08234462496156363d44b72baf00960229b101fc9d081f5a68cd5ec15ba',
                                          'ekk': '9084dd74f2f1736d932c24dc32f7acd1a29701e965cea262d7712ff8b1a78343'}}


def source_url(rid):
    return f'https://data.gov.lv/dati/dataset/{DATASET}/resource/{rid}/download/vb_pb_sb_ienemumi_{SOURCES[rid][0]}.xlsx'


def sheets_for(rid):
    _, _, data_count, ekk_count = SOURCES[rid]
    return {'dati': ('DATI', DATA_HEADERS, data_count), 'ekk': ('EKK', EKK_HEADERS, ekk_count)}


def xml_rows(handle):
    row_no = 0
    for _, node in ET.iterparse(handle, events=('end',)):
        tag = node.tag.rsplit('}', 1)[-1]
        if tag == 'mergeCell':
            raise ValueError('Unreviewed merge in Treasury worksheet')
        if tag != 'row':
            continue
        nr = int(node.get('r'))
        if not row_no < nr <= MAX_ROWS + 2 or node.get('hidden') in ('1', 'true'):
            raise ValueError('Treasury worksheet exceeds row or visibility limits')
        row_no = nr
        cells = {}
        for cell in node.findall('m:c', NS):
            coordinate = cell.get('r', '')
            i = col_index(coordinate)
            if coordinate.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ') != str(nr) or i in cells:
                raise ValueError('Duplicate or mismatched Treasury coordinates')
            if cell.find('m:f', NS) is not None:
                raise ValueError('Unexpected formula in reviewed revenue worksheet')
            cells[i] = cell
        yield nr, cells
        node.clear()


def read_table(handle, strings, name, headers, count, year):
    types = ['text'] * len(headers)
    data = name == 'DATI'
    if data:
        types[-1] = 'decimal'
    rows, dictionaries, found_header = [], [{} for _ in headers], False
    for nr, cells in xml_rows(handle):
        values = {}
        for i, cell in cells.items():
            if cell.get('t') == 's':
                index = cell.findtext('m:v', namespaces=NS)
                if not re.fullmatch(r'[0-9]{1,6}', index or '') or int(index) >= len(strings):
                    raise ValueError('Invalid Treasury shared-string index')
            value = cell_value(cell, strings)
            if i >= len(headers) and value is not None:
                raise ValueError('Unexpected value outside reviewed columns')
            if value is not None:
                values[i] = value
        if not values:
            continue
        vals = [values.get(i) for i in range(len(headers))]
        if not found_header:
            if nr != 1 or tuple(vals) != headers:
                raise ValueError('Treasury headings changed')
            found_header = True
            continue
        if len(rows) >= count:
            raise ValueError('Treasury report exceeds reviewed row count')
        if data:
            if (vals[0] != year or vals[1] not in {str(i) for i in range(1, 13)}
                    or vals[30] != 'Euro'):
                raise ValueError('Treasury report year, month or currency changed')
            vals[-1] = amount(cells.get(len(headers) - 1), 'decimal')
        elif any(v is None for v in vals):
            raise ValueError('Incomplete Treasury EKK row')
        encoded = []
        for i, v in enumerate(vals):
            if v is not None and (type(v) is not str or len(v) > 4096):
                raise ValueError('Unexpected Treasury cell type or length')
            encoded.append(None if v is None else dictionaries[i].setdefault(v, len(dictionaries[i])))
        rows.append(encoded)
    if not found_header or len(rows) != count:
        raise ValueError('Incomplete Treasury worksheet')
    return {'name': name, 'total': count, 'cachedFormulaCount': 0,
            'fields': [{'id': label, 'type': kind, 'dictionary': list(dictionary)}
                       for label, kind, dictionary in zip(headers, types, dictionaries)],
            'rows': rows}


def parse_workbook(rid, content):
    if len(content) > MAX_ARCHIVE:
        raise ValueError('Treasury workbook exceeds compressed limit')
    with zipfile.ZipFile(io.BytesIO(content)) as book:
        items = book.infolist()
        names = [x.filename for x in items]
        if len(names) > 100 or len(set(names)) != len(names) or sum(x.file_size for x in items) > MAX_EXPANDED:
            raise ValueError('Treasury workbook exceeds XML limits')
        paths = ('xl/workbook.xml', 'xl/_rels/workbook.xml.rels')
        if any(book.getinfo(path).file_size > 1024 * 1024 for path in paths):
            raise ValueError('Treasury workbook exceeds metadata limit')
        workbook, rels = (ET.fromstring(book.read(path)) for path in paths)
        targets = {}
        for rel in rels:
            if rel.get('TargetMode') != 'External':
                key = rel.get('Id')
                if key in targets:
                    raise ValueError('Duplicate Treasury relationship')
                targets[key] = rel.get('Target')
        names_and_targets = {}
        for sheet in workbook.findall('m:sheets/m:sheet', NS):
            name = sheet.get('name')
            target = targets.get(sheet.get(REL))
            if (sheet.get('state', 'visible') != 'visible' or name in names_and_targets
                    or not re.fullmatch(r'/?(?:xl/)?worksheets/sheet[1-9][0-9]*\.xml', target or '')):
                raise ValueError('Invalid Treasury worksheet relationship')
            target = target.lstrip('/')
            names_and_targets[name] = target if target.startswith('xl/') else 'xl/' + target
        spec = sheets_for(rid)
        if (set(names_and_targets) != {v[0] for v in spec.values()}
                or len(set(names_and_targets.values())) != len(spec)):
            raise ValueError('Treasury worksheets differ from the reviewed workbook')
        strings = []
        if 'xl/sharedStrings.xml' in names:
            with book.open('xl/sharedStrings.xml') as handle:
                for _, node in ET.iterparse(handle, events=('end',)):
                    if node.tag == '{' + NS['m'] + '}si':
                        s = ''.join(x.text or '' for x in node.findall('.//m:t', NS))
                        if len(s) > 4096 or len(strings) >= 45_000:
                            raise ValueError('Treasury shared strings exceed limits')
                        strings.append(s)
                        node.clear()
        result = {}
        for sid, (name, headers, count) in spec.items():
            with book.open(names_and_targets[name]) as handle:
                result[sid] = read_table(handle, strings, name, headers, count, SOURCES[rid][0])
    return result


def identity(rid):
    return {'previewKind': KIND, 'sourceFormat': 'XLSX', 'sourceUrl': source_url(rid),
            'sourceSha256': SOURCES[rid][1], 'reportScope': {'year': SOURCES[rid][0]}}


def asset_path(rid, sid, digest):
    return f'{DIR}/{rid}-{sid}-v1-{digest}.json'


def fresh(rid, source_dir):
    if source_dir is None:
        content = download(source_url(rid))
    else:
        with (source_dir / f'{rid}.xlsx').open('rb') as handle:
            content = handle.read(MAX_ARCHIVE + 1)
    if len(content) > MAX_ARCHIVE or sha(content) != SOURCES[rid][1]:
        raise ValueError(f'Treasury original {rid} changed; independent review required')
    meta = {**identity(rid), 'convertedAt': datetime.now(timezone.utc).isoformat()}
    assets, pointers = {}, []
    for sid, table in parse_workbook(rid, content).items():
        if sha(json_bytes(table)) != NORMALIZED[rid][sid]:
            raise ValueError(f'Treasury worksheet {sid} no longer matches reviewed output')
        encoded = json_bytes({'schemaVersion': 1, 'resourceId': rid, 'reportSheet': sid,
                              **meta, 'sheets': [table]})
        if len(encoded) > MAX_PREVIEW:
            raise ValueError('Treasury worksheet exceeds browser payload limit')
        digest = sha(encoded)
        path = asset_path(rid, sid, digest)
        pointers.append({'id': sid, 'name': table['name'], 'total': table['total'],
                         'sha256': digest, 'path': path})
        assets[path] = encoded
    return {**meta, 'total': sum(p['total'] for p in pointers), 'reportSheets': pointers}, assets


def selected(catalog):
    ds = exactly_one(catalog['datasets'], 'id', DATASET, 'dataset')
    if (ds.get('license_id') not in ('CC0-1.0', 'cc-zero') or ds.get('private', False)
            or (ds.get('organization') or {}).get('name') != 'valsts-kase'):
        raise ValueError('Treasury revenue dataset is not verified public CC0')
    result = {}
    for rid in SOURCES:
        res = exactly_one(ds['resources'], 'id', rid, 'resource')
        if res.get('url') != source_url(rid) or res.get('format', '').upper() != 'XLSX':
            raise ValueError('Treasury revenue official link or format changed')
        if res.get('local_preview') and res['local_preview'].get('previewKind') != KIND:
            raise ValueError('Refusing to overwrite another Treasury preview')
        result[rid] = res
    return result


def standby():
    prior = selected(parse_json(fetch_pages('data/catalog.json', MAX_CATALOG)))
    if not any(r.get('local_preview') for r in prior.values()):
        return {}
    result = {}
    for rid, res in prior.items():
        preview = res.get('local_preview')
        meta = identity(rid)
        allowed = sheets_for(rid)
        if (not isinstance(preview, dict) or any(preview.get(k) != v for k, v in meta.items())
                or preview.get('total') != sum(v[-1] for v in allowed.values())):
            raise ValueError('Incomplete previously published Treasury workbooks')
        timestamp(preview['convertedAt'])
        pointers = preview.get('reportSheets')
        if not isinstance(pointers, list) or [x.get('id') for x in pointers] != list(allowed):
            raise ValueError('Incomplete previously published Treasury worksheets')
        assets = {}
        for p in pointers:
            sid = p['id']
            name, _, count = allowed[sid]
            digest = p.get('sha256', '')
            if (p.get('name') != name or p.get('total') != count
                    or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)
                    or p.get('path') != asset_path(rid, sid, digest)):
                raise ValueError('Invalid pointer for previously published Treasury worksheet')
            encoded = fetch_pages(p['path'], MAX_PREVIEW)
            if len(encoded) > MAX_PREVIEW or sha(encoded) != digest:
                raise ValueError('Published Treasury worksheet container checksum mismatch')
            value = parse_json(encoded)
            if any(value.get(k) != v for k, v in {**meta, 'schemaVersion': 1, 'resourceId': rid,
                    'reportSheet': sid, 'convertedAt': preview['convertedAt']}.items()):
                raise ValueError('Published Treasury worksheet provenance mismatch')
            tables = value.get('sheets')
            if not isinstance(tables, list) or len(tables) != 1 or sha(json_bytes(tables[0])) != NORMALIZED[rid][sid]:
                raise ValueError('Published Treasury worksheet differs from its verified content')
            assets[p['path']] = encoded
        result[rid] = ({**preview, 'snapshotFallback': True}, assets)
    return result


def sync(source_dir=None, *, root=None, allow_standby=False):
    public = (ROOT if root is None else Path(root)) / 'public'
    cp = public / 'data/catalog.json'
    catalog = json.loads(cp.read_bytes())
    resources = selected(catalog)
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(zip(SOURCES, pool.map(lambda rid: fresh(rid, source_dir), SOURCES)))
    except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError) as exc:
        if not allow_standby or source_dir is not None:
            raise
        print(f'::warning::Treasury revenue originals did not pass refresh: {exc}', flush=True)
        results = standby()
        if not results:
            print('::warning::No previous revenue preview group; keeping all other site data.', flush=True)
            return {}
    created, keep = [], set()
    try:
        for rid, (preview, assets) in results.items():
            for path, encoded in assets.items():
                keep.add(path)
                target = public / path
                if target.exists():
                    if target.stat().st_size != len(encoded) or target.read_bytes() != encoded:
                        raise ValueError('Existing Treasury worksheet output conflicts')
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
    print(f'Treasury revenue originals: {len(results)}, worksheets: {len(keep)}, rows: '
          f'{sum(p["total"] for p, _ in results.values())}', flush=True)
    return {rid: preview for rid, (preview, _) in results.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--allow-standby', action='store_true')
    args = parser.parse_args()
    sync(args.source_dir, allow_standby=args.allow_standby)


if __name__ == '__main__':
    main()

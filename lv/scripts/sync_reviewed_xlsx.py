"""Reviewed historical Treasury imports; XLSX formulae are never executed."""
import argparse
import hashlib
import io
import json
import re
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from budget_estimate_fallback import MAX_CATALOG, fetch_pages, parse_json, timestamp
from publish_budget_estimates import atomic_bytes, cleanup_created, exactly_one, json_bytes
from sync_budget_estimates import NoRedirect
from sync_xlsx import NS, REL, cell_value, col_index

ROOT = Path(__file__).resolve().parents[1]
DIR = 'data/reviewed-xlsx'
KIND = 'treasury-reviewed-v1'
MAX_ARCHIVE = 4 * 1024 * 1024
MAX_EXPANDED = 48 * 1024 * 1024
MAX_PREVIEW = 12 * 1024 * 1024
MAX_ROWS = 75_000
FEB = '8c8ff425-d200-4a04-90c6-398508b8329b'
FOOTER = 'ee5889d5-e35e-46a0-beb2-3a317a9a64cd'
SUBTOTAL = {
    'sheet': '2025_Izdevumi', 'cell': 'F31030',
    'formula': 'SUBTOTAL(9,F2:F31029)', 'value': 28885561868, 'currency': 'EUR',
}
# Each entry: catalogue dataset ID, original URL, original SHA-256, sheet, year,
# exact number of dated records, columns in source order.
SOURCES = {'17ea37f3-e946-49a1-adf0-a6dbd0e03554': ('54302d29-36af-4b5e-813c-9f8741bd7504',
                                          'https://data.gov.lv/dati/dataset/54302d29-36af-4b5e-813c-9f8741bd7504/resource/17ea37f3-e946-49a1-adf0-a6dbd0e03554/download/2025_ienemumi.xlsx',
                                          '010cf812737dd7789625b2e803e1728badd39ce1782a2a020ab00c74ac263566',
                                          '2025_ienemumi',
                                          '2025',
                                          3912,
                                          ('Gads',
                                           'Pasvaldibas_ID',
                                           'Pasvaldibas nosaukums',
                                           'Ienemumu_klasifikacijas_kods',
                                           'EUR')),
 '1b192cdf-d194-4a22-a55e-3839668caca2': ('54302d29-36af-4b5e-813c-9f8741bd7504',
                                          'https://data.gov.lv/dati/dataset/54302d29-36af-4b5e-813c-9f8741bd7504/resource/1b192cdf-d194-4a22-a55e-3839668caca2/download/2024_ienemumi.xlsx',
                                          'b8bba3956135caca6dd7a163ff7ddd6c76c1abe6eda05a8691ea4f334010978e',
                                          '2024_ienemumi',
                                          '2024',
                                          3990,
                                          ('Gads',
                                           'Pasvaldibas_ID',
                                           'Pasvaldibas nosaukums',
                                           'Ienemumu_klasifikacijas_kods',
                                           'EUR')),
 'ee5889d5-e35e-46a0-beb2-3a317a9a64cd': ('acd4be04-7024-4511-bedd-1759d8d43dc0',
                                          'https://data.gov.lv/dati/dataset/acd4be04-7024-4511-bedd-1759d8d43dc0/resource/ee5889d5-e35e-46a0-beb2-3a317a9a64cd/download/2025_izdevumi.xlsx',
                                          '175f63e2f20e71df86827033c46f7121750dcda0c2d0be5d47f6f6eb7d76d41c',
                                          '2025_Izdevumi',
                                          '2025',
                                          31028,
                                          ('Gads',
                                           'Pasvaldibas_ID',
                                           'Pasvaldibas_nosaukums',
                                           'Funkcionalas_klasifikacijas_kods',
                                           'Izdevumu_ekonomiskas_klasifikacijas_kods',
                                           'EUR')),
 '32343873-19c3-49ec-b280-692b62730a59': ('acd4be04-7024-4511-bedd-1759d8d43dc0',
                                          'https://data.gov.lv/dati/dataset/acd4be04-7024-4511-bedd-1759d8d43dc0/resource/32343873-19c3-49ec-b280-692b62730a59/download/2024_izdevumi.xlsx',
                                          'c30d4e79016499479e4a9ec0283ca5008dadd19879ff30021cd9d2ecfc6790ef',
                                          '2024_Izdevumi',
                                          '2024',
                                          31608,
                                          ('Gads',
                                           'Pasvaldibas_ID',
                                           'Pasvaldibas_nosaukums',
                                           'Funkcionalas_klasifikacijas_kods',
                                           'Izdevumu_ekonomiskas_klasifikacijas_kods',
                                           'EUR')),
 'b8577673-d974-4b94-a541-11d0db1bda43': ('acd4be04-7024-4511-bedd-1759d8d43dc0',
                                          'https://data.gov.lv/dati/dataset/acd4be04-7024-4511-bedd-1759d8d43dc0/resource/b8577673-d974-4b94-a541-11d0db1bda43/download/2021_izdevumi.xlsx',
                                          '78e2eb92a0f09d8b8fa8c7287b5a90b4f9ef19896765da9cc73ae42a13d6c790',
                                          '2021_izdevumi',
                                          '2021',
                                          33830,
                                          ('Gads',
                                           'Pasvaldibas_ID',
                                           'Pasvaldibas_nosaukums',
                                           'Funkcionalas_klasifikacijas_kods',
                                           'Izdevumu_ekonomiskas_klasifikacijas_kods',
                                           'EUR')),
 'f0046fd5-3464-4793-a0e8-8852713b3f25': ('acd4be04-7024-4511-bedd-1759d8d43dc0',
                                          'https://data.gov.lv/dati/dataset/acd4be04-7024-4511-bedd-1759d8d43dc0/resource/f0046fd5-3464-4793-a0e8-8852713b3f25/download/2016_izdevumi.xlsx',
                                          '2291b80903ee9736bdb640e994f5f686a62da4db826c381268b2f9a61c92f686',
                                          '2016_Izdevumi',
                                          '2016',
                                          73840,
                                          ('Gads',
                                           'Pasvaldibas_ID',
                                           'Pasvaldibas_nosaukums',
                                           'Funkcionalas_klasifikacijas_kods',
                                           'Izdevumu_ekonomiskas_klasifikacijas_kods',
                                           'EUR')),
 '8c8ff425-d200-4a04-90c6-398508b8329b': ('ec81699b-3f04-4d9e-a305-8f9030c495cb',
                                          'https://data.gov.lv/dati/dataset/ec81699b-3f04-4d9e-a305-8f9030c495cb/resource/8c8ff425-d200-4a04-90c6-398508b8329b/download/vb_izpilde_pa_iestadem_budzeta_progr_apakspr_adkopai_2023_feb.xlsx',
                                          '193aff9869d555a2762cbb61371ac58d57fc0d5adc9514b8d3231cc2e3e1f390',
                                          'AD kopa',
                                          '2023',
                                          29988,
                                          ('Gads',
                                           'Dati_par_periodu_No',
                                           'Dati_par_periodu_Lidz',
                                           'Ministrija_Atslega',
                                           'Ministrija_nosaukums',
                                           'Iestade_Atslega',
                                           'Iestade_nosaukums',
                                           'Budzeta_tips_Atslega',
                                           'Budzeta_tips_nosaukums',
                                           'Programma_Atslega',
                                           'Programma_nosaukums',
                                           'Apaksprogramma_Atslega',
                                           'Apaksprogramma_nosaukums',
                                           'Funkcija_Atslega',
                                           'Funkcija_nosaukums',
                                           'Saistibu_veids_Atslega',
                                           'Saistibu_veids_nosaukums',
                                           'Projekta_arejais_kods_Atslega',
                                           'Projekts_nosaukums',
                                           'Vienotais_EKK_Atslega',
                                           'Vienotais_EKK_nosaukums',
                                           'Datu_valuta',
                                           'Finansesanas_plans_gadam_ar_izmainam',
                                           'Ienemumi',
                                           'Izdevumi',
                                           'Finansesana'))}

# Payload-data fingerprints exclude conversion time; they pin normalized fields,
# dictionaries, rows and the separately carried source subtotal.
NORMALIZED = {'17ea37f3-e946-49a1-adf0-a6dbd0e03554': '0730ad86ee7f816a5e9b644def89bab43906de832059050f69098bf1dc8d3546',
 '1b192cdf-d194-4a22-a55e-3839668caca2': 'b204690c3a032aba364a17453c3f3fbfa940dedad35fc7a2a4198546ee05d30c',
 'ee5889d5-e35e-46a0-beb2-3a317a9a64cd': 'e72d717bd787e125b1b2e27ad1f4ba7126e0b686de562b9be81076fbff12588b',
 '32343873-19c3-49ec-b280-692b62730a59': 'd8be6b54747e10f7620ab29b7bf21fc96cfcc2ed3774aa41b9a01e0aae3466b9',
 'b8577673-d974-4b94-a541-11d0db1bda43': '43df734abc626d8c12c22a161c733a358466c342338805c3029aa8acb2baee69',
 'f0046fd5-3464-4793-a0e8-8852713b3f25': '569b330db53ad0576627056881a3eb28aec003119bfe1610b61d3b0c581138b4',
 '8c8ff425-d200-4a04-90c6-398508b8329b': '82fdf2335356d51e31f933f57d624d023bdadd1b38870018ae496fd0a4abd7b5'}


def sha(content):
    return hashlib.sha256(content).hexdigest()


def report_scope(rid):
    scope = {'year': SOURCES[rid][4]}
    if rid == FEB:
        scope.update({'from': '2023.01.01.', 'through': '2023.02.28.'})
    return scope


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'LatvijasDatiExplorer/1.1'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        if response.geturl() != url or response.status != 200:
            raise ValueError('Unexpected historical spreadsheet response')
        return response.read(MAX_ARCHIVE + 1)


def col_types(rid, count):
    return ['text'] * (count - 4) + ['decimal'] * 4 if rid == FEB else ['text'] * (count - 1) + ['number']


def amount(cell, kind):
    raw = cell.findtext('m:v', namespaces=NS) if cell is not None else None
    if (raw is None or len(raw) > 64 or cell.get('t', 'n') != 'n'
            or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?', raw)):
        raise ValueError('Historical spreadsheet contains invalid or missing EUR amount')
    exact = Decimal(raw)
    if abs(exact) > 2**53 - 1 or (kind == 'number' and exact != exact.to_integral_value()):
        raise ValueError('Historical spreadsheet amount outside reviewed precision')
    # Preserve the exact XML decimal lexical value (including any Excel binary
    # rounding artefacts) rather than coercing to a Python or JavaScript float.
    return raw if kind == 'decimal' else int(exact)


def verify_footer(indexed):
    cell = indexed.get(5)
    formula = cell.find('m:f', NS) if cell is not None else None
    if (cell is None or cell.get('r') != SUBTOTAL['cell'] or formula is None
            or formula.text != SUBTOTAL['formula'] or amount(cell, 'number') != SUBTOTAL['value']):
        raise ValueError('Source subtotal is missing or changed')
    return dict(SUBTOTAL)


def parse_workbook(rid, content):
    _, _, _, sheet_name, _, count, headers = SOURCES[rid]
    types = col_types(rid, len(headers))
    scope = report_scope(rid)
    if len(content) > MAX_ARCHIVE:
        raise ValueError('Historical spreadsheet exceeds compressed size limit')
    with zipfile.ZipFile(io.BytesIO(content)) as book:
        items = book.infolist()
        names = [item.filename for item in items]
        if len(names) > 100 or len(set(names)) != len(names) or sum(item.file_size for item in items) > MAX_EXPANDED:
            raise ValueError('Historical spreadsheet XML archive exceeds limits')
        specs = ('xl/workbook.xml', 'xl/_rels/workbook.xml.rels')
        if any(book.getinfo(path).file_size > 1024 * 1024 for path in specs):
            raise ValueError('Unexpected large historical workbook metadata')
        workbook, rels = (ET.fromstring(book.read(path)) for path in specs)
        sheets = workbook.find('m:sheets', NS)
        if (sheets is None or len(sheets) != 1 or sheets[0].get('name') != sheet_name
                or sheets[0].get('state', 'visible') != 'visible'):
            raise ValueError('Expected a single reviewed visible worksheet')
        targets = [rel.get('Target') for rel in rels if rel.get('Id') == sheets[0].get(REL)
                   and rel.get('TargetMode') != 'External']
        if len(targets) != 1 or not re.fullmatch(r'/?(?:xl/)?worksheets/sheet[1-9][0-9]*\.xml', targets[0] or ''):
            raise ValueError('Bad historical worksheet relationship')
        target = targets[0].lstrip('/')
        if not target.startswith('xl/'):
            target = 'xl/' + target
        strings = []
        if 'xl/sharedStrings.xml' in names:
            with book.open('xl/sharedStrings.xml') as handle:
                for _, el in ET.iterparse(handle, events=('end',)):
                    if el.tag == '{' + NS['m'] + '}si':
                        entry = ''.join(t.text or '' for t in el.findall('.//m:t', NS))
                        if len(entry) > 4096 or len(strings) >= MAX_ROWS:
                            raise ValueError('Historical spreadsheet string limit exceeded')
                        strings.append(entry)
                        el.clear()
        found_header, footer, rows = False, None, []
        lookups = [{} for _ in headers]
        last = 0
        with book.open(target) as handle:
            for _, el in ET.iterparse(handle, events=('end',)):
                tag = el.tag.rsplit('}', 1)[-1]
                if tag == 'mergeCell':
                    raise ValueError('Unexpected merge in historical spreadsheet')
                if tag != 'row':
                    continue
                rowno = int(el.get('r'))
                if not last < rowno <= MAX_ROWS + 2 or el.get('hidden') in ('1', 'true'):
                    raise ValueError('Historical worksheet row order/visibility limit exceeded')
                last = rowno
                indexed = {}
                values = {}
                for cell in el.findall('m:c', NS):
                    address = cell.get('r', '')
                    i = col_index(address)
                    if address.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ') != str(rowno) or i in indexed:
                        raise ValueError('Invalid or duplicate historical worksheet coordinate')
                    if cell.get('t') == 's':
                        shared_index = cell.findtext('m:v', namespaces=NS)
                        if not re.fullmatch(r'[0-9]{1,6}', shared_index or '') or int(shared_index) >= len(strings):
                            raise ValueError('Invalid shared string in historical worksheet')
                    indexed[i] = cell
                    values[i] = cell_value(cell, strings)
                    if i >= len(headers) and (values[i] is not None or cell.find('m:f', NS) is not None):
                        raise ValueError('Extra columns in historical worksheet')
                el.clear()
                present = [i for i, val in values.items() if val is not None]
                if not present:
                    continue
                formulas = [i for i, cell in indexed.items() if cell.find('m:f', NS) is not None]
                if rid == FOOTER and found_header and rowno == 31030 and present == [5] and formulas == [5]:
                    footer = verify_footer(indexed)
                    continue
                if formulas:
                    raise ValueError('Unexpected formula in historical worksheet data')
                if not found_header:
                    if rowno != 1 or tuple(values.get(i) for i in range(len(headers))) != headers:
                        raise ValueError('Historical worksheet heading changed')
                    found_header = True
                    continue
                if (footer is not None or values.get(0) != scope['year'] or len(rows) >= count
                        or (rid == FEB and (values.get(1), values.get(2), values.get(21))
                            != (scope['from'], scope['through'], 'Euro'))):
                    raise ValueError('Historical worksheet year, period, currency or size changed')
                result = []
                for i, kind in enumerate(types):
                    value = values.get(i) if kind == 'text' else amount(indexed.get(i), kind)
                    if kind == 'text' and (value is not None and (type(value) is not str or len(value) > 4096)
                                           or (value is None and rid != FEB)):
                        raise ValueError('Historical worksheet text column changed')
                    if value is not None and kind != 'number':
                        value = lookups[i].setdefault(value, len(lookups[i]))
                    result.append(value)
                rows.append(result)
        if not found_header or len(rows) != count or (rid == FOOTER and footer is None):
            raise ValueError('Historical worksheet is not complete')
    fields = [{'id': header, 'type': kind, **({'dictionary': list(lookups[i])} if kind != 'number' else {})}
              for i, (header, kind) in enumerate(zip(headers, types))]
    return {'sheets': [{'name': sheet_name, 'fields': fields, 'rows': rows, 'total': count,
                        'cachedFormulaCount': 0}],
            **({'sourceSubtotal': footer} if footer is not None else {})}


def asset_path(rid, digest):
    return f'{DIR}/{rid}-v1-{digest}.json'


def provenance(rid):
    _, url, source_digest, _, _, _, _ = SOURCES[rid]
    return {'sourceUrl': url, 'sourceFormat': 'XLSX', 'sourceSha256': source_digest,
            'previewKind': KIND, 'reportScope': report_scope(rid)}


def fresh_resource(rid, source_dir):
    _, url, approved_digest, _, _, count, _ = SOURCES[rid]
    if source_dir is None:
        content = download(url)
    else:
        with (source_dir / f'{rid}.xlsx').open('rb') as handle:
            content = handle.read(MAX_ARCHIVE + 1)
    if len(content) > MAX_ARCHIVE or sha(content) != approved_digest:
        raise ValueError(f'Historical source {rid} changed; independent review required')
    data = parse_workbook(rid, content)
    if sha(json_bytes(data)) != NORMALIZED[rid]:
        raise ValueError(f'Historical preview {rid} no longer matches its reviewed output')
    meta = {**provenance(rid), 'convertedAt': datetime.now(timezone.utc).isoformat()}
    encoded = json_bytes({'schemaVersion': 1, 'resourceId': rid, **meta, **data})
    if len(encoded) > MAX_PREVIEW:
        raise ValueError('Historical preview exceeds browser size limit')
    digest = sha(encoded)
    return {'path': asset_path(rid, digest), 'sha256': digest, 'total': count, **meta}, encoded


def find_resources(catalog):
    selected = {}
    for rid, (dsid, url, *_) in SOURCES.items():
        dataset = exactly_one(catalog['datasets'], 'id', dsid, 'dataset')
        if (dataset.get('license_id') not in ('CC0-1.0', 'cc-zero') or dataset.get('private', False)
                or (dataset.get('organization') or {}).get('name') != 'valsts-kase'):
            raise ValueError('Historical Treasury dataset is not verified public CC0')
        res = exactly_one(dataset['resources'], 'id', rid, 'resource')
        if res.get('url') != url or res.get('format', '').upper() != 'XLSX':
            raise ValueError('Historical Treasury original link or format changed')
        if res.get('local_preview') and res['local_preview'].get('previewKind') != KIND:
            raise ValueError('Refusing to replace another published preview')
        selected[rid] = res
    return selected


def obtain_standby():
    selected = find_resources(parse_json(fetch_pages('data/catalog.json', MAX_CATALOG)))
    if not any(res.get('local_preview') for res in selected.values()):
        return {}
    result = {}
    for rid, resource in selected.items():
        preview = resource.get('local_preview')
        meta = provenance(rid)
        if not isinstance(preview, dict) or any(preview.get(k) != v for k, v in meta.items()):
            raise ValueError('No complete reviewed historical preview group to fall back to')
        digest = preview.get('sha256', '')
        if (not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or preview.get('path') != asset_path(rid, digest) or preview.get('total') != SOURCES[rid][5]):
            raise ValueError('Invalid historical standby pointer')
        timestamp(preview['convertedAt'])
        encoded = fetch_pages(preview['path'], MAX_PREVIEW)
        if sha(encoded) != digest or len(encoded) > MAX_PREVIEW:
            raise ValueError('Historical standby checksum mismatch')
        value = parse_json(encoded)
        if any(value.pop(k, None) != v for k, v in {
            **meta, 'convertedAt': preview['convertedAt'], 'schemaVersion': 1, 'resourceId': rid,
        }.items()) or sha(json_bytes(value)) != NORMALIZED[rid]:
            raise ValueError('Historical standby does not match reviewed normalized data')
        result[rid] = ({**preview, 'snapshotFallback': True}, encoded)
    return result


def sync(source_dir=None, *, root=None, allow_standby=False):
    public = (ROOT if root is None else Path(root)) / 'public'
    catalog_path = public / 'data/catalog.json'
    catalog = json.loads(catalog_path.read_bytes())
    selected = find_resources(catalog)
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(zip(SOURCES, pool.map(lambda rid: fresh_resource(rid, source_dir), SOURCES)))
    except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError) as exc:
        if not allow_standby or source_dir is not None:
            raise
        print(f'::warning::Reviewed historical reports were not updated: {exc}', flush=True)
        results = obtain_standby()
        if not results:
            print('::warning::No previous historical preview group; leaving existing unrelated previews alone.', flush=True)
            return {}
    created = []
    try:
        for rid, (preview, encoded) in results.items():
            path = public / preview['path']
            if path.exists():
                if len(encoded) != path.stat().st_size or sha(path.read_bytes()) != preview['sha256']:
                    raise ValueError('Conflicting existing historical preview')
            else:
                atomic_bytes(path, encoded)
                created.append(path)
            selected[rid]['local_preview'] = preview
        atomic_bytes(catalog_path, json_bytes(catalog))
    except Exception:
        cleanup_created(created)
        raise
    keep = {preview['path'] for preview, _ in results.values()}
    for rid in SOURCES:
        for old in (public / DIR).glob(f'{rid}-v1-*.json'):
            if old.relative_to(public).as_posix() not in keep:
                old.unlink(missing_ok=True)
    print(f'Reviewed historical spreadsheets: {len(results)}; {sum(v[0]["total"] for v in results.values())} rows', flush=True)
    return {rid: preview for rid, (preview, _) in results.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--allow-standby', action='store_true')
    args = parser.parse_args()
    sync(args.source_dir, allow_standby=args.allow_standby)


if __name__ == '__main__':
    main()

"""Strict, manifest-pinned XLSX table reader; does not run formulas or links."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal

from sync_xlsx import NS, REL, cell_value, col_index

MAX_EXPANDED = 12 * 1024 * 1024
MAX_ROWS = 5000
MAX_WIDTH = 32
MAX_CELL = 256
LEXICAL_DECIMAL = re.compile(r'-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?')


def cell_text(cell, lookup):
    if cell.find('m:f', NS) is not None:
        raise ValueError('Formula outside reviewed public table')
    raw = cell.findtext('m:v', namespaces=NS)
    kind = cell.get('t', 'n')
    if kind == 's' and (not re.fullmatch(r'[0-9]{1,6}', raw or '') or int(raw) >= len(lookup)):
        raise ValueError('Invalid public table shared string')
    if kind == 'n' and raw is not None:
        if len(raw) > 64 or not LEXICAL_DECIMAL.fullmatch(raw) or abs(Decimal(raw)) > 2**53 - 1:
            raise ValueError('Unsupported public table numeric value')
        return raw, 'decimal'
    value = cell_value(cell, lookup)
    if value is not None and (type(value) is not str or len(value) > MAX_CELL):
        raise ValueError('Unsupported public table text value')
    return value, 'text'


def sheets_from(book):
    names = book.namelist()
    if len(names) > 100 or len(set(names)) != len(names) or sum(x.file_size for x in book.infolist()) > MAX_EXPANDED:
        raise ValueError('Public spreadsheet archive limits exceeded')
    paths = ('xl/workbook.xml', 'xl/_rels/workbook.xml.rels')
    if any(book.getinfo(p).file_size > 1024 * 1024 for p in paths):
        raise ValueError('Public workbook metadata size exceeded')
    workbook, rels = (ET.fromstring(book.read(p)) for p in paths)
    props = workbook.find('m:workbookPr', NS)
    if props is not None and props.get('date1904') not in (None, '0', 'false'):
        raise ValueError('Public workbook date system not reviewed')
    refs = {}
    for rel in rels:
        key, target = rel.get('Id'), rel.get('Target')
        if rel.get('TargetMode') == 'External' or key in refs:
            raise ValueError('Public workbook has unreviewed external or duplicate links')
        refs[key] = target
    sheets = workbook.findall('m:sheets/m:sheet', NS)
    if len(sheets) != 1 or sheets[0].get('state', 'visible') != 'visible':
        raise ValueError('Expected a single visible public worksheet')
    sheet = sheets[0]
    part = refs.get(sheet.get(REL), '')
    if not re.fullmatch(r'/?(?:xl/)?worksheets/sheet[1-9][0-9]*\.xml', part):
        raise ValueError('Public worksheet relationship invalid')
    part = part.lstrip('/')
    if not part.startswith('xl/'):
        part = 'xl/' + part
    return sheet.get('name'), part


def shared_strings(book):
    if 'xl/sharedStrings.xml' not in book.namelist():
        return []
    out = []
    with book.open('xl/sharedStrings.xml') as handle:
        for _, el in ET.iterparse(handle, events=('end',)):
            if el.tag.rsplit('}', 1)[-1] != 'si':
                continue
            s = ''.join(x.text or '' for x in el.findall('.//m:t', NS))
            if len(out) >= MAX_ROWS * MAX_WIDTH or len(s) > MAX_CELL:
                raise ValueError('Public worksheet text limits exceeded')
            out.append(s)
            el.clear()
    return out


def parse_xlsx(content, spec):
    """Parse only one allowlisted sheet, matching the declared columns and rows."""
    width = len(spec.headers)
    if not 2 <= width <= MAX_WIDTH or not 1 <= spec.header_row <= 12:
        raise ValueError('Public workbook reviewed profile has invalid bounds')
    decimals = set(spec.decimal_columns)
    if any(not 0 <= x < width for x in decimals):
        raise ValueError('Public workbook reviewed profile has invalid column types')
    with zipfile.ZipFile(io.BytesIO(content)) as book:
        name, part = sheets_from(book)
        if name != spec.sheet_name:
            raise ValueError('Public worksheet title changed')
        lookup = shared_strings(book)
        dictionaries, rows, preamble = [{} for _ in range(width)], [], []
        found_header, prev = False, 0
        with book.open(part) as handle:
            for _, el in ET.iterparse(handle, events=('end',)):
                tag = el.tag.rsplit('}', 1)[-1]
                if tag == 'mergeCell':
                    raise ValueError('Unreviewed merged cells in public worksheet')
                if tag == 'col' and el.get('hidden') in ('true', '1'):
                    raise ValueError('Unreviewed hidden column in public worksheet')
                if tag != 'row':
                    continue
                nr = int(el.get('r'))
                if not prev < nr <= MAX_ROWS + 15 or el.get('hidden') in ('true', '1'):
                    raise ValueError('Unreviewed row position in public worksheet')
                prev = nr
                values, seen = {}, set()
                for cell in el.findall('m:c', NS):
                    coord = cell.get('r', '')
                    i = col_index(coord)
                    if coord.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ') != str(nr) or i in seen:
                        raise ValueError('Invalid or duplicate public worksheet coordinates')
                    seen.add(i)
                    value, typ = cell_text(cell, lookup)
                    if value is not None and value != '':
                        if i >= width:
                            raise ValueError('Unexpected public table content beyond reviewed headers')
                        if nr > spec.header_row and typ != ('decimal' if i in decimals else 'text'):
                            raise ValueError('Public table column type changed')
                        values[i] = value
                el.clear()
                if not values:
                    continue
                if nr < spec.header_row:
                    preamble.extend(values.values())
                    continue
                vals = [values.get(i) for i in range(width)]
                if not found_header:
                    if nr != spec.header_row or tuple(vals) != spec.headers:
                        raise ValueError('Public worksheet headers differ from review')
                    found_header = True
                    continue
                if len(rows) >= spec.row_count:
                    raise ValueError('Public worksheet exceeds reviewed rows')
                rows.append([None if v is None else dictionaries[i].setdefault(v, len(dictionaries[i]))
                             for i, v in enumerate(vals)])
    if not found_header or len(rows) != spec.row_count or not rows or tuple(preamble) != (spec.preamble or ()):
        raise ValueError('Public worksheet did not match reviewed rows and title')
    return {'name': name, 'fields': [{'id': label, 'type': 'decimal' if i in decimals else 'text',
                                       'dictionary': list(dictionaries[i])}
                                      for i, label in enumerate(spec.headers)],
            'rows': rows, 'total': len(rows), 'cachedFormulaCount': 0,
            **({'sourceCaption': ' · '.join(preamble)} if preamble else {})}

from dataclasses import replace
from pathlib import Path
import io
import json
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from parse_public_table_xlsx import parse_xlsx
from sync_csv_preview import ReviewedSource, SourceChanged, json_bytes, parse_csv, sha256, sync


def workbook(rows, sheet='Sheet1', state='visible', after=''):
    xml = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{xml}" xmlns:r="{rel}"><sheets>'
                   f'<sheet name="{sheet}" state="{state}" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships>'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{xml}"><sheetData>{rows}'
                   f'</sheetData>{after}</worksheet>')
    return output.getvalue()


class FirstPreviewTests(unittest.TestCase):
    def test_xlsx_preserves_source_lexemes_and_rejects_formulas(self):
        sample = '<row r="1"><c r="A1" t="inlineStr"><is><t>Kods</t></is></c>' \
                 '<c r="B1" t="inlineStr"><is><t>Skaits</t></is></c></row>' \
                 '<row r="2"><c r="A2" t="inlineStr"><is><t>00060</t></is></c>' \
                 '<c r="B2"><v>-4754.1400000000003</v></c></row>'
        content = workbook(sample)
        spec = ReviewedSource('ds', 'rid', 'aggregate.xlsx', sha256(content), ('Kods','Skaits'), 0, 1,
                              source_format='XLSX', sheet_name='Sheet1', decimal_columns=(1,))
        got = parse_xlsx(content, spec)
        self.assertEqual(got['name'], 'Sheet1')
        self.assertEqual(got['fields'][0]['dictionary'], ['00060'])
        self.assertEqual(got['fields'][1]['dictionary'], ['-4754.1400000000003'])
        self.assertEqual(got['fields'][1]['type'], 'decimal')
        with self.assertRaisesRegex(ValueError, 'Formula'):
            parse_xlsx(workbook(sample.replace('<v>-4754', '<f>1+1</f><v>-4754')), spec)
        with self.assertRaisesRegex(ValueError, 'visible'):
            parse_xlsx(workbook(sample, state='hidden'), spec)
        with self.assertRaisesRegex(ValueError, 'column type changed'):
            parse_xlsx(content, replace(spec, decimal_columns=()))

    def test_csv_reviewed_footer_visible_but_not_counted(self):
        content = 'Gads;Mēnesis;\n2023;01;\n;;\nAvota piezīme;;\n'.encode()
        spec = ReviewedSource('ds', 'rid', 'aggregate.csv', sha256(content), ('Gads','Mēnesis'), 1, 1,
                              footer=('Avota piezīme','',''))
        got = parse_csv(content, spec)
        self.assertEqual(got['sourceFooter'], 'Avota piezīme')
        self.assertEqual(got['total'], 1)
        self.assertEqual(got['fields'][1]['dictionary'], ['01'])
        inserted = content + '2024;01;\n'.encode()
        with self.assertRaisesRegex(ValueError, 'after reviewed'):
            parse_csv(inserted, replace(spec, sha256=sha256(inserted)))

    def test_xlsx_audited_offset_and_footer_do_not_consume_rows(self):
        def inline(cell, val):
            return f'<c r="{cell}" t="inlineStr"><is><t>{val}</t></is></c>'

        label = 'Piezīme ar precīzām atstarpēm: ' + ' ' * 260 + 'nesummēt.'
        header = f'<row r="1">{inline("B1", "Periods")}{inline("C1", "Vērtība")}</row>'
        body = f'<row r="2">{inline("B2", "2026Q1")}<c r="C2"><v>1.0000000000000002</v></c></row>'
        footer = f'<row r="5">{inline("B5", label)}</row><row r="6">{inline("B6", "Otra piezīme.")}</row>'
        merge = '<mergeCells><mergeCell ref="B5:C5"/></mergeCells>'
        content = workbook(header + body + footer, after=merge)
        source = ReviewedSource('ds', 'rid', 'aggregate.xlsx', sha256(content), ('Periods', 'Vērtība'), 0, 1,
                                source_format='XLSX', sheet_name='Sheet1', decimal_columns=(1,), first_column=1,
                                xlsx_footer_cells=('B5', 'B6'), xlsx_footer_merges=('B5:C5',), scope_note='2026. gada 1. ceturksnis.')
        data = parse_xlsx(content, source)
        self.assertEqual(data['rows'], [[0, 0]])
        self.assertEqual(data['fields'][1]['dictionary'], ['1.0000000000000002'])
        self.assertEqual(data['sourceFooter'], label + '\nOtra piezīme.')
        self.assertEqual(data['scopeNote'], source.scope_note)
        for bad, message in (
            (workbook(header + body + footer, after=merge.replace('B5:C5', 'B2:C2')), 'Unreviewed merged'),
            (workbook(header + body + footer.replace('</is></c></row><row r="6">', '</is></c>' + inline('C5', 'Pārsteigums') + '</row><row r="6">'), after=merge), 'notes area'),
            (workbook(header.replace('<row r="1">', '<row r="1">' + inline('A1', 'Pārsteigums')) + body + footer, after=merge), 'beyond reviewed headers'),
            (workbook(header + body + footer[:footer.index('<row r="6">')], after=merge), 'source notes differ'),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_xlsx(bad, source)

    def test_xlsx_cohort_does_not_publish_first_valid_snapshot_when_later_bytes_changed(self):
        xml = ('<row r="1"><c r="A1" t="inlineStr"><is><t>Periods</t></is></c>'
               '<c r="B1" t="inlineStr"><is><t>Vērtība</t></is></c></row>'
               '<row r="2"><c r="A2" t="inlineStr"><is><t>2026Q1</t></is></c><c r="B2"><v>1</v></c></row>')
        content = workbook(xml)
        spec = ReviewedSource('ds', 'first', 'report.xlsx', sha256(content), ('Periods','Vērtība'), 0, 1,
                              source_format='XLSX', sheet_name='Sheet1', decimal_columns=(1,))
        spec = replace(spec, table_sha256=sha256(json_bytes(parse_xlsx(content, spec))))
        later = replace(spec, resource_id='second')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / 'public/data/catalog.json'
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps({'datasets': [{'id':'ds', 'license_id':'CC0-1.0',
                'organization':{'name':'iub'}, 'resources': [{'id': s.resource_id, 'url':s.url, 'format':'XLSX'}
                    for s in (spec, later)]}]}), encoding='utf-8')
            before = catalog.read_bytes()
            (root/'first.xlsx').write_bytes(content)
            (root/'second.xlsx').write_bytes(content + b' ')
            with self.assertRaisesRegex(SourceChanged, 'review required: second'):
                sync(root, root, sources=(spec, later), allow_standby=True)
            self.assertEqual(catalog.read_bytes(), before)
            self.assertFalse((catalog.parent/'public-xlsx').exists())

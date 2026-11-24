from dataclasses import replace
from pathlib import Path
import io
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from parse_public_table_xlsx import parse_xlsx
from sync_csv_preview import ReviewedSource, parse_csv, sha256


def workbook(rows, sheet='Sheet1', state='visible'):
    xml = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{xml}" xmlns:r="{rel}"><sheets>'
                   f'<sheet name="{sheet}" state="{state}" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships>'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{xml}"><sheetData>{rows}'
                   '</sheetData></worksheet>')
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

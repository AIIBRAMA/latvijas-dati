"""Small OOXML fixtures test source semantics and fail-closed conversion."""
import importlib.util
import io
import sys
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('sync_xlsx', Path(__file__).resolve().parents[1] / 'scripts/sync_xlsx.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HEADERS = ['Gads', 'Menesis_nr', 'Iestade', 'Datu_valuta', 'Summa', 'Kods']


def fixture(extra='', headers=None, amount='<v>-25</v>'):
    headers = headers or HEADERS
    cells = ''.join(f'<c r="{chr(65+i)}1" t="inlineStr"><is><t>{h}</t></is></c>' for i,h in enumerate(headers))
    rows = f'<row r="1">{cells}</row><row r="2"><c r="A2"><v>2025</v></c><c r="B2" t="inlineStr"><is><t>#</t></is></c><c r="C2" t="inlineStr"><is><t>Rīgas iestāde</t></is></c><c r="D2" t="inlineStr"><is><t>EUR</t></is></c><c r="E2">{amount}</c><c r="F2" t="inlineStr"><is><t>001</t></is></c></row>'
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, 'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Budžets" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{rows}</sheetData>{extra}</worksheet>')
    return memory.getvalue()


class ImportTests(unittest.TestCase):
    def test_values_and_markers(self):
        sheet = module.parse_xlsx(fixture())[0]
        self.assertEqual(sheet['total'],1)
        self.assertEqual(sheet['rows'][0][4],-25)
        self.assertEqual(sheet['fields'][1]['dictionary'],['#'])
        self.assertEqual(sheet['fields'][5]['dictionary'],['001'])

    def test_ambiguous_layout_rejected(self):
        with self.assertRaisesRegex(ValueError,'Merged'):
            module.parse_xlsx(fixture('<mergeCells><mergeCell ref="A1:B1"/></mergeCells>'))
        with self.assertRaisesRegex(ValueError,'unique'):
            module.parse_xlsx(fixture(headers=['Gads','Gads',*HEADERS[2:]]))
        with self.assertRaisesRegex(ValueError,'required'):
            module.parse_xlsx(fixture(headers=['Periods',*HEADERS[1:]]))

    def test_formula_requires_cached_result(self):
        with self.assertRaisesRegex(ValueError,'cached result'):
            module.parse_xlsx(fixture(amount='<f>1+1</f>'))
        sheet=module.parse_xlsx(fixture(amount='<f>1+1</f><v>2</v>'))[0]
        self.assertEqual(sheet['rows'][0][4],2)
        self.assertEqual(sheet['cachedFormulaCount'],1)

    def test_download_is_restricted_to_public_source(self):
        for url in ['http://data.gov.lv/x','https://example.com/x','https://127.0.0.1/x','file:///tmp/x','https://data.gov.lv:444/x','https://user:pass@data.gov.lv/x']:
            with self.assertRaises(ValueError):module.trusted_url(url)
        self.assertEqual(module.trusted_url('https://data.gov.lv/dati/file.xlsx'),'https://data.gov.lv/dati/file.xlsx')


if __name__ == '__main__':
    unittest.main()

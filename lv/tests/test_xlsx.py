"""Small OOXML fixtures test source semantics and fail-closed conversion."""
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sync_xlsx', Path(__file__).resolve().parents[1] / 'scripts/sync_xlsx.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HEADERS = ['Gads', 'Menesis_nr', 'Iestade', 'Datu_valuta', 'Summa', 'Kods']


def fixture(extra='', headers=None, amount='<v>-25</v>', *, name='Budžets', overflow='', header_extra=''):
    headers = headers or HEADERS
    def column(i):
        return chr(65+i) if i < 26 else 'A' + chr(65+i-26)
    cells = ''.join(f'<c r="{column(i)}1" t="inlineStr"><is><t>{h}</t></is></c>' for i,h in enumerate(headers))
    if 'Novadi_pilsetas' in headers:
        total = column(headers.index('Summa'))
        currency = column(headers.index('Valuta'))
        rows = (f'<row r="1">{cells}{header_extra}</row>'
                '<row r="2"><c r="A2"><v>2026</v></c><c r="B2" t="inlineStr"><is><t>#</t></is></c>'
                '<c r="E2" t="inlineStr"><is><t>Aizkraukles novads</t></is></c>'
                '<c r="F2" t="inlineStr"><is><t>0020000</t></is></c>'
                f'<c r="{currency}2" t="inlineStr"><is><t>EUR</t></is></c>'
                f'<c r="{total}2">{amount}</c>{overflow}</row>')
    elif headers == module.EKK_HEADERS:
        rows = (f'<row r="1">{cells}{header_extra}</row>'
                '<row r="2"><c r="A2"><v>2026</v></c><c r="AF2"><v>23</v></c></row>'
                f'<row r="3"><c r="A3"><v>2026</v></c><c r="AF3"><v>25</v></c>{overflow}</row>')
    else:
        rows = f'<row r="1">{cells}</row><row r="2"><c r="A2"><v>2025</v></c><c r="B2" t="inlineStr"><is><t>#</t></is></c><c r="C2" t="inlineStr"><is><t>Rīgas iestāde</t></is></c><c r="D2" t="inlineStr"><is><t>EUR</t></is></c><c r="E2">{amount}</c><c r="F2" t="inlineStr"><is><t>001</t></is></c>{overflow}</row>'
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, 'w') as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{rows}</sheetData>{extra}</worksheet>')
    return memory.getvalue()


class ImportTests(unittest.TestCase):
    def test_exact_municipal_layouts_preserve_names_and_atvk(self):
        for resource_id, (name, headers) in module.MUNICIPAL_LAYOUTS.items():
            with self.subTest(resource_id=resource_id):
                source = fixture(headers=headers, name=name)
                sheet = module.parse_xlsx(source, resource_id=resource_id)[0]
                fields = {field['id']: field for field in sheet['fields']}
                self.assertEqual(tuple(fields), headers)
                self.assertEqual(sheet['total'], 1)
                self.assertEqual(sheet['rows'][0][-1], -25)
                self.assertEqual(fields['ATVK']['dictionary'], ['0020000'])
                self.assertEqual(fields['Menesis_nr']['dictionary'], ['#'])
                self.assertEqual(fields['Valuta']['dictionary'], ['EUR'])

    def test_municipal_layout_scope_and_overflow(self):
        name, headers = module.MUNICIPAL_LAYOUTS[module.MUNICIPAL_EKK]
        source = fixture(headers=headers, name=name)
        with self.assertRaisesRegex(ValueError, 'required'):
            module.parse_xlsx(source, resource_id=module.EKK_RESOURCE)
        with self.assertRaisesRegex(ValueError, 'worksheet layout changed'):
            module.parse_xlsx(source, resource_id=module.MUNICIPAL_FKK)
        changed = (*headers[:3], 'Changed', *headers[4:])
        with self.assertRaisesRegex(ValueError, 'column layout changed'):
            module.parse_xlsx(fixture(headers=changed, name=name), resource_id=module.MUNICIPAL_EKK)
        with self.assertRaisesRegex(ValueError, 'outside header'):
            module.parse_xlsx(fixture(headers=headers, name=name, overflow='<c r="AC2"><v>1</v></c>'),
                              resource_id=module.MUNICIPAL_EKK)

    def test_cli_updates_all_four_pointers_only_after_all_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / 'sources'
            source_dir.mkdir()
            catalog_path = root / 'public/data/catalog.json'
            catalog = {'datasets': [{
                'id': dataset_id,
                'resources': [{'id': resource_id, 'url': f'https://data.gov.lv/{resource_id}.xlsx'}
                              for resource_id in resources],
            } for dataset_id, resources in module.RESOURCE_GROUPS.items()]}
            module.atomic_json(catalog_path, catalog)
            for resource_id in module.RESOURCES:
                layout = module.MUNICIPAL_LAYOUTS.get(resource_id)
                workbook = fixture(name=layout[0], headers=layout[1]) if layout else fixture()
                (source_dir / f'{resource_id}.xlsx').write_bytes(workbook)
            last = source_dir / f'{module.MUNICIPAL_FKK}.xlsx'
            with patch.object(module, 'ROOT', root), patch.object(sys, 'argv', ['sync_xlsx', '--source-dir', str(source_dir)]):
                module.main()
                previous_catalog = catalog_path.read_bytes()
                previous_files = {p.name: p.read_bytes() for p in (root / 'public/data/xlsx').glob('*.json')}
                last.write_bytes(fixture())
                with self.assertRaisesRegex(ValueError, 'worksheet layout changed'):
                    module.main()
                self.assertEqual(catalog_path.read_bytes(), previous_catalog)
                self.assertEqual({p.name: p.read_bytes() for p in (root / 'public/data/xlsx').glob('*.json')}, previous_files)
            result = json.loads(catalog_path.read_bytes())
            previews = [r['local_preview'] for d in result['datasets'] for r in d['resources']]
            self.assertEqual(len(previews), 4)
            for preview in previews:
                self.assertEqual(preview['sourceFormat'], 'XLSX')
                self.assertEqual(preview['total'], 1)
                payload = json.loads((root / 'public' / preview['path']).read_bytes())
                self.assertEqual(payload['sourceFormat'], 'XLSX')
                self.assertEqual(payload['sourceSha256'], preview['sourceSha256'])

    def test_reviewed_ekk_column_preserves_marker_and_blank(self):
        for header_extra in ('', '<c r="AG1"/>'):
            with self.subTest(header_extra=header_extra):
                source = fixture(headers=module.EKK_HEADERS, name=module.EKK_SHEET,
                                 overflow='<c r="AG3"><v>1</v></c>', header_extra=header_extra)
                sheet = module.parse_xlsx(source, resource_id=module.EKK_RESOURCE)[0]
                self.assertEqual(sheet['fields'][-1], {
                    'id': module.AG_HEADER, 'type': 'text', 'dictionary': ['1']})
                self.assertEqual([row[-2:] for row in sheet['rows']], [[23, None], [25, 0]])

    def test_other_orphan_values_and_resources_rejected(self):
        variants = ['<c r="AG3"><v>2</v></c>', '<c r="AG3" t="b"><v>1</v></c>',
                    '<c r="AG3"><f>1</f><v>1</v></c>', '<c r="AH3"><v>1</v></c>']
        for overflow in variants:
            with self.subTest(overflow=overflow), self.assertRaisesRegex(ValueError, 'outside header'):
                module.parse_xlsx(fixture(headers=module.EKK_HEADERS, name=module.EKK_SHEET,
                                          overflow=overflow), resource_id=module.EKK_RESOURCE)
        with self.assertRaisesRegex(ValueError, 'outside header'):
            module.parse_xlsx(fixture(headers=module.EKK_HEADERS, name=module.EKK_SHEET,
                                      overflow='<c r="AG3"><v>1</v></c>'), resource_id=module.RESOURCES[1])
        with self.assertRaisesRegex(ValueError, 'outside header'):
            module.parse_xlsx(fixture(overflow='<c r="G2"><v>1</v></c>'), resource_id=module.EKK_RESOURCE)

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

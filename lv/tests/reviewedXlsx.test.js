import test from 'node:test';
import assert from 'node:assert/strict';
import {validateWorkbook, localPreviewPath, rowsCsv} from '../src/localPreview.js';

const footerId = 'ee5889d5-e35e-46a0-beb2-3a317a9a64cd';
const feb = '8c8ff425-d200-4a04-90c6-398508b8329b';
function fixture(id, reportScope, fields, row) {
    const meta = {sourceUrl: 'https://data.gov.lv/test', sourceSha256: 'a'.repeat(64),
        sourceFormat: 'XLSX', convertedAt: '2026-01-10T11:11:11+00:00', previewKind: 'treasury-reviewed-v1', reportScope};
    const preview = {...meta, total: 1, sha256: 'b'.repeat(64), path: `data/reviewed-xlsx/${id}-v1-${'b'.repeat(64)}.json`};
    return [{id, local_preview: preview}, {schemaVersion: 1, resourceId: id, ...meta,
        sheets: [{name: 'Test', fields, rows: [row], total: 1}]}];
}
const f = (id, value) => ({id, type: 'text', dictionary: [value]});
test('municipal codes survive browser, cached amount excluded from rows and exports', () => {
    const fields = [f('Gads', '2025'), f('Pasvaldibas_ID', '0001000'), f('Pašvaldība', 'Rīga'),
        f('FKK', '01.000'), f('EKK', '1.0.'), {id:'EUR', type:'number'}];
    const [resource, value] = fixture(footerId, {year:'2025'}, fields, [0,0,0,0,0,244241114]);
    value.sourceSubtotal = {sheet:'2025_Izdevumi', cell:'F31030', formula:'SUBTOTAL(9,F2:F31029)', value:28885561868, currency:'EUR'};
    assert.equal(localPreviewPath(resource), resource.local_preview.path);
    const result = validateWorkbook(value, resource).sheets[0];
    assert.match(rowsCsv(result, result.rows), /"0001000"/);
    assert.doesNotMatch(rowsCsv(result, result.rows), /28885561868/);
    value.sourceSubtotal.cell = 'F31031';
    assert.throws(() => validateWorkbook(value, resource), /neatbilst/);
});
test('cumulative February preserves four exact measures and enforces scope', () => {
    const scope = {year:'2023',from:'2023.01.01.',through:'2023.02.28.'};
    const fields = [f('Gads',scope.year),f('Dati_par_periodu_No',scope.from),f('Dati_par_periodu_Lidz',scope.through),
        ...Array.from({length:18}, (_,i)=>f(`text_${i}`,'x')),f('Datu_valuta','Euro'),
        ...['Finansesanas_plans_gadam_ar_izmainam','Ienemumi','Izdevumi','Finansesana'].map(id=>({id,type:'decimal',dictionary:['4754.1400000000003']}))];
    const [resource,value] = fixture(feb, scope, fields, Array(26).fill(0));
    assert.match(rowsCsv(validateWorkbook(value, resource).sheets[0], value.sheets[0].rows), /4754\.1400000000003/);
    fields[2].dictionary[0] = '2023.03.31.';
    assert.throws(() => validateWorkbook(value, resource), /neatbilst/);
    resource.local_preview.path = resource.local_preview.path.replace('reviewed-xlsx', '..');
    assert.equal(localPreviewPath(resource), null);
});

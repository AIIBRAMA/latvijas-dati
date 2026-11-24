import test from 'node:test';
import assert from 'node:assert/strict';
import {localPreviewPath, localPreviewPartitions, filterRows, rowsCsv, toRecords, validateWorkbook} from '../src/localPreview.js';
const id = 'da897dfc-5b65-40c6-a8c8-d4ca530fa411';
const sourceSha256 = 'a057384f4b1b02dcf2604d901de0c65e8bbe8fbcb9a7e7f6b8a10308eebe3f6a';
const path = `data/csv/${id}-v1-${sourceSha256}.json`;
const source = {
    sourceFormat: 'CSV', sourceSha256, sourceUrl: 'https://data.gov.lv/dati/demo.csv',
    publisher: 'Iepirkumu uzraudzības birojs', licenseId: 'CC0-1.0', convertedAt: '2026-11-24T10:00:00+00:00'
};
const resource = {id, local_preview: {...source, path, total: 2}};
const sheet = {name: 'Dati', fields: [
    {id: 'Gads', type: 'text', dictionary: ['2019', '2020']},
    {id: 'Kods', type: 'text', dictionary: ['0003', '0']},
    {id: 'Piezīme', type: 'text', dictionary: ['=1+1']}
], rows: [[0, 0, 0], [1, 1, null]], total: 2};
const payload = {schemaVersion: 1, resourceId: id, ...source, sheets: [sheet]};

test('CSV local preview paths require full matching hash, resource ID, and scalar path', () => {
    assert.equal(localPreviewPath(resource), path);
    for (const substitute of [path.replace(sourceSha256, sourceSha256.slice(0, 16)), path.replace('data/csv', 'data/json'),
        path.replace('da897dfc', 'deadbeef'), '../' + path, '/'+path]) {
        assert.equal(localPreviewPath({id, local_preview: {...resource.local_preview, path: substitute}}), null);
    }
    assert.equal(localPreviewPath(resource, {path, label: '2024'}), null);
    assert.deepEqual(localPreviewPartitions({id, local_preview: {...resource.local_preview, partitions: [{path}]} }), []);
});

test('CSV validated and exported without Summa or accidental formula execution', () => {
    assert.equal(validateWorkbook(payload, resource), payload);
    assert.equal(toRecords(sheet, sheet.rows)[0].Kods, '0003');
    assert.equal(toRecords(sheet, sheet.rows)[1].Piezīme, null);
    assert.deepEqual(filterRows(sheet, {Gads: '2020'}), [sheet.rows[1]]);
    assert.match(rowsCsv(sheet, sheet.rows), /"2019","0003","'=1\+1"/);
});

test('CSV rejects mismatched provenance, dimensions, and dictionary indexes', () => {
    for (const bad of [
        {...payload, licenseId: 'other'}, {...payload, convertedAt: 'changed'}, {...payload, sourceUrl: 'https://x.example'},
        {...payload, sourceFormat: undefined}, {...payload, sheets: [sheet, sheet]},
        {...payload, sheets: [{...sheet, rows: [[0,0,0], [1,1,1]]}]},
        {...payload, sheets: [{...sheet, rows: [[0,0], [1,1,null]]}]},
        {...payload, sheets: [{...sheet, fields: [sheet.fields[0], {...sheet.fields[1], id: 'Ｇａｄｓ'}, sheet.fields[2]]}]},
    ]) assert.throws(() => validateWorkbook(bad, resource), /neatbilst/);
    assert.throws(() => validateWorkbook(payload, {id, local_preview: {...resource.local_preview, total: 1}}), /neatbilst/);
});

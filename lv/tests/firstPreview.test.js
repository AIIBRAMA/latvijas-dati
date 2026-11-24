import assert from 'node:assert/strict';
import test from 'node:test';
import {localPreviewPath,validateWorkbook,rowsCsv} from '../src/localPreview.js';

const id='95276527-f486-4b21-ac93-395241b84aad';
const sourceSha256='f'.repeat(64);
const meta={sourceFormat:'XLSX',sourceSha256,sourceUrl:'https://data.gov.lv/dati/dataset/official.xlsx',
    convertedAt:'2026-11-24T12:00:00Z',publisher:'Iestāde',licenseId:'CC0-1.0',previewKind:'public-reviewed-xlsx-v1'};

test('reviewed public XLSX is bound to the resource and exports exact numeric data, not notes',()=>{
    const path=`data/public-xlsx/${id}-v1-${sourceSha256}.json`;
    const resource={id,local_preview:{path,total:1,...meta}};
    const table={name:'Sheet1',sourceFooter:'Avota piezīme',fields:[
        {id:'Kods',type:'text',dictionary:['00060']},
        {id:'Vērtība',type:'decimal',dictionary:['-4754.1400000000003']}
    ],rows:[[0,0]],total:1};
    const data={schemaVersion:1,resourceId:id,...meta,sheets:[table]};
    assert.equal(localPreviewPath(resource),path);
    assert.match(rowsCsv(validateWorkbook(data,resource).sheets[0],table.rows),/"00060","-4754\.1400000000003"/);
    assert.doesNotMatch(rowsCsv(table,table.rows),/Avota piezīme/);
    table.fields[1].dictionary[0]='=HYPERLINK("other")';
    assert.throws(()=>validateWorkbook(data,resource), /neatbilst/);
    resource.local_preview.path=path.replace('public-xlsx','csv');
    assert.equal(localPreviewPath(resource),null);
});

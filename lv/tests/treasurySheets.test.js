import test from 'node:test';
import assert from 'node:assert/strict';
import {localTreasurySheets, selectedTreasurySheetPath, validateWorkbook, rowsCsv, previewCsvCell} from '../src/localPreview.js';
const id='d55ce40b-72d3-4d86-ab95-6cc978bf07f8';
const meta={previewKind:'treasury-sheets-v1',sourceFormat:'XLSX',sourceUrl:'https://data.gov.lv/original.xlsx',
    sourceSha256:'a'.repeat(64),reportScope:{year:'2026'},convertedAt:'2026-01-10T11:11:11+00:00'};
const pointer=(id2,name,digest)=>({id:id2,name,total:1,sha256:digest,
    path:`data/treasury-sheets/${id}-${id2}-v1-${digest}.json`});
const resource=()=>({id,local_preview:{...meta,total:2,reportSheets:[pointer('dati','DATI','b'.repeat(64)),pointer('ekk','EKK','c'.repeat(64))]}});
const field=(id,value,type='text')=>({id,type,dictionary:[value]});
test('Treasury sheet selector keeps EKK dictionary separate and rejects crossed or forged paths',()=>{
    const r=resource(), [dati,ekk]=localTreasurySheets(r);
    const table={name:'EKK',total:1,fields:[field('EKK','01.00'),field('Vienotais EKK - Key','0010'),field('EKK nosaukums','Kods')],rows:[[0,0,0]]};
    const payload={schemaVersion:1,resourceId:id,reportSheet:'ekk',...meta,sheets:[table]};
    assert.equal(selectedTreasurySheetPath(r,ekk),ekk.path);
    assert.match(rowsCsv(validateWorkbook(payload,r,undefined,ekk).sheets[0],table.rows),/"0010"/);
    assert.throws(()=>validateWorkbook(payload,r,undefined,dati),/neatbilst/);
    ekk.path='../other.json';
    assert.deepEqual(localTreasurySheets(r),[]);
    assert.equal(selectedTreasurySheetPath(r,dati),null);
});
test('exact decimal export preserves negative amount but blocks formula-looking text',()=>{
    const exact='-4754.1400000000003';
    assert.equal(previewCsvCell({type:'decimal'},exact),`"${exact}"`);
    assert.equal(previewCsvCell({type:'decimal'},'-1+1'),`"'-1+1"`);
    assert.equal(previewCsvCell({type:'text'},exact),`"'${exact}"`);
    assert.equal(previewCsvCell({type:'text'},'=A1+1'),`"'=A1+1"`);
});

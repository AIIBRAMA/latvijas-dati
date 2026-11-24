import test from 'node:test';
import assert from 'node:assert/strict';
import {isAnnualPreview, localPreviewPath, validateWorkbook, chartLabelField, filterRows, rowsCsv} from '../src/localPreview.js';

const id = 'bd0aa72f-700b-499c-a0f2-38f50248e50d';
const sourceSha256 = '0123456789abcdef'.repeat(4);
const sha256 = 'fedcba9876543210'.repeat(4);
const sourceUrl = 'https://data.gov.lv/dati/dataset/c4db2159-7852-4551-bd59-46d92cd74b12/resource/bd0aa72f-700b-499c-a0f2-38f50248e50d/download/2025_2_pb_pasv_ad.xlsx';
const checked = '2026-11-24T01:00:00+00:00';
const path = `data/annual-xlsx/${id}-v1-${sourceSha256.slice(0,16)}-${sha256.slice(0,16)}.json`;
const metadata = {sourceFormat:'XLSX', previewKind:'treasury-annual-v1', reportYear:2025, total:2, path, sourceUrl, sourceSha256, sha256, convertedAt:checked};
const sheet = {name:'Report 1', fields:[{id:'Gads'}, {id:'Novads',sourceId:'Ministrija',dictionary:['Ādažu novads','Rīga']}, {id:'EKK',dictionary:['001']}, {id:'Summa',sourceId:'Summa_EUR'}], total:2, rows:[[2025,0,0,-2],[2025,1,0,null]]};
const payload = {schemaVersion:1,resourceId:id,sourceFormat:'XLSX',previewKind:'treasury-annual-v1',reportYear:2025,convertedAt:checked,sourceUrl,sourceSha256,sheets:[sheet]};

test('Annual preview paths are same-origin and pin both source and normalized content',()=>{
  assert.equal(isAnnualPreview(metadata),true);
  assert.equal(localPreviewPath({id,local_preview:metadata}),path);
  assert.equal(localPreviewPath({id,local_preview:{...metadata,sha256:sourceSha256}}),null);
  assert.equal(localPreviewPath({id,local_preview:{...metadata,path:'https://elsewhere.example/'+path}}),null);
  assert.equal(localPreviewPath({id,local_preview:{...metadata,path:path.replace('annual-xlsx','xlsx')}}),null);
  assert.equal(localPreviewPath({id,local_preview:{...metadata,sourceFormat:'JSON'}}),null);
});
test('Annual data keeps its precise year, amounts and municipality label; allows standard search/filter/CSV',()=>{
  const resource = {id,local_preview:metadata};
  assert.equal(validateWorkbook(payload,resource),payload);
  assert.throws(()=>validateWorkbook({...payload,convertedAt:'other'},resource),/neatbilst/);
  assert.throws(()=>validateWorkbook({...payload,reportYear:2024},resource),/neatbilst/);
  assert.throws(()=>validateWorkbook({...payload,sheets:[{...sheet,rows:[[2024,0,0,-2],sheet.rows[1]]}]},resource),/neatbilst/);
  assert.equal(chartLabelField(sheet.fields),'Novads');
  assert.match(rowsCsv(sheet,filterRows(sheet,{Novads:'Ādažu novads'})),/"001","-2"/);
});

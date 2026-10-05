import test from 'node:test';
import assert from 'node:assert/strict';
import {filterDatasets, mergePreviewResources, csvCell} from '../src/data.js';
import {cell, filterRows, filterOptions, toRecords, rowsCsv, validateWorkbook} from '../src/localPreview.js';
const sheet={name:'Pārskats',total:4,fields:[
 {id:'Gads',type:'number'}, {id:'Menesis_nr',type:'text',dictionary:['1','#']},
 {id:'Iestade',type:'text',dictionary:['Rīgas iestāde','Cita iestāde']},
 {id:'Klasifikacija',type:'text',dictionary:['Izpilde','Plāns']},
 {id:'Kods',type:'text',dictionary:['001','90000089305']}, {id:'Summa',type:'number'}
],rows:[[2025,0,0,0,0,15],[2025,1,0,1,1,100],[2026,0,0,0,0,-2],[2025,0,1,0,null,0]]};
test('XLSX filters combine year, month, institution and plan type; # is retained',()=>{
 assert.equal(filterRows(sheet,{Gads:'2025',Menesis_nr:'1',Iestade:'Rīgas iestāde',Klasifikacija:'Izpilde'}).length,1);
 assert.equal(filterRows(sheet,{Menesis_nr:'#'})[0][5],100);
 assert.deepEqual(filterOptions(sheet,'Menesis_nr'),['#','1']);
 assert.equal(filterRows(sheet,{Gads:'2026'},'rigas')[0][5],-2);
 assert.equal(filterRows(sheet,{},'neeksistē').length,0);
});
test('Decoding retains identifiers, zero, negatives and missing cells',()=>{
 const rows=toRecords(sheet,sheet.rows);
 assert.equal(rows[0].Kods,'001');assert.equal(rows[1].Kods,'90000089305');
 assert.equal(rows[2].Summa,-2);assert.equal(rows[3].Summa,0);assert.equal(rows[3].Kods,null);
 assert.equal(cell(sheet,sheet.rows[1],1),'#');
});
test('Full-selection CSV exports all selected rows, and numeric negatives remain numeric',()=>{
 const csv=rowsCsv(sheet,filterRows(sheet,{Iestade:'Rīgas iestāde'}));
 assert.equal(csv.split('\r\n').length,4);assert.ok(csv.includes('"001"'));assert.ok(csv.includes('"-2"'));
 assert.equal(csvCell(-2),'"-2"');assert.equal(csvCell('=1+1'),'"\'=1+1"');
});
test('Live metadata keeps local preview only for the exact source URL and resource',()=>{
 const snapshot=[{id:'one',url:'https://data.gov.lv/one.xlsx',local_preview:{path:'data/xlsx/one.json'}}];
 assert.ok(mergePreviewResources([{id:'one',url:snapshot[0].url}],snapshot)[0].local_preview);
 assert.equal(mergePreviewResources([{id:'one',url:'https://data.gov.lv/new.xlsx'}],snapshot)[0].local_preview,undefined);
 assert.equal(mergePreviewResources([{id:'two',url:snapshot[0].url}],snapshot)[0].local_preview,undefined);
});
test('Catalog preview filter includes XLSX copies without DataStore',()=>{
 const datasets=[{id:'one',title:'Budžets',resources:[{local_preview:{path:'file'}}]},{id:'two',title:'Other',resources:[{}]}];
 assert.deepEqual(filterDatasets(datasets,{preview:true}).map(d=>d.id),['one']);
});
test('A mismatched cached workbook cannot masquerade as the selected resource',()=>{
 const resource={id:'one',local_preview:{sourceUrl:'https://data.gov.lv/one.xlsx',sourceSha256:'sha'}};
 const payload={schemaVersion:1,resourceId:'one',sourceUrl:resource.local_preview.sourceUrl,sourceSha256:'sha',sheets:[sheet]};
 assert.equal(validateWorkbook(payload,resource),payload);
 assert.throws(()=>validateWorkbook({...payload,resourceId:'two'},resource));
 assert.throws(()=>validateWorkbook({...payload,sourceSha256:'old'},resource));
});

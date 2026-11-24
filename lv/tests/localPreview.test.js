import test from 'node:test';
import assert from 'node:assert/strict';
import {filterDatasets, mergePreviewResources, csvCell} from '../src/data.js';
import {PRIMARY_FILTERS, cell, chartCurrencyField, chartLabelField, filterRows, filterOptions, localPreviewPartitions, localPreviewPath, toRecords, rowsCsv, validateWorkbook} from '../src/localPreview.js';
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
const id = 'e4543728-914f-4b8b-bdd8-0123456789ab';
const sourceSha256 = '0123456789abcdef'.repeat(4);
const memo = (sourceFormat, extra = {}) => ({
 id, local_preview:{...(sourceFormat ? {sourceFormat} : {}), sourceSha256, sourceUrl:'https://data.gov.lv/budget', ...extra}
});
const part = (label) => ({label, total:1, path:`data/json/${id}-v1-${sourceSha256.slice(0,16)}-${label}.json`});
test('Local cache accepts legacy XLSX and direct JSON paths but binds format, resource and source hash',()=>{
 const path = `data/xlsx/${id}-v1-${sourceSha256.slice(0,16)}.json`;
 assert.equal(localPreviewPath(memo(undefined,{path})),path);
 assert.equal(localPreviewPath(memo('XLSX',{path})),path);
 assert.equal(localPreviewPath(memo('JSON',{path})),null);
 assert.equal(localPreviewPath(memo('TXT',{path})),null);
 assert.equal(localPreviewPath(memo('JSON',{path:path.replace('xlsx','json')})),path.replace('xlsx','json'));
 assert.equal(localPreviewPath(memo('XLSX',{path:path.replace('data/','data/../')})),null);
 assert.equal(localPreviewPath(memo('XLSX',{path:path.replace(id, 'e4543728-914f-4b8b-bdd8-0123456789ac')})),null);
 assert.equal(localPreviewPath(memo('XLSX',{path:path.replace('0123456789abcdef','fedcba9876543210')})),null);
});
test('JSON partitions select newest year and reject duplicate, inconsistent and wrong-path entries',()=>{
 const years=[part('2025'),part('2026')];
 const r=memo('JSON',{partitions:years,total:2});
 assert.deepEqual(localPreviewPartitions(r).map((p)=>p.label),['2026','2025']);
 assert.equal(localPreviewPath(r,years[0]),years[0].path);
 assert.equal(localPreviewPath(r,{...years[0],label:'2026'}),null);
 assert.deepEqual(localPreviewPartitions(memo('JSON',{partitions:years,total:3})),[]);
 assert.deepEqual(localPreviewPartitions(memo('JSON',{partitions:[years[0],years[0]],total:2})),[]);
 assert.deepEqual(localPreviewPartitions(memo('XLSX',{partitions:years,total:2})),[]);
 assert.equal(localPreviewPartitions(memo('XLSX')),undefined);
});
test('A live package_show resource keeps partitions only while its ID and source URL match',()=>{
 const cached=memo('JSON',{partitions:[part('2025'),part('2026')],total:2});
 const snapshot=[{...cached,url:cached.local_preview.sourceUrl}];
 const live=[{id,url:snapshot[0].url,format:'JSON',description:'Jaunā informācija'}];
 const [matched]=mergePreviewResources(live,snapshot);
 assert.equal(matched.description,'Jaunā informācija');
 assert.equal(matched.local_preview,cached.local_preview);
 assert.deepEqual(localPreviewPartitions(matched).map(({label})=>label),['2026','2025']);
 assert.equal(mergePreviewResources([{...live[0],url:'https://data.gov.lv/budget-new'}],snapshot)[0].local_preview,undefined);
});
test('A partition can contain only records of its selected year, and estimated amounts are not currency-labelled',()=>{
 const r=memo('JSON',{partitions:[part('2026')],total:1});
 const estimates={name:'Tāmes',total:1,fields:[{id:'Gads'},{id:'ministrija',dictionary:['Kultūras ministrija']},{id:'iestade',dictionary:['Iestāde']},{id:'tips',dictionary:['IZDEVUMI']},{id:'Summa'}],rows:[[2026,0,0,0,-4]]};
 const payload={schemaVersion:1,resourceId:id,sourceUrl:r.local_preview.sourceUrl,sourceSha256,sourceFormat:'JSON',sheets:[estimates]};
 assert.equal(validateWorkbook(payload,r,part('2026')),payload);
 assert.throws(()=>validateWorkbook(payload,r,part('2025')),/citam gadam/);
 assert.throws(()=>validateWorkbook(payload,r,{...part('2026'),total:2}),/ierakstu skaits/);
 assert.throws(()=>validateWorkbook({...payload,sourceFormat:'XLSX'},r,part('2026')),/neatbilst/);
 assert.deepEqual(PRIMARY_FILTERS.JSON,['Gads','ministrija','iestade','tips']);
 assert.equal(filterRows(estimates,{Gads:'2026',ministrija:'Kultūras ministrija',tips:'IZDEVUMI'}).length,1);
 assert.equal(chartLabelField(estimates.fields),'iestade');
 assert.equal(chartCurrencyField(estimates.fields),undefined);
 assert.match(rowsCsv(estimates,estimates.rows),/"-4"/);
 const municipality=[{id:'Summa'},{id:'Valuta'},{id:'Novadi_pilsetas'}];
 assert.equal(chartLabelField(municipality),'Novadi_pilsetas');
 assert.equal(chartCurrencyField(municipality),'Valuta');
});

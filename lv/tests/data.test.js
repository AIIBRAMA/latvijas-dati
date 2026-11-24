import test from 'node:test';
import assert from 'node:assert/strict';
import {filterDatasets, facets, catalogCsv, hasPreview, mergePreviewResources, safeUrl, numeric} from '../src/data.js';
const sample = [
 {id:'a',name:'a',title:'Iedzīvotāji Rīgā',notes:'Statistika',metadata_modified:'2026-01-02',organization:{name:'riga',title:'Rīgas dome'},groups:[{name:'people',title:'Sabiedrība'},{name:'places',title:'Pašvaldības'}],tags:[],resources:[{format:'.csv',datastore_active:true},{format:'CSV'}]},
 {id:'b',name:'b',title:'Meži',notes:'Vide',metadata_modified:'2026-02-01',organization:{name:'vmd',title:'Valsts meža dienests'},groups:[],tags:[],resources:[{format:'XLSX'}]}
];
test('Latvian diacritics, words and filters combine',()=>{
 assert.deepEqual(filterDatasets(sample,{q:'iedzivotaji riga',org:'riga',format:'CSV',group:'people',preview:true}).map(d=>d.id),['a']);
 assert.equal(filterDatasets(sample,{q:'iedzivotaji',org:'vmd'}).length,0);
});
test('Saved datasets and sort are applied without mutating the source',()=>{
 assert.deepEqual(filterDatasets(sample,{saved:true},['a']).map(d=>d.id),['a']);
 assert.deepEqual(filterDatasets(sample).map(d=>d.id),['b','a']);assert.equal(sample[0].id,'a');
});
test('Facets count each dataset once per format and retain unclassified datasets',()=>{
 assert.equal(facets(sample,'formats').find(f=>f.id==='CSV').amount,1);
 assert.equal(facets(sample,'groups').find(f=>f.id==='_none').amount,1);
 assert.equal(filterDatasets(sample,{group:'_none'})[0].id,'b');
});
test('Untrusted links cannot execute JavaScript or access local files',()=>{
 for(const url of ['javascript:alert(1)','data:text/html,test','file:///etc/passwd','//evil.example']) assert.equal(safeUrl(url),null);
 assert.equal(safeUrl('https://data.gov.lv/dati'),'https://data.gov.lv/dati');
});
test('CSV preserves quotes/newlines and neutralizes spreadsheet formulas',()=>{
 const csv=catalogCsv([{...sample[0],title:'=HYPERLINK("bad")\nRīga'}]);
 assert.ok(csv.includes('"\'=HYPERLINK(""bad"")\nRīga"'));assert.ok(csv.startsWith('\uFEFF'));
});
test('Charts do not treat missing or malformed values as zero',()=>{
 for(const v of [null,'',' ','unknown','12px',Infinity,'1.2.3']) assert.equal(numeric(v),null);
 assert.equal(numeric('-12,5'),-12.5);assert.equal(numeric(0),0);
 assert.equal(numeric('1 616 775'),1616775);assert.equal(numeric('40\u00a0855'),40855);assert.equal(numeric('1 2 3'),null);
});
test('CKAN preview accepts only actual active flags, not truthy strings',()=>{
 for(const v of [true,'true']) assert.equal(hasPreview({datastore_active:v}),true);
 for(const v of [false,'false','False','0',0,1,'',null,undefined]) assert.equal(hasPreview({datastore_active:v}),false);
});
test('Seven audited broken DataStore entries expose no preview but still keep source links',()=>{
 const broken=[
  ['19c8e915-cc00-457d-98c5-d05b2e8fbaf8',true],
  ['ee6bde54-fe44-4237-9755-54b970c316f8',true],
  ['cd9b78fa-3acb-4c2c-a710-56927e70c4f7',true],
  ['371c14d7-1c34-4abd-94ee-14a01f6362d9',true],
  ['0f2a8453-724c-45a6-9c96-e25c5259ed5d','true'],
  ['e39a56e9-8377-4b85-ae18-c3ffcae19ac0','false'],
  ['63df3b12-4de6-4fee-ac4f-c6a421a589d5','false']
 ].map(([id,datastore_active])=>({id,datastore_active,url:'https://data.gov.lv/dati/dataset/example/resource/'+id}));
 const current=mergePreviewResources(broken,broken);
 assert.equal(current.length,7);
 for(const r of current) {
  assert.equal(hasPreview(r),false);
  assert.equal(safeUrl(r.url),r.url);
 }
 const catalog=[{id:'broken',resources:current}];
 assert.equal(filterDatasets(catalog,{preview:true}).length,0);
 assert.equal(filterDatasets(catalog).length,1);
 assert.equal(hasPreview({...current[0],local_preview:{path:'data/reviewed.json'}}),true);
});

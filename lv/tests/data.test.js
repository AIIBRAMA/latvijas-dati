import test from 'node:test';
import assert from 'node:assert/strict';
import {filterDatasets, facets, catalogCsv, safeUrl, numeric} from '../src/data.js';
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

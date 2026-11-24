import test from 'node:test';
import assert from 'node:assert/strict';
import {localTreasurySheets, selectedTreasurySheetPath, validateWorkbook, rowsCsv} from '../src/localPreview.js';
import {COMPENSATION, EXECUTION, RAIM, reportPartLabel, MONTHS_LV} from '../src/treasuryMonthly.js';

const rid = 'c415d924-df22-4f5e-b39c-7e289a67b1a1';
const sha = 'a'.repeat(64);
const monthIds = Array.from({length:10}, (_,i)=>String(i+1));
const lexicalMonths = [...monthIds].sort();

function resourceFor(profile) {
    const resource = {id: rid};
    const reportScope = profile === RAIM ? {from:'2009', through:'2025'} : {year:'2026'};
    const ptr = (id, name, month) => ({id, name, sha256:sha, total:1,
        path:`data/treasury-sheets/${rid}-${id}-v1-${sha}.json`, ...(month ? {month}: {})});
    const reportSheets = profile === RAIM ? [ptr('saistibas','Sheet1')] :
        [...(profile === COMPENSATION ? [ptr('plans','AD','#')]: []),
         ...lexicalMonths.map(m=>ptr('m'+m.padStart(2,'0'),'AD',m)), ptr('ekk','EKK')];
    resource.local_preview = {previewKind:'treasury-sheets-v1', sourceFormat:'XLSX', reportProfile:profile, reportScope,
        convertedAt:'2026-11-24T11:55:00+00:00', sourceSha256:sha, sourceUrl:'test-original',
        total:reportSheets.length, reportSheets};
    return resource;
}

function envelope(resource, part, fields, values, decimals = []) {
    const meta = resource.local_preview;
    return {schemaVersion:1, resourceId:resource.id, previewKind:meta.previewKind, sourceFormat:meta.sourceFormat,
        reportProfile:meta.reportProfile, reportScope:meta.reportScope, reportSheet:part.id, sourceSha256:meta.sourceSha256,
        sourceUrl:meta.sourceUrl, convertedAt:meta.convertedAt, sheets:[{name:part.name,total:1,cachedFormulaCount:0,
            fields:fields.map((id,i)=>({id,type:decimals.includes(i)?'decimal':'text',dictionary:values[i]===null ? [] : [values[i]]})),
            rows:[values.map(v=>v===null?null:0)]}]};
}

test('month selector is chronological, with distinct plans and EKK; rejects missing/wrong month and paths', () => {
    const res = resourceFor(COMPENSATION);
    const list = localTreasurySheets(res);
    assert.deepEqual(list.map(p=>p.month), [...monthIds, '#', undefined]);
    assert.equal(reportPartLabel(list[9]), 'Oktobris (AD)');
    assert.equal(reportPartLabel(list[10]), 'Gada plāna versijas (AD)');
    assert.equal(reportPartLabel(list[11]), 'EKK kodu vārdnīca');
    assert.equal(selectedTreasurySheetPath(res,list[9]), list[9].path);
    assert.equal(selectedTreasurySheetPath(res,{...list[9]}), null);
    const attacked = structuredClone(res);
    attacked.local_preview.reportSheets[0].path = 'https://wrong.test/a.json';
    assert.deepEqual(localTreasurySheets(attacked),[]);
    const wrong = structuredClone(res);
    wrong.local_preview.reportSheets[1].month = '10';
    assert.deepEqual(localTreasurySheets(wrong),[]);
    const dup = structuredClone(res);
    dup.local_preview.reportSheets[1] = dup.local_preview.reportSheets[2];
    assert.deepEqual(localTreasurySheets(dup),[]);
});

test('RAIM validates holdings without inferring a currency and retains original numeric lexemes',() => {
    const res = resourceFor(RAIM), p = localTreasurySheets(res)[0];
    const headers=['Pasvaldiba_nosaukums','Pasvaldiba_ATVK_kods',
        'Planotie_pb_ien_bez_transf_ipasiem_merkiem_un_iemaks_PFIF_summa','Aiznemumi_summa','Galvojumi_summa',
        'Citas_ilgtermina_saistibas_summa','Saistibas_kopa_summa','Saistibu_apmers_procenti','Dati_datums'];
    const doc = envelope(res,p,headers,['Daugavpils','0050000','51644374','2587716','825679','572956','3986351',
        '7.7188489999999996','31.12.2009.'],[2,3,4,5,6,7]);
    assert.equal(validateWorkbook(doc,res,undefined,p),doc);
    assert.match(rowsCsv(doc.sheets[0],doc.sheets[0].rows), /"0050000".*"7\.7188489999999996","31\.12\.2009\."/s);
    const wrong = structuredClone(doc);
    wrong.sheets[0].fields[8].dictionary[0] = '31.12.2030.';
    assert.throws(()=>validateWorkbook(wrong,res,undefined,p));
});

test('execution and compensation keep EKK dictionaries separate, only compensation preserves blank A', () => {
    for (const profile of [EXECUTION, COMPENSATION]) {
        const res=resourceFor(profile), p=localTreasurySheets(res).at(-1);
        const doc=envelope(res,p,['EKK','Vienotais EKK - Key','EKK nosaukums'],
            [profile === COMPENSATION ? null : '1.0.grupa','A100','Nodokļu ieņēmumi']);
        assert.equal(validateWorkbook(doc,res,undefined,p),doc);
        doc.sheets[0].fields[1].dictionary=[];
        assert.throws(()=>validateWorkbook(doc,res,undefined,p));
    }
});

test('compensation plan version and real Gregorian date, exact currency and original partition', () => {
    const res=resourceFor(COMPENSATION), p=localTreasurySheets(res).find(x=>x.id==='plans');
    const headers = Array.from({length:39},(_,i)=>'avota-aile-'+i);
    headers.splice(0,5,'Gads','Budzeta_fin_plans_prognoze_gadam_versija_Atslega',
        'Budzeta_fin_plans_prognoze_gadam_uz_datumu','Menesis_Atslega','Menesis_nosaukums');
    headers[26]='Klasifikacija';headers[37]='Datu_valuta';headers[38]='Summa';
    const vals=Array(39).fill(null);
    vals.splice(0,5,'2026','F260228','28.02.2026','#','#');
    vals[26]='Finansēšanas plāns gadam ar izmaiņām'; vals[37]='Euro';vals[38]='-1.0682351245';
    const doc=envelope(res,p,headers,vals,[38]);
    assert.equal(validateWorkbook(doc,res,undefined,p),doc);
    for(const [idx,v] of [[2,'29.02.2026'],[1,'F260131'],[37,'USD'],[3,'2']]){
        const mutated=structuredClone(doc);mutated.sheets[0].fields[idx].dictionary[0]=v;
        assert.throws(()=>validateWorkbook(mutated,res,undefined,p));
    }
    const actual=localTreasurySheets(res)[1];
    assert.throws(()=>validateWorkbook({...doc,reportSheet:actual.id},res,undefined,actual));
    assert.equal(MONTHS_LV[1], 'Februāris');
});

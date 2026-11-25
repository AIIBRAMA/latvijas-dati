import test from 'node:test';
import assert from 'node:assert/strict';
import {formatAmount, formatDisplayNumber, isAmountField} from '../src/amountDisplay.js';
import {csvCell} from '../src/data.js';
import {previewCsvCell} from '../src/localPreview.js';

const field = (id) => ({id});
const gap = '\u00a0';

test('formats the three screenshot amounts and displays cents consistently', () => {
    assert.equal(formatAmount(36491.440000000002), `36${gap}491,44`);
    assert.equal(formatAmount('39445.89'), `39${gap}445,89`);
    assert.equal(formatAmount('921.27'), '921,27');
    assert.equal(formatAmount(1000), `1${gap}000,00`);
    assert.equal(formatAmount(0), '0,00');
    assert.equal(formatAmount('-0.001'), '0,00');
    assert.equal(formatAmount('−1\u202f999,995'), `−2${gap}000,00`);
});
test('rounds decimal strings directly, including high precision or exponent notation', () => {
    assert.equal(formatAmount('9007199254740993.235'), `9${gap}007${gap}199${gap}254${gap}740${gap}993,24`);
    assert.equal(formatAmount('5e-3'), '0,01');
    assert.equal(formatAmount('4.999e-3'), '0,00');
    assert.equal(formatAmount(2.5e+5), `250${gap}000,00`);
    assert.equal(formatAmount('1.005'), '1,01');
});
test('does not turn non-numbers and unsupported notation into amounts', () => {
    for (const value of ['', null, undefined, '—', '#', true, {}, 'n/a', '1,234.56', '1 23', Infinity, NaN, '1e10000']) assert.equal(formatAmount(value), null);
});
test('recognizes public money columns but leaves codes, dates, rates and counts unchanged', () => {
    for (const name of ['Summa', 'Summa_EUR', 'EUR', 'Aiznemumi_summa', 'Līgumsumma', 'Līgumcena (EUR bez PVN)']) assert.equal(isAmountField(field(name)), true, name);
    for (const name of ['Gads', 'Datu_valuta', 'Vienotais_EKK_Atslega_7_limenis', 'Saistibu_apmers_procenti', 'summa (%)', 'Likme EUR', 'atslegas_kods_EUR', 'Iepirkumu skaits EUR', 'Value']) assert.equal(isAmountField(field(name)), false, name);
    assert.equal(isAmountField({id:'abstract', sourceId:'Summa_EUR'}), true);
    assert.equal(isAmountField(field('Value'), 'pasvaldibu-parads-euro'), true);
    assert.equal(isAmountField(field('Parskata_perioda_beigas_neto'), 'valsts-un-pasvaldibu-sektora-ceturksna-finansu-dati'), true);
    assert.equal(isAmountField(field('Kop_izd'), 'pasvaldibu-pamatbudzeta-izdevumi'), true);
    assert.equal(isAmountField(field('IIN_ien'), 'pasvaldibu-pamatbudzeta-ienemumi'), true);
    assert.equal(isAmountField(field('Izdevumi'), 'other-dataset'), false);
    assert.equal(isAmountField(field('Izdevumi'), 'other-dataset', true), true);
});
test('both CSV paths retain the original numeric precision', () => {
    const value = '36491.440000000002';
    assert.equal(csvCell(value), '"' + value + '"');
    assert.equal(previewCsvCell({id:'Summa', type:'number', exactExcelNumber:true}, value), '"' + value + '"');
});
test('applies Latvian notation to numerical data without losing precision', () => {
    assert.equal(formatDisplayNumber({id:'Rezultāts', type:'numeric'}, '12345.678900'), `12${gap}345,678900`);
    assert.equal(formatDisplayNumber({id:'Diennakts_temperatūra', type:'float'}, 1.234e-7), '0,0000001234');
    assert.equal(formatDisplayNumber(field('Saistibu_apmers_procenti'), '12.1234'), '12,1234');
    assert.equal(formatDisplayNumber(field('Ierakstu skaits'), '10000'), `10${gap}000`);
    assert.equal(formatDisplayNumber(field('Daudzums'), '9007199254740993'), `9${gap}007${gap}199${gap}254${gap}740${gap}993`);
    assert.equal(formatDisplayNumber(field('Daudzums'), '-0,00700'), '−0,00700');
    assert.equal(formatDisplayNumber({id:'Value',type:'text'}, '31233'), null);
    assert.equal(formatDisplayNumber({id:'Value',type:'integer'}, '0031233'), null);
});
test('leaves identifier, year and date fields untouched even when typed as integers', () => {
    for (const id of ['Gads','Iestades_NMR','Vienotais_EKK_Atslega_7_limenis','Pasvaldiba_ATVK_kods','Datums','Pasta_indekss','Tālrunis','Personas kods','Reģistrācijas numurs','Mēnesis']) {
        assert.equal(formatDisplayNumber({id,type:'int'}, 20261125), null, id);
    }
    assert.equal(formatDisplayNumber(field('Summa'), '2026', true), `2${gap}026,00`);
});
test('historical Treasury execution: separate the institution code from the four money columns', () => {
    const dataset = 'valsts-budzeta-izpilde-pa-iestadem-budzeta-programmam-apaksprogrammam-un-klasifikacijas-kodiem';
    const historical = ['Finansēšanas plāns gadam\n(ar izmaiņām)', 'Ieņēmumi', 'Izdevumi', 'Izpilde pa finansēšanas kodiem'];
    for (const id of historical) {
        const f = {id,type:'numeric'};
        assert.equal(formatDisplayNumber(f, '1234.567890', isAmountField(f,dataset)), `1${gap}234,57`, id);
    }
    assert.equal(formatDisplayNumber({id:'Iestāde',type:'numeric'}, 1234),null);
    assert.equal(formatDisplayNumber({id:'Cenu indekss',type:'numeric'}, '1234.5'), `1${gap}234,5`);
});

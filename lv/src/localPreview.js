import {csvCell, normalize} from './data.js';

export const FILTERS = [
    ['Gads', 'Gads'], ['Menesis_nr', 'Mēnesis (numurs)'], ['Ministrija', 'Ministrija'],
    ['Iestade', 'Iestāde'], ['Klasifikacija', 'Plāns / izpilde'], ['Plans_gadam_uz_datumu', 'Plāna datums (avota vērtība)'],
    ['Budzeta_tips', 'Budžeta tips'], ['Iestades_hier', 'Iestādes hierarhijas līmenis'],
    ['Pamatd_kons', 'Pamatdati / konsolidācija'], ['EKK_kods', 'EKK kods'],
    ['EKK_kods_1_limenis', 'EKK 1. līmenis'], ['EKK_kods_2_limenis', 'EKK 2. līmenis'], ['EKK_kods_7_limenis', 'EKK 7. līmenis'],
    ['Funkcija_augstakais_limenis_Nosaukums', 'Funkcija'], ['Datu_valuta', 'Valūta']
];
export function cell(sheet, row, index) {
    const value = row[index];
    return value === null || value === undefined ? null : sheet.fields[index].dictionary ? sheet.fields[index].dictionary[value] : value;
}
export function validateWorkbook(value, resource) {
    if (value?.schemaVersion !== 1 || value.resourceId !== resource.id || value.sourceUrl !== resource.local_preview.sourceUrl || value.sourceSha256 !== resource.local_preview.sourceSha256 || !Array.isArray(value.sheets) || !value.sheets.length) throw new Error('XLSX datu kopija neatbilst izvēlētajam resursam. Pārlādējiet vietni.');
    for (const sheet of value.sheets) {
        if (!Array.isArray(sheet.fields) || !Array.isArray(sheet.rows) || sheet.rows.length !== sheet.total || !sheet.fields.some((f) => f.id === 'Summa')) throw new Error('XLSX datu kopijas struktūra nav derīga.');
    }
    return value;
}
export function filterOptions(sheet, fieldId) {
    const index = sheet.fields.findIndex((field) => field.id === fieldId);
    if (index === -1) return [];
    return [...new Set(sheet.rows.map((row) => cell(sheet, row, index)).filter((value) => value !== null).map(String))].sort((a, b) => a.localeCompare(b, 'lv', {numeric: true}));
}
export function filterRows(sheet, filters = {}, query = '') {
    const active = Object.entries(filters).filter(([, value]) => value !== '').map(([field, value]) => [sheet.fields.findIndex((f) => f.id === field), value]);
    const words = normalize(query).split(/\s+/).filter(Boolean);
    return sheet.rows.filter((row) => {
        if (!active.every(([index, value]) => index >= 0 && String(cell(sheet, row, index) ?? '') === value)) return false;
        if (!words.length) return true;
        const text = normalize(sheet.fields.map((_, i) => cell(sheet, row, i) ?? '').join(' '));
        return words.every((word) => text.includes(word));
    });
}
export function toRecords(sheet, rows) {return rows.map((row) => Object.fromEntries(sheet.fields.map((field, index) => [field.id, cell(sheet, row, index)])));}
export function rowsCsv(sheet, rows) {
    return '\uFEFF' + [sheet.fields.map((field) => csvCell(field.id)).join(','), ...rows.map((row) => sheet.fields.map((_, index) => csvCell(cell(sheet, row, index))).join(','))].join('\r\n');
}

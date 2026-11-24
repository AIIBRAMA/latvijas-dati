import {csvCell, normalize} from './data.js';

export const FILTERS = [
    ['Gads', 'Gads'], ['Menesis_nr', 'Mēnesis (numurs)'], ['Ministrija', 'Ministrija'],
    ['Iestade', 'Iestāde'], ['Klasifikacija', 'Plāns / izpilde'], ['Plans_gadam_uz_datumu', 'Plāna datums (avota vērtība)'],
    ['Budzeta_tips', 'Budžeta tips'], ['Iestades_hier', 'Iestādes hierarhijas līmenis'],
    ['Pamatd_kons', 'Pamatdati / konsolidācija'], ['EKK_kods', 'EKK kods'],
    ['EKK_kods_1_limenis', 'EKK 1. līmenis'], ['EKK_kods_2_limenis', 'EKK 2. līmenis'], ['EKK_kods_7_limenis', 'EKK 7. līmenis'],
    ['Funkcija_augstakais_limenis_Nosaukums', 'Funkcija'], ['Datu_valuta', 'Valūta'],
    ['Novadi_pilsetas', 'Pašvaldība'], ['ATVK', 'ATVK kods'], ['Valuta', 'Valūta'],
    ['Novads', 'Novads / valstspilsēta'], ['Tips', 'Rindas tips'], ['ien_izd', 'Ieņēmumi / izdevumi'],
    ['EKK', 'EKK kods'], ['Funkcija_Liela', 'Funkcijas augstākais līmenis'],
    ['Funkcija_kods_1_limenis', 'Funkcijas kods (1. līmenis)'], ['Funkcija_1_limenis', 'Funkcija (1. līmenis)'],
    ['ministrija', 'Ministrija'], ['iestade', 'Iestāde'], ['tips', 'Ieņēmumi / izdevumi / finansēšana'],
    ['budzeta_tips', 'Budžeta tips'], ['progr_apaksprogr_kods', 'Programmas / apakšprogrammas kods'],
    ['ekk_kods', 'EKK kods'], ['funkcija', 'Funkcija'],
    ['sakotnejais_budzets', 'Sākotnējais budžets (avota vērtība)'],
    ['Ceturksnis', 'Ceturksnis'], ['Ce-turksnis', 'Ceturksnis'], ['Mēnesis', 'Mēnesis (avota kods)'],
    ['Iepirkuma veids', 'Iepirkuma veids'], ['Pēc līgum-cenu sliekšņa', 'Pēc līgumcenu sliekšņa']
];
export const PRIMARY_FILTERS = {
    XLSX: ['Gads', 'Menesis_nr', 'Novadi_pilsetas', 'Iestade', 'Klasifikacija'],
    JSON: ['Gads', 'ministrija', 'iestade', 'tips'],
    CSV: ['Gads', 'Mēnesis', 'Iepirkuma veids']
};
export const localSourceFormat = (preview) => preview?.sourceFormat ?? 'XLSX';
export const isAnnualPreview = (preview) => preview?.previewKind === 'treasury-annual-v1';

export function localPreviewPartitions(resource) {
    const preview = resource?.local_preview;
    const parts = preview?.partitions;
    if (parts === undefined) return undefined;
    if (localSourceFormat(preview) !== 'JSON' || !Array.isArray(parts) || !parts.length) return [];
    if (parts.some((part) => typeof part?.label !== 'string' || !/^\d{4}$/.test(part.label) ||
        !Number.isSafeInteger(part.total) || part.total < 1 || !localPreviewPath(resource, part)) ||
        new Set(parts.map((part) => part.label)).size !== parts.length ||
        parts.reduce((count, part) => count + part.total, 0) !== preview.total) return [];
    return [...parts].sort((a, b) => b.label.localeCompare(a.label));
}

export function localPreviewPath(resource, partition) {
    const preview = resource?.local_preview;
    const sourceFormat = localSourceFormat(preview);
    if (!preview || (sourceFormat !== 'XLSX' && sourceFormat !== 'JSON' && sourceFormat !== 'CSV')) return null;
    const path = partition?.path ?? (!partition ? preview.path : null);
    if (sourceFormat === 'CSV') {
        const match = typeof path === 'string' && /^data\/csv\/([\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12})-v1-([\da-f]{64})\.json$/.exec(path);
        return match && !partition && !isAnnualPreview(preview) && match[1] === resource.id &&
            match[2] === preview.sourceSha256 ? path : null;
    }
    if (isAnnualPreview(preview)) {
        const match = typeof path === 'string' && /^data\/annual-xlsx\/([\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12})-v1-([\da-f]{16})-([\da-f]{16})\.json$/.exec(path);
        return match && sourceFormat === 'XLSX' && !partition && match[1] === resource.id &&
            /^[\da-f]{64}$/.test(preview.sourceSha256 ?? '') && preview.sourceSha256.startsWith(match[2]) &&
            /^[\da-f]{64}$/.test(preview.sha256 ?? '') && preview.sha256.startsWith(match[3]) ? path : null;
    }
    const parts = typeof path === 'string' && /^data\/(xlsx|json)\/([\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12})-v1-([\da-f]{16,64})(?:-(\d{4}))?\.json$/.exec(path);
    if (!parts || parts[1] !== sourceFormat.toLowerCase() || parts[2] !== resource.id ||
        typeof preview.sourceSha256 !== 'string' || !preview.sourceSha256.startsWith(parts[3]) ||
        parts[4] !== partition?.label || (partition && sourceFormat !== 'JSON')) return null;
    return path;
}

export function chartLabelField(fields) {
    return ['Novadi_pilsetas', 'Novads', 'Iestade', 'iestade', 'ministrija'].find((id) => fields.some((field) => field.id === id)) || fields[0]?.id;
}

export function chartCurrencyField(fields) {
    return ['Datu_valuta', 'Valuta'].find((id) => fields.some((field) => field.id === id));
}

export function cell(sheet, row, index) {
    const value = row[index];
    return value === null || value === undefined ? null : sheet.fields[index].dictionary ? sheet.fields[index].dictionary[value] : value;
}
export function validateWorkbook(value, resource, partition) {
    if (value?.schemaVersion !== 1 || value.resourceId !== resource.id || value.sourceUrl !== resource.local_preview.sourceUrl || value.sourceSha256 !== resource.local_preview.sourceSha256 || (value.sourceFormat != null && value.sourceFormat !== localSourceFormat(resource.local_preview)) || !Array.isArray(value.sheets) || !value.sheets.length) throw new Error('Datu kopija neatbilst izvēlētajam resursam. Pārlādējiet vietni.');
    if (localSourceFormat(resource.local_preview) === 'CSV') {
        const preview = resource.local_preview;
        const sheet = value.sheets[0];
        if (partition || !localPreviewPath(resource) || value.sourceFormat !== 'CSV' || value.licenseId !== 'CC0-1.0' ||
            value.licenseId !== preview.licenseId || value.publisher !== preview.publisher ||
            value.convertedAt !== preview.convertedAt || value.sheets.length !== 1 ||
            !Number.isSafeInteger(preview.total) || preview.total < 1 || preview.total > 5000 ||
            !Array.isArray(sheet?.fields) || sheet.fields.length < 2 || sheet.fields.length > 32 ||
            !Array.isArray(sheet.rows) || sheet.rows.length !== sheet.total || sheet.total !== preview.total ||
            sheet.fields.some((field) => !field || field.type !== 'text' || typeof field.id !== 'string' || !field.id.trim() ||
                field.id.length > 256 || !Array.isArray(field.dictionary) || field.dictionary.length > sheet.total ||
                field.dictionary.some((v) => typeof v !== 'string' || !v.length || v.length > 256)) ||
            new Set(sheet.fields.map((f) => f.id.normalize('NFKC').trim().toLocaleLowerCase('lv'))).size !== sheet.fields.length ||
            sheet.rows.some((row) => !Array.isArray(row) || row.length !== sheet.fields.length ||
                row.some((v, i) => v !== null && (!Number.isSafeInteger(v) || v < 0 || v >= sheet.fields[i].dictionary.length)))) {
            throw new Error('CSV tabulas kopija neatbilst atlasītajam avotam.');
        }
        return value;
    }
    for (const sheet of value.sheets) {
        if (!Array.isArray(sheet.fields) || !Array.isArray(sheet.rows) || sheet.rows.length !== sheet.total || !sheet.fields.some((f) => f.id === 'Summa')) throw new Error('Datu kopijas struktūra nav derīga.');
        if (partition) {
            const yearIndex = sheet.fields.findIndex((field) => field.id === 'Gads');
            if (yearIndex < 0 || sheet.rows.some((row) => String(cell(sheet, row, yearIndex)) !== partition.label)) throw new Error('Datu kopijā ir citam gadam atbilstoši ieraksti.');
        }
    }
    if (isAnnualPreview(resource.local_preview)) {
        const {reportYear, total, convertedAt} = resource.local_preview;
        if (!isAnnualPreview(value) || value.sourceFormat !== 'XLSX' || !Number.isSafeInteger(reportYear) || value.reportYear !== reportYear ||
            value.convertedAt !== convertedAt || value.sheets.length !== 1 || value.sheets[0].total !== total ||
            value.sheets[0].fields[0]?.id !== 'Gads' || value.sheets[0].fields.find((field) => field.id === 'Summa')?.sourceId !== 'Summa_EUR' ||
            value.sheets[0].rows.some((row) => !Array.isArray(row) || row.length !== value.sheets[0].fields.length || row[0] !== reportYear)) throw new Error('Gada pārskata kopija neatbilst atlasītajam avotam.');
    }
    if (partition && value.sheets.reduce((count, sheet) => count + sheet.total, 0) !== partition.total) throw new Error('Datu kopijas ierakstu skaits neatbilst izvēlētajam gadam.');
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

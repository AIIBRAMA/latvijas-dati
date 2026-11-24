import {monthlySheetName, monthlySheetList, validMonthlyWorkbook} from './treasuryMonthly.js';
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
    ['Pasvaldibas nosaukums', 'Pašvaldība'], ['Pasvaldibas_nosaukums', 'Pašvaldība'],
    ['Ienemumu_klasifikacijas_kods', 'Ieņēmumu klasifikācija'],
    ['Funkcionalas_klasifikacijas_kods', 'Funkcionālā klasifikācija'],
    ['Izdevumu_ekonomiskas_klasifikacijas_kods', 'Izdevumu klasifikācija'],
    ['Ministrija_nosaukums', 'Ministrija'], ['Iestade_nosaukums', 'Iestāde'],
    ['Budzeta_tips_nosaukums', 'Budžeta tips'], ['Vienotais_EKK_Atslega', 'EKK kods'],
    ['Menesis_nosaukums', 'Mēnesis'], ['Konsolidacija', 'Konsolidācijas griezums'],
    ['Vienotais_EKK_Atslega_8_limenis', 'EKK kods (8. līmenis)'],
    ['Pasvaldiba_nosaukums', 'Pašvaldība'], ['Pasvaldiba_ATVK_kods', 'ATVK kods'],
    ['Dati_datums', 'Pārskata datums'], ['Iestades_NMR', 'Iestādes reģistrācijas numurs'],
    ['Budzeta_fin_plans_prognoze_gadam_uz_datumu', 'Gada plāns uz datumu'],
    ['Budzeta_fin_plans_prognoze_gadam_versija_Atslega', 'Gada plāna versija'],
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

export const isReviewedXlsx = (preview) => preview?.previewKind === 'treasury-reviewed-v1';
const february = '8c8ff425-d200-4a04-90c6-398508b8329b';
const subtotalId = 'ee5889d5-e35e-46a0-beb2-3a317a9a64cd';
const febMeasures = ['Finansesanas_plans_gadam_ar_izmainam', 'Ienemumi', 'Izdevumi', 'Finansesana'];
export const isTreasurySheets = (preview) => preview?.previewKind === 'treasury-sheets-v1';
const treasurySheetNames = {dati: 'DATI', ekk: 'EKK'};
function treasurySheetPath(resource, sheet) {
    const preview = resource.local_preview;
    if (!isTreasurySheets(preview) || preview.sourceFormat !== 'XLSX' ||
        !/^[0-9a-f]{64}$/.test(preview.sourceSha256 ?? '') || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(resource.id) ||
        !sheet?.name || sheet.name !== (preview.reportProfile === undefined ?
            (Object.hasOwn(treasurySheetNames, sheet.id) ? treasurySheetNames[sheet.id] : undefined) :
            monthlySheetName(preview.reportProfile, sheet.id)) ||
        !/^[0-9a-f]{64}$/.test(sheet?.sha256 ?? '') ||
        sheet.path !== `data/treasury-sheets/${resource.id}-${sheet.id}-v1-${sheet.sha256}.json`) return null;
    return sheet.path;
}
export function localTreasurySheets(resource) {
    const preview = resource?.local_preview;
    if (!isTreasurySheets(preview)) return undefined;
    const sheets = preview.reportSheets;
    if (preview.reportProfile !== undefined) {
        const expected = monthlySheetList(preview);
        if (!expected.length || !Array.isArray(sheets) || sheets.length !== expected.length) return [];
        const byId = new Map(sheets.map((s) => [s?.id, s]));
        const ordered = expected.map(({id, month}) => {
            const entry = byId.get(id);
            return entry && entry.month === month && treasurySheetPath(resource, entry) && Number.isSafeInteger(entry.total) &&
                entry.total > 0 && entry.total <= 15000 ? entry : null;
        });
        return ordered.every(Boolean) && ordered.reduce((n, s) => n + s.total, 0) === preview.total ? ordered : [];
    }
    if (!Array.isArray(sheets) || sheets.length !== 2 || sheets[0]?.id !== 'dati' || sheets[1]?.id !== 'ekk' ||
        sheets.some((s) => !treasurySheetPath(resource, s) || !Number.isSafeInteger(s.total) || s.total < 1 || s.total > 7200) ||
        sheets.reduce((n, s) => n + s.total, 0) !== preview.total) return [];
    return sheets;
}
export function selectedTreasurySheetPath(resource, sheet) {
    return localTreasurySheets(resource)?.includes(sheet) ? treasurySheetPath(resource, sheet) : null;
}
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
    if (isReviewedXlsx(preview)) {
        const match = typeof path === 'string' && /^data\/reviewed-xlsx\/([\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12})-v1-([\da-f]{64})\.json$/.exec(path);
        return match && !partition && sourceFormat === 'XLSX' && match[1] === resource.id &&
            match[2] === preview.sha256 && /^[\da-f]{64}$/.test(preview.sourceSha256 ?? '') ? path : null;
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
export function validateWorkbook(value, resource, partition, reportSheet) {
    if (value?.schemaVersion !== 1 || value.resourceId !== resource.id || value.sourceUrl !== resource.local_preview.sourceUrl || value.sourceSha256 !== resource.local_preview.sourceSha256 || (value.sourceFormat != null && value.sourceFormat !== localSourceFormat(resource.local_preview)) || !Array.isArray(value.sheets) || !value.sheets.length) throw new Error('Datu kopija neatbilst izvēlētajam resursam. Pārlādējiet vietni.');
    if (isTreasurySheets(resource.local_preview)) {
        const preview = resource.local_preview;
        const sheet = value.sheets[0];
        if (preview.reportProfile !== undefined) {
            if (partition || !selectedTreasurySheetPath(resource, reportSheet) || !isTreasurySheets(value) ||
                value.sourceFormat !== 'XLSX' || value.reportSheet !== reportSheet.id || value.convertedAt !== preview.convertedAt ||
                !validMonthlyWorkbook(value, preview, reportSheet, cell)) {
                throw new Error('Valsts kases tabula neatbilst atlasītajam avotam vai periodam.');
            }
            return value;
        }
        const data = reportSheet?.id === 'dati';
        const ids = Array.isArray(sheet?.fields) ? sheet.fields.map((f) => f?.id) : [];
        const lexical = /^-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?$/;
        if (partition || value.reportProfile !== undefined || !selectedTreasurySheetPath(resource, reportSheet) || !isTreasurySheets(value) ||
            value.sourceFormat !== 'XLSX' || value.reportSheet !== reportSheet.id || value.convertedAt !== preview.convertedAt ||
            value.reportScope?.year !== preview.reportScope?.year || !/^[0-9]{4}$/.test(preview.reportScope?.year ?? '') ||
            value.sheets.length !== 1 || sheet?.name !== reportSheet.name || sheet?.total !== reportSheet.total ||
            !Array.isArray(sheet?.rows) || sheet.rows.length !== reportSheet.total ||
            ids.some((id) => typeof id !== 'string' || !id || id.length > 256) || new Set(ids).size !== ids.length ||
            (data ? ids.length !== 32 || ids[0] !== 'Gads' || ids[1] !== 'Menesis_Atslega' ||
                ids[30] !== 'Datu_valuta' || ids[31] !== 'Summa'
                : JSON.stringify(ids) !== JSON.stringify(['EKK', 'Vienotais EKK - Key', 'EKK nosaukums'])) ||
            sheet.fields.some((f, i) => f.type !== (data && i === 31 ? 'decimal' : 'text') ||
                !Array.isArray(f.dictionary) || f.dictionary.length > sheet.total ||
                f.dictionary.some((v) => typeof v !== 'string' || v.length > 4096 ||
                    (f.type === 'decimal' && (v.length > 64 || !lexical.test(v))))) ||
            sheet.rows.some((row) => !Array.isArray(row) || row.length !== ids.length ||
                row.some((v, i) => v === null ? !data || [0, 1, 30, 31].includes(i) :
                    !Number.isSafeInteger(v) || v < 0 || v >= sheet.fields[i].dictionary.length) ||
                (data && (cell(sheet, row, 0) !== preview.reportScope.year ||
                    !/^(?:[1-9]|1[0-2])$/.test(cell(sheet, row, 1)) || cell(sheet, row, 30) !== 'Euro')))) {
            throw new Error('Valsts kases darblapa neatbilst atlasītajam pārskatam.');
        }
        return value;
    }
    if (isReviewedXlsx(resource.local_preview)) {
        const preview = resource.local_preview;
        const sheet = value.sheets[0];
        const feb = resource.id === february;
        const scope = preview.reportScope;
        const types = Array.isArray(sheet?.fields) ? sheet.fields.map((field) => field?.type) : [];
        const ids = Array.isArray(sheet?.fields) ? sheet.fields.map((field) => field?.id) : [];
        const readValue = (row, i) => row[i] === null ? null : sheet.fields[i].dictionary[row[i]];
        const subtotal = value.sourceSubtotal;
        const validFooter = resource.id === subtotalId ?
            subtotal?.sheet === '2025_Izdevumi' && subtotal.cell === 'F31030' &&
            subtotal.formula === 'SUBTOTAL(9,F2:F31029)' && subtotal.value === 28885561868 && subtotal.currency === 'EUR' : subtotal === undefined;
        if (partition || !localPreviewPath(resource) || !isReviewedXlsx(value) ||
            value.sourceFormat !== 'XLSX' || value.convertedAt !== preview.convertedAt || value.sheets.length !== 1 ||
            !scope || !/^\d{4}$/.test(scope.year) || value.reportScope?.year !== scope.year ||
            value.reportScope?.from !== scope.from || value.reportScope?.through !== scope.through ||
            (feb && (scope.year !== '2023' || scope.from !== '2023.01.01.' || scope.through !== '2023.02.28.')) ||
            (!feb && (scope.from !== undefined || scope.through !== undefined)) ||
            !validFooter || !Number.isSafeInteger(preview.total) || preview.total < 1 || preview.total > 75000 ||
            !Array.isArray(sheet?.rows) || sheet.rows.length !== sheet.total || sheet.total !== preview.total ||
            ids[0] !== 'Gads' || ids.some((id) => typeof id !== 'string' || !id) || new Set(ids).size !== ids.length ||
            (feb ? ids.length !== 26 || ids[1] !== 'Dati_par_periodu_No' || ids[2] !== 'Dati_par_periodu_Lidz' ||
                ids[21] !== 'Datu_valuta' || febMeasures.some((id, i) => ids[22+i] !== id)
                : ![5, 6].includes(ids.length) || ids.at(-1) !== 'EUR') ||
            types.some((type, i) => type !== (i < ids.length - (feb ? 4 : 1) ? 'text' : feb ? 'decimal' : 'number')) ||
            sheet.fields.some((field) => field.type === 'number' ? 'dictionary' in field : (!Array.isArray(field.dictionary) ||
                field.dictionary.length > sheet.total || field.dictionary.some((v) => typeof v !== 'string' ||
                    v.length > 4096 || (field.type === 'decimal' &&
                        (v.length > 64 || !/^-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?$/.test(v)))))) ||
            sheet.rows.some((row) => !Array.isArray(row) || row.length !== ids.length || row.some((v, i) => {
                if (types[i] === 'number') return !Number.isSafeInteger(v);
                if (v === null) return !feb || types[i] === 'decimal';
                return !Number.isSafeInteger(v) || v < 0 || v >= sheet.fields[i].dictionary.length;
            }) || readValue(row, 0) !== scope.year ||
                (feb && (readValue(row, 1) !== scope.from || readValue(row, 2) !== scope.through || readValue(row, 21) !== 'Euro')))) {
            throw new Error('Valsts kases vēsturiskā pārskata kopija neatbilst atlasītajam avotam.');
        }
        return value;
    }
    if (localSourceFormat(resource.local_preview) === 'CSV') {
        const preview = resource.local_preview;
        const sheet = value.sheets[0];
        if (partition || !localPreviewPath(resource) || value.sourceFormat !== 'CSV' || value.licenseId !== 'CC0-1.0' ||
            value.licenseId !== preview.licenseId || value.publisher !== preview.publisher ||
            value.convertedAt !== preview.convertedAt || value.sheets.length !== 1 ||
            !Number.isSafeInteger(preview.total) || preview.total < 1 || preview.total > 5000 ||
            (sheet?.sourceCaption !== undefined && (typeof sheet.sourceCaption !== 'string' || !sheet.sourceCaption ||
                sheet.sourceCaption.length > 256)) ||
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
export function previewCsvCell(field, value) {
    // An exact numeric lexeme cannot express a spreadsheet formula. Other text
    // remains protected by csvCell, even when it begins with a minus sign.
    if (field.type === 'decimal' && typeof value === 'string' && value.length <= 64 &&
        /^-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?$/.test(value)) return `"${value}"`;
    return csvCell(value);
}
export function rowsCsv(sheet, rows) {
    return '\uFEFF' + [sheet.fields.map((field) => csvCell(field.id)).join(','), ...rows.map((row) => sheet.fields.map((field, index) => previewCsvCell(field, cell(sheet, row, index))).join(','))].join('\r\n');
}

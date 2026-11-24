export const RAIM = 'raim-liabilities';
export const EXECUTION = 'state-execution';
export const COMPENSATION = 'state-compensation';
export const MONTHS_LV = ['Janvāris', 'Februāris', 'Marts', 'Aprīlis', 'Maijs', 'Jūnijs',
    'Jūlijs', 'Augusts', 'Septembris', 'Oktobris', 'Novembris', 'Decembris'];

const EKK = ['EKK', 'Vienotais EKK - Key', 'EKK nosaukums'];
const RAIM_FIELDS = ['Pasvaldiba_nosaukums', 'Pasvaldiba_ATVK_kods',
    'Planotie_pb_ien_bez_transf_ipasiem_merkiem_un_iemaks_PFIF_summa',
    'Aiznemumi_summa', 'Galvojumi_summa', 'Citas_ilgtermina_saistibas_summa',
    'Saistibas_kopa_summa', 'Saistibu_apmers_procenti', 'Dati_datums'];
const PLAN_DATE = 'Budzeta_fin_plans_prognoze_gadam_uz_datumu';
const PLAN_VERSION = 'Budzeta_fin_plans_prognoze_gadam_versija_Atslega';
const modes = new Set([RAIM, EXECUTION, COMPENSATION]);
const lexeme = /^-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?$/;

export function monthlySheetName(profile, id) {
    if (!modes.has(profile)) return undefined;
    if (profile === RAIM) return id === 'saistibas' ? 'Sheet1' : undefined;
    if (id === 'ekk') return 'EKK';
    if (/^m(?:0[1-9]|1[0-2])$/.test(id ?? '') || (profile === COMPENSATION && id === 'plans')) return 'AD';
    return undefined;
}

export function monthlySheetList(preview) {
    const profile = preview?.reportProfile;
    const scope = preview?.reportScope;
    if (profile === RAIM) {
        if (scope?.from !== '2009' || scope?.through !== '2025' || 'year' in scope) return [];
        return [{id: 'saistibas'}];
    }
    if (!modes.has(profile) || !['2025', '2026'].includes(scope?.year) || 'from' in scope || 'through' in scope) return [];
    const n = scope.year === '2025' ? 12 : 10;
    const months = Array.from({length: n}, (_, i) => ({id: 'm' + String(i + 1).padStart(2, '0'), month: String(i + 1)}));
    return [...months, ...(profile === COMPENSATION ? [{id: 'plans', month: '#'}] : []), {id: 'ekk'}];
}

export function reportPartLabel(sheet) {
    if (sheet?.id === 'plans') return 'Gada plāna versijas (AD)';
    if (sheet?.id === 'saistibas') return 'Pašvaldību saistības (2009–2025)';
    if (sheet?.id === 'ekk') return 'EKK kodu vārdnīca';
    return sheet?.month ? `${MONTHS_LV[Number(sheet.month) - 1]} (AD)` : sheet?.name;
}

export function validMonthlyWorkbook(value, preview, part, readCell) {
    const profile = preview.reportProfile;
    const sheet = value.sheets[0];
    const ids = Array.isArray(sheet?.fields) ? sheet.fields.map((f) => f?.id) : [];
    const len = ids.length;
    const monthly = part.name === 'AD';
    const ekk = part.name === 'EKK';
    const index = profile === EXECUTION ? 1 : 3;
    const scope = preview.reportScope;
    if (value.reportProfile !== profile || value.reportScope?.year !== scope.year ||
        value.reportScope?.from !== scope.from || value.reportScope?.through !== scope.through ||
        value.sheets.length !== 1 || sheet?.name !== part.name || sheet?.total !== part.total ||
        sheet?.cachedFormulaCount !== 0 || !Array.isArray(sheet?.rows) || sheet.rows.length !== part.total ||
        ids.some((id) => typeof id !== 'string' || !id || id.length > 256) || new Set(ids).size !== len ||
        (ekk ? JSON.stringify(ids) !== JSON.stringify(EKK) :
        monthly ? len !== (profile === EXECUTION ? 37 : 39) || ids[0] !== 'Gads' ||
            ids[index] !== 'Menesis_Atslega' || ids[index + 1] !== 'Menesis_nosaukums' ||
            ids[len - 13] !== 'Klasifikacija' || ids[len - 2] !== 'Datu_valuta' || ids[len - 1] !== 'Summa' ||
            (profile === COMPENSATION && (ids[1] !== PLAN_VERSION || ids[2] !== PLAN_DATE)) :
            JSON.stringify(ids) !== JSON.stringify(RAIM_FIELDS))) return false;
    const decimal = (i) => monthly ? i === len - 1 : !ekk && i >= 2 && i <= 7;
    const required = (i) => !monthly ? (!ekk || i !== 0 || profile === EXECUTION) :
        [0, index, index + 1, len - 13, len - 2, len - 1].includes(i) ||
        (profile === COMPENSATION && [1, 2].includes(i));
    if (sheet.fields.some((f, i) => f.type !== (decimal(i) ? 'decimal' : 'text') ||
        !Array.isArray(f.dictionary) || f.dictionary.length > sheet.total ||
        f.dictionary.some((v) => typeof v !== 'string' || !v || v.length > 4096 ||
            (decimal(i) && (v.length > 64 || !lexeme.test(v)))))) return false;
    return !sheet.rows.some((row) => {
        if (!Array.isArray(row) || row.length !== len ||
            row.some((v, i) => v === null ? required(i) : !Number.isSafeInteger(v) || v < 0 || v >= sheet.fields[i].dictionary.length)) return true;
        const at = (i) => readCell(sheet, row, i);
        if (ekk) return profile === COMPENSATION && row[0] !== null; // Published source column is blank.
        if (!monthly) return !/^\d{7}$/.test(at(1)) || !/^31\.12\.(?:2009|201[0-9]|202[0-5])\.$/.test(at(8));
        if (at(0) !== scope.year || at(index) !== part.month || at(index + 1) !==
            (part.month === '#' ? '#' : MONTHS_LV[Number(part.month) - 1]) || at(len - 2) !== 'Euro') return true;
        const cls = at(len - 13);
        if (profile === EXECUTION) return !['Izdevumi', 'Ieņēmumi', 'Finansēšana'].includes(cls);
        if (part.month !== '#') return cls !== 'Izdevumi' || at(1) !== '#' || at(2) !== '#';
        const date = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(at(2));
        if (!date || date[3] !== scope.year) return true;
        const dt = new Date(Date.UTC(Number(date[3]), Number(date[2]) - 1, Number(date[1])));
        if (dt.getUTCMonth() !== Number(date[2]) - 1 || dt.getUTCDate() !== Number(date[1])) return true;
        if (cls === 'Finansēšanas plāna prognoze gadam') return at(1) !== 'P000000' || date[1] !== '01' || date[2] !== '01';
        return cls !== 'Finansēšanas plāns gadam ar izmaiņām' || at(1) !== `F${date[3].slice(2)}${date[2]}${date[1]}`;
    });
}

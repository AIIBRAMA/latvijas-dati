// Browser presentation only. Never replace the source values used for CSV,
// filtering or calculations. Ambiguous field names are scoped to known datasets.
const KEY = (value) => String(value ?? '').normalize('NFD').replace(/\p{M}/gu, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');

const FINANCIAL_COLUMNS = new Map([
    ['pasvaldibu-parads-euro', new Set(['value'])],
    ['pasvaldibu-pamatbudzeta-izdevumi', new Set(['kop_izd', 'uztur_izd', 'kap_izd', 'izd_atlidzib', 'soc_pab_iz', 'iemak_pfif', 'parejie_izd_pec_uzkr'])],
    ['pasvaldibu-pamatbudzeta-ienemumi', new Set(['kop_ien', 'nod_ien_kopa', 'iin_ien', 'nin_ien', 'dot_pfif'])],
    ['pasvaldibu-budzetu-ienemumi-un-izdevumi-pa-menesiem', new Set(['finansesanas_plans_gadam_ar_izmainam', 'ienemumi', 'izdevumi', 'finansesana'])],
    ['valsts-un-pasvaldibu-sektora-ceturksna-finansu-dati', new Set([
        'parskata_perioda_sakuma', 'parskata_perioda_beigas', 'parskata_perioda_sakuma_bruto',
        'parskata_perioda_sakuma_vertibas_samazinajums', 'parskata_perioda_sakuma_neto',
        'parskata_perioda_beigas_bruto', 'parskata_perioda_beigas_vertibas_samazinajums',
        'parskata_perioda_beigas_neto', 'parskata_prioda_palielinajums', 'parskata_prioda_samazinajums',
        'parskata_perioda_palielinajums', 'parskata_perioda_samazinajums',
        'parskata_perioda_darijumi', 'parskata_perioda_citas_izmainas', 'parskata_perioda_valutas_kursa_svarstibas',
        'atlikums_parskata_perioda_sakuma', 'atlikums_parskata_perioda_beigas',
        'kavetie_maksajumi_parskata_perioda_beigas_mazak_par_30_dienam',
        'kavetie_maksajumi_parskata_perioda_beigas_30_dienas_un_vairak',
    ])],
]);

export function isAmountField(field, dataset, cumulative = false) {
    return [field.id, field.sourceId].filter(Boolean).some((label) => {
        const key = KEY(label);
        if (/%/.test(label) || /(?:^|_)(?:kods|koda|atslega|id|skaits|vienibas|procenti|procentos|procentu|likme|likmes|datums|nosaukums|valuta)(?:_|$)/.test(key)) return false;
        return /(?:^|_)(?:summa|amount|eur|eiro|lvl|lats|latos|ligumcena|ligumsumma)(?:_|$)/.test(key)
            || FINANCIAL_COLUMNS.get(dataset)?.has(key)
            || (cumulative && FINANCIAL_COLUMNS.get('pasvaldibu-budzetu-ienemumi-un-izdevumi-pa-menesiem').has(key));
    });
}

// Work from the decimal text so even sums above Number.MAX_SAFE_INTEGER
// format correctly when they arrive as strings. Trims display to cents only.
export function formatAmount(value) {
    if (typeof value !== 'string' && !Number.isFinite(value)) return null;
    let input = String(value).trim();
    if (input.length > 160) return null;
    if (/^[+−-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?$/.test(input)) input = input.replace(/[ \u00a0\u202f]/g, '');
    const parts = /^([+−-]?)(\d+)(?:[.,](\d+))?(?:[eE]([+-]?\d{1,3}))?$/.exec(input);
    if (!parts) return null;
    const [, sign, whole, fraction = '', exponent = '0'] = parts;
    const power = Number(exponent);
    if (Math.abs(power) > 100 || (fraction.length + whole.length) > 100) return null;
    const digits = whole + fraction;
    const cut = whole.length + power + 2;
    let cents = cut <= 0 ? 0n : BigInt(digits.slice(0, cut).padEnd(cut, '0'));
    if (cut >= 0 && digits[cut] >= '5') cents += 1n;
    const integer = String(cents / 100n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
    return `${cents !== 0n && /[−-]/.test(sign) ? '−' : ''}${integer},${String(cents % 100n).padStart(2, '0')}`;
}

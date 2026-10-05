export const number = (value) => new Intl.NumberFormat('lv-LV', {maximumFractionDigits: 2}).format(value);
export const normalize = (value = '') => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('lv');
export const format = (value = '') => String(value ?? '').trim().replace(/^\./, '').toUpperCase() || 'CITS';
export const date = (value) => value && !Number.isNaN(Date.parse(value)) ? new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleDateString('lv-LV') : 'Nav norādīts';
export const safeUrl = (value) => {try {const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null;} catch {return null;}};
export function filterDatasets(datasets, filters = {}, saved = []) {
    const terms = normalize(filters.q).split(/\s+/).filter(Boolean);
    const result = datasets.filter((d) => {
        const haystack = normalize([d.title, d.notes, d.organization?.title, ...(d.tags || [])].join(' '));
        return terms.every((term) => haystack.includes(term)) &&
            (!filters.group || (filters.group === '_none' ? !d.groups?.length : d.groups?.some((g) => g.name === filters.group))) &&
            (!filters.org || d.organization?.name === filters.org) &&
            (!filters.format || d.resources?.some((r) => format(r.format) === filters.format)) &&
            (!filters.saved || saved.includes(d.id)) &&
            (!filters.preview || d.resources?.some((r) => r.datastore_active));
    });
    return result.sort((a, b) => filters.sort === 'title' ? (a.title || '').localeCompare(b.title || '', 'lv') : (b.metadata_modified || '').localeCompare(a.metadata_modified || ''));
}
export function facets(datasets, type) {
    const values = new Map();
    for (const d of datasets) {
        let entries = type === 'groups' ? (d.groups?.length ? d.groups.map((g) => [g.name, g.title || g.name]) : [['_none', 'Bez norādītas nozares']]) : type === 'organization' ? (d.organization?.name ? [[d.organization.name, d.organization.title || d.organization.name]] : []) : [...new Set((d.resources || []).map((r) => format(r.format)))].map((f) => [f, f]);
        for (const [id, name] of new Map(entries)) {const existing = values.get(id) || {id, name, amount: 0}; existing.amount++; values.set(id, existing);}
    }
    return [...values.values()].sort((a, b) => b.amount - a.amount || a.name.localeCompare(b.name, 'lv'));
}
export function csvCell(value) {
    let text = String(value ?? '');
    if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
}
export function catalogCsv(datasets) {
    return '\uFEFF' + [['Nosaukums', 'Iestāde', 'Nozares', 'Formāti', 'Metadatu atjaunošana', 'Licence', 'Avots'], ...datasets.map((d) => [d.title, d.organization?.title, d.groups.map((g) => g.title).join('; '), [...new Set(d.resources.map((r) => format(r.format)))].join('; '), d.metadata_modified, d.license_title, `https://data.gov.lv/dati/dataset/${encodeURIComponent(d.name)}`])].map((row) => row.map(csvCell).join(',')).join('\r\n');
}
export function numeric(value) {
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    if (typeof value !== 'string' || !value.trim()) return null;
    let text = value.trim();
    // Latvian sources often use spaces (including NBSP) as thousands separators.
    if (/^-?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?$/.test(text)) text = text.replace(/[ \u00a0\u202f]/g, '');
    const candidate = text.replace(',', '.');
    return /^-?\d+(\.\d+)?$/.test(candidate) && Number.isFinite(Number(candidate)) ? Number(candidate) : null;
}

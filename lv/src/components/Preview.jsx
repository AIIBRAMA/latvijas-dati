import React, {useEffect, useMemo, useState} from 'react';
import {ckan} from '../api.js';
import {csvCell, number, numeric} from '../data.js';
import {FILTERS, filterOptions, filterRows, rowsCsv, toRecords, validateWorkbook} from '../localPreview.js';
export function download(text, filename, type = 'text/csv;charset=utf-8') {const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);}
export default function Preview({resource}) {
    const [page, setPage] = useState(0), [query, setQuery] = useState(''), [draft, setDraft] = useState('');
    const [data, setData] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0);
    const [view, setView] = useState('table'), [x, setX] = useState(''), [y, setY] = useState('');
    const local = Boolean(resource.local_preview);
    const [workbook, setWorkbook] = useState(null), [sheetIndex, setSheetIndex] = useState(0), [filters, setFilters] = useState({});
    useEffect(() => {
        if (!local) return undefined;
        const abort = new AbortController(); setWorkbook(null); setLoading(true); setError('');
        const path = resource.local_preview.path;
        if (!/^data\/xlsx\/[a-zA-Z0-9-]+\.json$/.test(path)) {setError('XLSX priekšskatījuma adrese nav derīga.'); setLoading(false); return () => abort.abort();}
        fetch(`${import.meta.env.BASE_URL}${path}`, {signal: abort.signal}).then((response) => {
            if (!response.ok) throw new Error('XLSX tabulas kopiju neizdevās ielādēt. Pārlādējiet vietni vai atveriet oriģinālo resursu.');
            return response.json();
        }).then((value) => {setWorkbook(validateWorkbook(value, resource)); setLoading(false);})
            .catch((e) => {if (e.name !== 'AbortError') {setError(e.message); setLoading(false);}});
        return () => abort.abort();
    }, [resource.id, resource.local_preview?.path, retry, local]);
    const sheet = workbook?.sheets[sheetIndex];
    const allRows = useMemo(() => sheet ? filterRows(sheet, filters, query) : [], [sheet, filters, query]);
    const options = useMemo(() => sheet ? FILTERS.filter(([field]) => sheet.fields.some((f) => f.id === field)).map(([field, label]) => ({field, label, values: filterOptions(sheet, field)})) : [], [sheet]);
    const localPage = Math.min(page, Math.max(0, Math.ceil(allRows.length / 50) - 1));
    const localData = useMemo(() => sheet ? {fields: sheet.fields, total: allRows.length, records: toRecords(sheet, allRows.slice(localPage * 50, (localPage + 1) * 50))} : null, [sheet, allRows, localPage]);
    useEffect(() => {if (local) return undefined; const abort = new AbortController(); setLoading(true); setData(null); setError('');
        ckan('datastore_search', {resource_id: resource.id, limit: 50, offset: page * 50, ...(query ? {q: query} : {})}, abort.signal)
            .then((r) => {setData(r); setLoading(false);}).catch((e) => {if (e.name !== 'AbortError') {setError(e.message); setLoading(false);}});
        return () => abort.abort();
    }, [resource.id, page, query, retry, local]);
    const displayed = local ? localData : data;
    const currentPage = local ? localPage : page;
    const fields = displayed?.fields?.filter((f) => f.id !== '_id' && f.id !== '_full_text') || [];
    const numericFields = fields.filter((f) => (!local || f.id === 'Summa') && displayed.records.some((r) => numeric(r[f.id]) !== null));
    const xField = fields.find((f) => f.id === x)?.id || (local && fields.some((f) => f.id === 'Iestade') ? 'Iestade' : fields[0]?.id);
    const yField = numericFields.find((f) => f.id === y)?.id || numericFields[0]?.id;
    const points = useMemo(() => (displayed?.records || []).map((r) => ({label: String(r[xField] ?? ''), value: numeric(r[yField])})).filter((p) => p.value !== null), [displayed, xField, yField]);
    const low = Math.min(0, ...points.map((p) => p.value)), high = Math.max(0, ...points.map((p) => p.value)), span = high - low || 1;
    const zero = -low / span * 100;
    function renderFilter({field, label, values}) {return <label key={field}>{label}<select value={filters[field] || ''} onChange={(e) => {setPage(0); setFilters({...filters, [field]: e.target.value});}}><option value="">Visas vērtības</option>{values.map((value) => <option key={value} value={value}>{value === '#' ? '# — avota apzīmējums' : value}</option>)}</select></label>;}
    function exportRows() {download('\uFEFF' + [fields.map((f) => f.id), ...displayed.records.map((r) => fields.map((f) => r[f.id]))].map((row) => row.map(csvCell).join(',')).join('\r\n'), `priekskatijums-${resource.id}-${currentPage + 1}.csv`);}
    return <section className="preview panel" aria-label="Resursa priekšskatījums">
        <div className="section-heading"><div><span className="eyebrow">{local ? 'NO XLSX SAGATAVOTA TABULA' : 'DATI NO AVOTA'}</span><h2>{resource.name || 'Tabulas priekšskatījums'}</h2></div></div>
        {local && workbook && <>
            <p className="caption">XLSX kopija iegūta {new Date(workbook.convertedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika. Avota rindas saglabātas bez summēšanas.</p>
            <label className="sheet-select">Darblapa<select value={sheetIndex} onChange={(e) => {setSheetIndex(Number(e.target.value)); setPage(0); setFilters({}); setX(''); setY('');}}>{workbook.sheets.map((s, i) => <option key={i} value={i}>{s.name} ({number(s.total)} rindas)</option>)}</select></label>
            <div className="xlsx-filter-panel"><h3>Atlasīt datus</h3><div className="xlsx-filters">{options.filter(({field}) => ['Gads', 'Menesis_nr', 'Iestade', 'Klasifikacija'].includes(field)).map(renderFilter)}</div>
                <details className="advanced-filters"><summary>Papildu filtri{Object.entries(filters).some(([field, value]) => value && !['Gads', 'Menesis_nr', 'Iestade', 'Klasifikacija'].includes(field)) ? ' · ir aktīvi filtri' : ''}</summary><div className="xlsx-filters">{options.filter(({field}) => !['Gads', 'Menesis_nr', 'Iestade', 'Klasifikacija'].includes(field)).map(renderFilter)}</div></details>
                <button className="text-button" onClick={() => {setFilters({}); setQuery(''); setDraft(''); setPage(0);}}>Notīrīt tabulas filtrus</button>
            </div>
            <p className="caption">Filtri, meklēšana un atlases CSV aptver visu izvēlēto darblapu. “#” saglabāts tieši no avota. Rindās var būt plāns, izpilde un dažādu līmeņu kopsummas — tās netiek automātiski saskaitītas.</p>
            {sheet?.cachedFormulaCount > 0 && <p className="caption">Formulām izmantotas avota failā saglabātās vērtības; vietne formulas nepārrēķina.</p>}
        </>}
        <form className="row-search" onSubmit={(e) => {e.preventDefault(); setPage(0); setQuery(draft);}}><label className="sr-only" htmlFor="row-search">Meklēt tabulas ierakstos</label><input id="row-search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Meklēt tabulas ierakstos…"/><button className="button secondary">Meklēt ierakstos</button></form>
        {loading && <p role="status">{local ? 'Ielādē no XLSX sagatavoto tabulu… Lielam failam tas var aizņemt brīdi.' : 'Ielādē tabulu no data.gov.lv…'}</p>}
        {error && <div role="alert" className="notice">{error} <button className="text-button" onClick={() => setRetry(retry + 1)}>Mēģināt vēlreiz</button></div>}
        {displayed && <>
            <div className="preview-toolbar"><p>{number(displayed.total)} ieraksti · šajā lapā {displayed.records.length}</p><div className="button-group"><button aria-pressed={view === 'table'} onClick={() => setView('table')}>Tabula</button><button aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Diagramma</button><button onClick={exportRows}>Lejupielādēt šo lapu ↓</button>{local && <button disabled={!allRows.length} onClick={() => download(rowsCsv(sheet, allRows), `valsts-kase-${resource.id}-atlase.csv`)}>Visa atlase CSV ↓</button>}</div></div>
            {view === 'table' ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Ritināma datu tabula"><table><thead><tr>{fields.map((f) => <th key={f.id}>{f.id}</th>)}</tr></thead><tbody>{displayed.records.map((row, i) => <tr key={i}>{fields.map((f) => <td key={f.id}>{typeof row[f.id] === 'object' && row[f.id] !== null ? JSON.stringify(row[f.id]) : String(row[f.id] ?? '—')}</td>)}</tr>)}</tbody></table>{!displayed.records.length && <p>Nav atrastu ierakstu. Mainiet meklējumu.</p>}</div> : numericFields.length ? <>
                <div className="chart-selects"><label>Etiķetes<select value={xField} onChange={(e) => setX(e.target.value)}>{fields.map((f) => <option key={f.id}>{f.id}</option>)}</select></label><label>Skaitliskā vērtība<select value={yField} onChange={(e) => setY(e.target.value)}>{numericFields.map((f) => <option key={f.id}>{f.id}</option>)}</select></label></div>
                <p className="caption">Attēloti tikai šīs lapas {displayed.records.length} ieraksti, bez summēšanas. Tukšas un neskaitliskas vērtības izlaistas. {local ? 'Summa izteikta kolonnā Datu_valuta norādītajā valūtā. Viena etiķete var atkārtoties dažādām klasifikācijām; diagramma šīs rindas neapvieno.' : 'Mērvienību pārbaudiet resursa aprakstā.'}</p>
                <div className="bar-chart" aria-label={`${yField} pēc ${xField}`}>{points.map((p, i) => <div className="bar-row" key={i}><span title={p.label}>{p.label}</span><div className="bar-track"><i className="zero" style={{left: `${zero}%`}}/><i className={p.value < 0 ? 'bar negative' : 'bar'} style={{left: `${(Math.min(0, p.value) - low) / span * 100}%`, width: `${Math.abs(p.value) / span * 100}%`}}/></div><strong>{number(p.value)}</strong></div>)}</div>
            </> : <p className="notice">Šajā lapā nav diagrammai izmantojamu skaitlisku vērtību.</p>}
            <div className="pagination"><button disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>← Iepriekšējā</button><span>{currentPage + 1}. lapa · līdz 50 ierakstiem</span><button disabled={(currentPage + 1) * 50 >= displayed.total} onClick={() => setPage(currentPage + 1)}>Nākamā →</button></div>
        </>}
    </section>;
}

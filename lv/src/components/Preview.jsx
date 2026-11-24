import React, {useEffect, useMemo, useState} from 'react';
import {ckan} from '../api.js';
import {csvCell, number, numeric} from '../data.js';
import {FILTERS, PRIMARY_FILTERS, chartCurrencyField, chartLabelField, filterOptions, filterRows, isAnnualPreview, localPreviewPartitions, localPreviewPath, localSourceFormat, rowsCsv, toRecords, validateWorkbook} from '../localPreview.js';
export function download(text, filename, type = 'text/csv;charset=utf-8') {const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);}
export default function Preview({resource}) {
    const [page, setPage] = useState(0), [query, setQuery] = useState(''), [draft, setDraft] = useState('');
    const [data, setData] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0);
    const [view, setView] = useState('table'), [x, setX] = useState(''), [y, setY] = useState('');
    const local = Boolean(resource.local_preview);
    const jsonSource = localSourceFormat(resource.local_preview) === 'JSON';
    const localFormat = jsonSource ? 'JSON' : 'XLSX';
    const annual = isAnnualPreview(resource.local_preview);
    const primaryFields = annual ? ['Novads', 'Ministrija', 'Iestade', 'Tips', 'ien_izd'] : PRIMARY_FILTERS[localFormat];
    const [workbook, setWorkbook] = useState(null), [sheetIndex, setSheetIndex] = useState(0), [filters, setFilters] = useState({});
    const [selectedYear, setSelectedYear] = useState('');
    const partitions = useMemo(() => localPreviewPartitions(resource), [resource]);
    const partition = partitions?.find(({label}) => label === selectedYear) ?? partitions?.[0];
    useEffect(() => {
        if (!local) return undefined;
        const abort = new AbortController(); setWorkbook(null); setLoading(true); setError('');
        const path = partitions && !partition ? null : localPreviewPath(resource, partition);
        if (!path) {setError('Tabulas kopijas adrese nav derīga. Atveriet oriģinālo resursu.'); setLoading(false); return () => abort.abort();}
        fetch(`${import.meta.env.BASE_URL}${path}`, {signal: abort.signal}).then((response) => {
            if (!response.ok) throw new Error('Tabulas kopiju neizdevās ielādēt. Pārlādējiet vietni vai atveriet oriģinālo resursu.');
            return response.json();
        }).then((value) => {if (!abort.signal.aborted) {setWorkbook(validateWorkbook(value, resource, partition)); setLoading(false);}})
            .catch((e) => {if (!abort.signal.aborted && e.name !== 'AbortError') {setError(e.message); setLoading(false);}});
        return () => abort.abort();
    }, [resource, retry, local, partitions, partition]);
    const sheet = workbook?.sheets[sheetIndex];
    const allRows = useMemo(() => sheet ? filterRows(sheet, filters, query) : [], [sheet, filters, query]);
    const options = useMemo(() => sheet ? FILTERS.filter(([field]) => (field !== 'Gads' || !partition) && sheet.fields.some((f) => f.id === field)).map(([field, label]) => ({field, label, values: filterOptions(sheet, field)})).filter(({values}) => values.length > 0) : [], [sheet, partition]);
    const mainOptions = primaryFields.map((id) => options.find(({field}) => field === id)).filter(Boolean);
    const advancedOptions = options.filter(({field}) => !primaryFields.includes(field));
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
    const xField = fields.find((f) => f.id === x)?.id || (local ? chartLabelField(fields) : fields[0]?.id);
    const yField = numericFields.find((f) => f.id === y)?.id || numericFields[0]?.id;
    const currencyField = local && chartCurrencyField(fields);
    const columnLabel = (id) => id === 'Summa' ? (annual ? 'Summa (EUR)' : jsonSource ? 'Summa (tāmes izmaiņu līmenī)' : id) : id;
    const points = useMemo(() => (displayed?.records || []).map((r) => ({label: String(r[xField] ?? ''), value: numeric(r[yField])})).filter((p) => p.value !== null), [displayed, xField, yField]);
    const low = Math.min(0, ...points.map((p) => p.value)), high = Math.max(0, ...points.map((p) => p.value)), span = high - low || 1;
    const zero = -low / span * 100;
    function renderFilter({field, label, values}) {return <label key={field}>{label}<select value={filters[field] || ''} onChange={(e) => {setPage(0); setFilters({...filters, [field]: e.target.value});}}><option value="">Visas vērtības</option>{values.map((value) => <option key={value} value={value}>{value === '#' ? '# — avota apzīmējums' : value}</option>)}</select></label>;}
    const yearSuffix = partition ? `-${partition.label}` : '';
    function exportRows() {download('\uFEFF' + [fields.map((f) => f.id), ...displayed.records.map((r) => fields.map((f) => r[f.id]))].map((row) => row.map(csvCell).join(',')).join('\r\n'), `priekskatijums-${resource.id}${yearSuffix}-${currentPage + 1}.csv`);}
    function selectYear(event) {
        setSelectedYear(event.target.value); setWorkbook(null); setLoading(true); setError('');
        setSheetIndex(0); setFilters({}); setPage(0); setQuery(''); setDraft(''); setX(''); setY('');
    }
    return <section className="preview panel" aria-label="Resursa priekšskatījums">
        <div className="section-heading"><div><span className="eyebrow">{local ? `NO ${localFormat} SAGATAVOTA TABULA` : 'DATI NO AVOTA'}</span><h2>{resource.name || 'Tabulas priekšskatījums'}</h2></div></div>
        {jsonSource && resource.local_preview.snapshotFallback === true && <p className="notice" role="status"><strong>Rādīta pēdējā pieejamā pārbaudītā kopija.</strong> Valsts kases avotu atjaunošanas laikā nevarēja sasniegt. Kopijas dati pārbaudīti {new Date(resource.local_preview.sourceCheckedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika; kopija var nebūt aktuāla.</p>}
        {annual && resource.local_preview.snapshotFallback === true && <p className="notice" role="status"><strong>Rādīta pēdējā pilnā pārskatu kopija.</strong> Atjaunošanas laikā neizdevās pārbaudīt visus 12 gada pārskatus. Kopija sagatavota {new Date(resource.local_preview.convertedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika.</p>}
        {partition && <label className="sheet-select">Gads<select value={partition.label} onChange={selectYear} aria-describedby="preview-year-scope">{partitions.map(({label, total}) => <option key={label} value={label}>{label} ({number(total)} rindas)</option>)}</select></label>}
        {partition && <p className="caption" id="preview-year-scope">Lai ielādētu mazāk datu, vienlaikus atvērts tikai viens gads. Meklēšana, filtri un CSV attiecas uz izvēlēto gadu; vairāku gadu dati netiek apvienoti.</p>}
        {local && workbook && <>
            <p className="caption">{localFormat} avota kopija sagatavota {new Date(workbook.convertedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika. Avota rindas nav summētas.</p>
            {(!jsonSource || workbook.sheets.length > 1) && <label className="sheet-select">{jsonSource ? 'Tabula' : 'Darblapa'}<select value={sheetIndex} onChange={(e) => {setSheetIndex(Number(e.target.value)); setPage(0); setFilters({}); setX(''); setY('');}}>{workbook.sheets.map((s, i) => <option key={i} value={i}>{s.name} ({number(s.total)} rindas)</option>)}</select></label>}
            {options.length > 0 && <div className="xlsx-filter-panel"><h3>Atlasīt datus</h3>{mainOptions.length > 0 && <div className="xlsx-filters">{mainOptions.map(renderFilter)}</div>}
                {advancedOptions.length > 0 && <details className="advanced-filters"><summary>Papildu filtri{advancedOptions.some(({field}) => filters[field]) ? ' · ir aktīvi filtri' : ''}</summary><div className="xlsx-filters">{advancedOptions.map(renderFilter)}</div></details>}
                <button className="text-button" onClick={() => {setFilters({}); setQuery(''); setDraft(''); setPage(0);}}>Notīrīt tabulas filtrus</button>
            </div>}
            <p className="caption">{jsonSource ? `${partition ? '' : 'Filtri, meklēšana un atlases CSV aptver visu tabulu. '}“Gads” un “Summa” atbilst avota laukiem gads un vertiba. Summas attiecas uz tāmes izmaiņām, nevis faktisko budžeta izpildi.` : annual ? 'Filtri, meklēšana un CSV aptver visu gada pārskatu. Avota Summa_EUR ir summa eiro. Pamatdati, konsolidācija, korekcijas un klasifikācijas kopsummas netiek automātiski saskaitītas.' : 'Filtri, meklēšana un atlases CSV aptver visu izvēlēto darblapu. “#” saglabāts tieši no avota. Rindās var būt plāns, izpilde un dažādu līmeņu kopsummas; tās netiek automātiski saskaitītas.'} Tukša vērtība nav nulle.</p>
            {sheet?.cachedFormulaCount > 0 && <p className="caption">Formulām izmantotas avota failā saglabātās vērtības; vietne formulas nepārrēķina.</p>}
        </>}
        <form className="row-search" onSubmit={(e) => {e.preventDefault(); setPage(0); setQuery(draft);}}><label className="sr-only" htmlFor="row-search">Meklēt tabulas ierakstos</label><input id="row-search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Meklēt tabulas ierakstos…"/><button className="button secondary">Meklēt ierakstos</button></form>
        {loading && <p role="status">{local ? 'Ielādē sagatavoto tabulu… Lielam failam tas var aizņemt brīdi.' : 'Ielādē tabulu no data.gov.lv…'}</p>}
        {error && <div role="alert" className="notice">{error} <button className="text-button" onClick={() => setRetry(retry + 1)}>Mēģināt vēlreiz</button></div>}
        {displayed && <>
            <div className="preview-toolbar"><p>{number(displayed.total)} ieraksti · šajā lapā {displayed.records.length}</p><div className="button-group"><button aria-pressed={view === 'table'} onClick={() => setView('table')}>Tabula</button><button aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Diagramma</button><button onClick={exportRows}>Lejupielādēt šo lapu ↓</button>{local && <button disabled={!allRows.length} onClick={() => download(rowsCsv(sheet, allRows), `valsts-kase-${resource.id}${yearSuffix}-atlase.csv`)}>{partition ? 'Gada atlase CSV ↓' : 'Visa atlase CSV ↓'}</button>}</div></div>
            {view === 'table' ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Ritināma datu tabula"><table><thead><tr>{fields.map((f) => <th key={f.id} scope="col">{columnLabel(f.id)}</th>)}</tr></thead><tbody>{displayed.records.map((row, i) => <tr key={i}>{fields.map((f) => <td key={f.id}>{typeof row[f.id] === 'object' && row[f.id] !== null ? JSON.stringify(row[f.id]) : String(row[f.id] ?? '—')}</td>)}</tr>)}</tbody></table>{!displayed.records.length && <p>Nav atrastu ierakstu. Mainiet meklējumu.</p>}</div> : numericFields.length ? <>
                <div className="chart-selects"><label>Etiķetes<select value={xField} onChange={(e) => setX(e.target.value)}>{fields.map((f) => <option key={f.id} value={f.id}>{columnLabel(f.id)}</option>)}</select></label><label>Skaitliskā vērtība<select value={yField} onChange={(e) => setY(e.target.value)}>{numericFields.map((f) => <option key={f.id} value={f.id}>{columnLabel(f.id)}</option>)}</select></label></div>
                <p className="caption">Attēloti {points.length} no šīs lapas {displayed.records.length} ierakstiem, bez summēšanas. Tukšas un neskaitliskas vērtības izlaistas. {currencyField ? `Valūta norādīta kolonnā ${currencyField}.` : annual ? 'Vērtības ir eiro (EUR).' : 'Mērvienību pārbaudiet resursa aprakstā.'} {local && 'Vienādas etiķetes diagrammā netiek apvienotas.'}</p>
                <div className="bar-chart" aria-label={`${columnLabel(yField)} pēc ${columnLabel(xField)}`}>{points.map((p, i) => <div className="bar-row" key={i}><span title={p.label}>{p.label}</span><div className="bar-track"><i className="zero" style={{left: `${zero}%`}}/><i className={p.value < 0 ? 'bar negative' : 'bar'} style={{left: `${(Math.min(0, p.value) - low) / span * 100}%`, width: `${Math.abs(p.value) / span * 100}%`}}/></div><strong>{number(p.value)}</strong></div>)}</div>
            </> : <p className="notice">Šajā lapā nav diagrammai izmantojamu skaitlisku vērtību.</p>}
            <div className="pagination"><button disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>← Iepriekšējā</button><span>{currentPage + 1}. lapa · līdz 50 ierakstiem</span><button disabled={(currentPage + 1) * 50 >= displayed.total} onClick={() => setPage(currentPage + 1)}>Nākamā →</button></div>
        </>}
    </section>;
}

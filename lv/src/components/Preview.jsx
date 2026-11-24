import React, {useEffect, useMemo, useState} from 'react';
import {ckan} from '../api.js';
import {csvCell, number, numeric} from '../data.js';
import {COMPENSATION, RAIM, reportPartLabel} from '../treasuryMonthly.js';
import {FILTERS, PRIMARY_FILTERS, chartCurrencyField, chartLabelField, filterOptions, filterRows, isAnnualPreview, isReviewedXlsx, isTreasurySheets, localPreviewPartitions, localPreviewPath, localSourceFormat, localTreasurySheets, selectedTreasurySheetPath, previewCsvCell, rowsCsv, toRecords, validateWorkbook} from '../localPreview.js';
export function download(text, filename, type = 'text/csv;charset=utf-8') {const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);}
export default function Preview({resource}) {
    const [page, setPage] = useState(0), [query, setQuery] = useState(''), [draft, setDraft] = useState('');
    const [data, setData] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0);
    const [view, setView] = useState('table'), [x, setX] = useState(''), [y, setY] = useState('');
    const local = Boolean(resource.local_preview);
    const jsonSource = localSourceFormat(resource.local_preview) === 'JSON';
    const csvSource = localSourceFormat(resource.local_preview) === 'CSV';
    const procurementCsv = csvSource && resource.local_preview.publisher === 'Iepirkumu uzraudzības birojs';
    const localFormat = csvSource ? 'CSV' : jsonSource ? 'JSON' : 'XLSX';
    const annual = isAnnualPreview(resource.local_preview);
    const reviewed = isReviewedXlsx(resource.local_preview);
    const treasuryMulti = isTreasurySheets(resource.local_preview);
    const reportProfile = resource.local_preview?.reportProfile;
    const cumulative = reviewed && Boolean(resource.local_preview.reportScope?.through);
    const primaryFields = reportProfile === RAIM ? ['Pasvaldiba_nosaukums', 'Pasvaldiba_ATVK_kods', 'Dati_datums'] :
        reportProfile ? ['Budzeta_fin_plans_prognoze_gadam_uz_datumu', 'Ministrija_nosaukums', 'Iestade_nosaukums', 'Klasifikacija'] : treasuryMulti ? ['Menesis_nosaukums', 'Budzeta_tips_nosaukums', 'Konsolidacija', 'Vienotais_EKK_Atslega_8_limenis'] : reviewed ? (cumulative ?
        ['Ministrija_nosaukums', 'Iestade_nosaukums', 'Budzeta_tips_nosaukums', 'Vienotais_EKK_Atslega'] :
        ['Pasvaldibas nosaukums', 'Pasvaldibas_nosaukums', 'Ienemumu_klasifikacijas_kods', 'Funkcionalas_klasifikacijas_kods']) : annual ? ['Novads', 'Ministrija', 'Iestade', 'Tips', 'ien_izd'] : PRIMARY_FILTERS[localFormat];
    const [loadedWorkbook, setWorkbook] = useState(null), [sheetIndex, setSheetIndex] = useState(0), [filters, setFilters] = useState({});
    const [selectedYear, setSelectedYear] = useState('');
    const [selectedReportSheet, setSelectedReportSheet] = useState('');
    const reportSheets = useMemo(() => localTreasurySheets(resource), [resource]);
    const reportSheet = reportSheets?.find(({id}) => id === selectedReportSheet) ?? reportSheets?.[0];
    const workbook = treasuryMulti && loadedWorkbook?.reportSheet !== reportSheet?.id ? null : loadedWorkbook;
    const partitions = useMemo(() => localPreviewPartitions(resource), [resource]);
    const partition = partitions?.find(({label}) => label === selectedYear) ?? partitions?.[0];
    useEffect(() => {
        if (!local) return undefined;
        const abort = new AbortController(); setWorkbook(null); setLoading(true); setError('');
        const path = treasuryMulti ? selectedTreasurySheetPath(resource, reportSheet) : partitions && !partition ? null : localPreviewPath(resource, partition);
        if (!path) {setError('Tabulas kopijas adrese nav derīga. Atveriet oriģinālo resursu.'); setLoading(false); return () => abort.abort();}
        fetch(`${import.meta.env.BASE_URL}${path}`, {signal: abort.signal}).then((response) => {
            if (!response.ok) throw new Error('Tabulas kopiju neizdevās ielādēt. Pārlādējiet vietni vai atveriet oriģinālo resursu.');
            return response.json();
        }).then((value) => {if (!abort.signal.aborted) {setWorkbook(validateWorkbook(value, resource, partition, reportSheet)); setLoading(false);}})
            .catch((e) => {if (!abort.signal.aborted && e.name !== 'AbortError') {setError(e.message); setLoading(false);}});
        return () => abort.abort();
    }, [resource, retry, local, partitions, partition, treasuryMulti, reportSheet]);
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
    const numericFields = fields.filter((f) => (!local || f.id === 'Summa' || (reviewed && !cumulative && f.id === 'EUR')) && displayed.records.some((r) => numeric(r[f.id]) !== null));
    const xField = fields.find((f) => f.id === x)?.id || (local ? chartLabelField(fields) : fields[0]?.id);
    const yField = numericFields.find((f) => f.id === y)?.id || numericFields[0]?.id;
    const currencyField = local && chartCurrencyField(fields);
    const columnLabel = (id) => id === 'Summa' ? (annual ? 'Summa (EUR)' : jsonSource ? 'Summa (tāmes izmaiņu līmenī)' : id) : id;
    const points = useMemo(() => (displayed?.records || []).map((r) => ({label: String(r[xField] ?? ''), value: numeric(r[yField])})).filter((p) => p.value !== null), [displayed, xField, yField]);
    const low = Math.min(0, ...points.map((p) => p.value)), high = Math.max(0, ...points.map((p) => p.value)), span = high - low || 1;
    const zero = -low / span * 100;
    function renderFilter({field, label, values}) {return <label key={field}>{label}<select value={filters[field] || ''} onChange={(e) => {setPage(0); setFilters({...filters, [field]: e.target.value});}}><option value="">Visas vērtības</option>{values.map((value) => <option key={value} value={value}>{value === '#' ? '# — avota apzīmējums' : value}</option>)}</select></label>;}
    const yearSuffix = reportSheet ? `-${reportSheet.id}` : partition ? `-${partition.label}` : '';
    function exportRows() {download('\uFEFF' + [fields.map((f) => csvCell(f.id)).join(','), ...displayed.records.map((r) => fields.map((f) => local ? previewCsvCell(f, r[f.id]) : csvCell(r[f.id])).join(','))].join('\r\n'), `priekskatijums-${resource.id}${yearSuffix}-${currentPage + 1}.csv`);}
    function selectYear(event) {
        const choice = event.target.value;
        if (choice === partition?.label) return;
        setSelectedYear(choice); setWorkbook(null); setLoading(true); setError('');
        setSheetIndex(0); setFilters({}); setPage(0); setQuery(''); setDraft(''); setX(''); setY('');
    }
    function selectReportSheet(event) {
        const choice = event.target.value;
        if (choice === reportSheet?.id) return;
        setSelectedReportSheet(choice); setWorkbook(null); setLoading(true); setError('');
        setSheetIndex(0); setFilters({}); setPage(0); setQuery(''); setDraft(''); setX(''); setY(''); setView('table');
    }
    return <section className="preview panel" aria-label="Resursa priekšskatījums">
        <div className="section-heading"><div><span className="eyebrow">{local ? `NO ${localFormat} SAGATAVOTA TABULA` : 'DATI NO AVOTA'}</span><h2>{resource.name || 'Tabulas priekšskatījums'}</h2></div></div>
        {jsonSource && resource.local_preview.snapshotFallback === true && <p className="notice" role="status"><strong>Rādīta pēdējā pieejamā pārbaudītā kopija.</strong> Valsts kases avotu atjaunošanas laikā nevarēja sasniegt. Kopijas dati pārbaudīti {new Date(resource.local_preview.sourceCheckedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika; kopija var nebūt aktuāla.</p>}
        {csvSource && resource.local_preview.snapshotFallback === true && <p className="notice" role="status"><strong>Rādīta pēdējā pārbaudītā CSV kopija.</strong> {resource.local_preview.snapshotFallbackReason === 'source-changed' ? 'Avota fails ir mainījies; jaunā versija jāpārbauda.' : 'Atjaunošanas laikā avots nebija sasniedzams.'}</p>}
        {annual && resource.local_preview.snapshotFallback === true && <p className="notice" role="status"><strong>Rādīta pēdējā pilnā pārskatu kopija.</strong> Atjaunošanas laikā neizdevās pārbaudīt visus 12 gada pārskatus. Kopija sagatavota {new Date(resource.local_preview.convertedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika.</p>}
        {reviewed && resource.local_preview.snapshotFallback === true && <p className="notice" role="status"><strong>Rādīta iepriekš pārbaudītā pārskata kopija.</strong> Jaunākais avots nav pieejams vai vēl nav pārbaudīts.</p>}
        {treasuryMulti && resource.local_preview.snapshotFallback === true && <p className="notice" role="status"><strong>Rādīta iepriekš pārbaudītā pārskata kopija.</strong> Jaunākais avots nav pieejams vai vēl nav pārbaudīts.</p>}
        {reportSheets?.length > 1 && <label className="sheet-select">{reportProfile ? 'Periods vai kodu vārdnīca' : 'Darblapa'}<select value={reportSheet.id} onChange={selectReportSheet} aria-describedby="report-sheet-note">{reportSheets.map((entry) => <option key={entry.id} value={entry.id}>{reportProfile ? reportPartLabel(entry) : entry.name} ({number(entry.total)} rindas)</option>)}</select></label>}
        {reportSheets?.length > 1 && <p className="caption" id="report-sheet-note">{reportProfile ? 'Ielādēts tikai atlasītais periods, gada plāna versijas vai EKK vārdnīca. Meklēšana, filtri un CSV darbojas izvēlētajā daļā.' : 'Meklēšana, filtri un CSV attiecas tikai uz izvēlēto darblapu.'} EKK ir kodu vārdnīca, nevis finanšu datu rindas.</p>}
        {reportProfile === COMPENSATION && <p className="caption"><strong>Gada plānus nesummē pa mēnešiem.</strong> Plāna sadaļā atlasi konkrētu versiju pēc datuma. Faktiskie izdevumi ir atsevišķos mēnešos.</p>}
        {partition && <label className="sheet-select">Gads<select value={partition.label} onChange={selectYear} aria-describedby="preview-year-scope">{partitions.map(({label, total}) => <option key={label} value={label}>{label} ({number(total)} rindas)</option>)}</select></label>}
        {partition && <p className="caption" id="preview-year-scope">Lai ielādētu mazāk datu, vienlaikus atvērts tikai viens gads. Meklēšana, filtri un CSV attiecas uz izvēlēto gadu; vairāku gadu dati netiek apvienoti.</p>}
        {local && workbook && <>
            <p className="caption">{localFormat} avota kopija sagatavota {new Date(workbook.convertedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika. Avota rindas nav summētas.</p>
            {csvSource && sheet?.sourceCaption && <p className="caption">{sheet.sourceCaption}</p>}
            {!treasuryMulti && ((!jsonSource && !csvSource) || workbook.sheets.length > 1) && <label className="sheet-select">{jsonSource ? 'Tabula' : 'Darblapa'}<select value={sheetIndex} onChange={(e) => {setSheetIndex(Number(e.target.value)); setPage(0); setFilters({}); setX(''); setY('');}}>{workbook.sheets.map((s, i) => <option key={i} value={i}>{s.name} ({number(s.total)} rindas)</option>)}</select></label>}
            {options.length > 0 && <div className="xlsx-filter-panel"><h3>Atlasīt datus</h3>{mainOptions.length > 0 && <div className="xlsx-filters">{mainOptions.map(renderFilter)}</div>}
                {advancedOptions.length > 0 && <details className="advanced-filters"><summary>Papildu filtri{advancedOptions.some(({field}) => filters[field]) ? ' · ir aktīvi filtri' : ''}</summary><div className="xlsx-filters">{advancedOptions.map(renderFilter)}</div></details>}
                <button className="text-button" onClick={() => {setFilters({}); setQuery(''); setDraft(''); setPage(0);}}>Notīrīt tabulas filtrus</button>
            </div>}
            <p className="caption">{csvSource ? (procurementCsv ? 'Pārbaudītas vēsturiskās iepirkumu kopsavilkuma rindas. Filtri, meklēšana un atlases CSV aptver visu tabulu; vērtības saglabātas tā, kā tās norādītas avotā.' : 'Meklēšana un atlases CSV aptver visu tabulu. Skaitļi, periodi un kodi saglabāti kā teksts tā, kā norādīts avotā.') : jsonSource ? `${partition ? '' : 'Filtri, meklēšana un atlases CSV aptver visu tabulu. '}“Gads” un “Summa” atbilst avota laukiem gads un vertiba. Summas attiecas uz tāmes izmaiņām, nevis faktisko budžeta izpildi.` : reportProfile === RAIM ? 'Pašvaldību saistību pārskati uz 31. decembri (2009–2025). Saglabātas avota summas un procentu vērtības; avota tabulā summu valūta nav norādīta.' : treasuryMulti ? (reportSheet.id === 'ekk' ? 'Avota EKK klasifikācijas kodu un nosaukumu vārdnīca.' : 'CSV saglabā avota summas EUR bez noapaļošanas; izklājlapu programma pēc atvēršanas var tās noapaļot. Klasifikācijas līmeņu kopsummas un detalizācija nav savstarpēji summējamas.') : annual ? 'Filtri, meklēšana un CSV aptver visu gada pārskatu. Avota Summa_EUR ir summa eiro. Pamatdati, konsolidācija, korekcijas un klasifikācijas kopsummas netiek automātiski saskaitītas.' : 'Filtri, meklēšana un atlases CSV aptver visu izvēlēto darblapu. “#” saglabāts tieši no avota. Rindās var būt plāns, izpilde un dažādu līmeņu kopsummas; tās netiek automātiski saskaitītas.'} Tukša vērtība nav nulle.</p>
            {reviewed && (cumulative ? <p className="caption"><strong>Kumulatīvais periods: 01.01.–28.02.2023.</strong> Finansēšanas gada plāns ar izmaiņām, ieņēmumi, izdevumi un finansēšana ir četras atsevišķas avota ailes; tās netiek saskaitītas vai noapaļotas. Šī tabula aptver pilnu XLSX, nevis nepilno DataStore priekšskatījumu.</p> : <p className="caption">Summas ir eiro. Klasifikācijas kopsummas un to detalizācijas rindas var pārklāties; portāls tās nesummē.</p>)}
            {reviewed && workbook.sourceSubtotal && <p className="notice"><strong>Atsevišķa avota kājenes vērtība: {number(workbook.sourceSubtotal.value)} EUR.</strong> Darblapas “{workbook.sourceSubtotal.sheet}” šūna {workbook.sourceSubtotal.cell}, saglabātā formulas {workbook.sourceSubtotal.formula} vērtība. Tā nav vēl viena datu rinda, netiek iekļauta atlasē vai CSV un nav uzskatāma par visu pašvaldību salīdzināmu izdevumu kopsummu.</p>}
            {sheet?.cachedFormulaCount > 0 && <p className="caption">Formulām izmantotas avota failā saglabātās vērtības; vietne formulas nepārrēķina.</p>}
        </>}
        <form className="row-search" onSubmit={(e) => {e.preventDefault(); setPage(0); setQuery(draft);}}><label className="sr-only" htmlFor="row-search">Meklēt tabulas ierakstos</label><input id="row-search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Meklēt tabulas ierakstos…"/><button className="button secondary">Meklēt ierakstos</button></form>
        {loading && <p role="status">{local ? 'Ielādē sagatavoto tabulu… Lielam failam tas var aizņemt brīdi.' : 'Ielādē tabulu no data.gov.lv…'}</p>}
        {error && <div role="alert" className="notice">{error} <button className="text-button" onClick={() => setRetry(retry + 1)}>Mēģināt vēlreiz</button></div>}
        {displayed && <>
            <div className="preview-toolbar"><p>{number(displayed.total)} ieraksti · šajā lapā {displayed.records.length}</p><div className="button-group"><button aria-pressed={view === 'table'} onClick={() => setView('table')}>Tabula</button>{!csvSource && !cumulative && !treasuryMulti && <button aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Diagramma</button>}<button onClick={exportRows}>Lejupielādēt šo lapu ↓</button>{local && <button disabled={!allRows.length} onClick={() => download(rowsCsv(sheet, allRows), `${procurementCsv ? 'iepirkumu-statistika' : csvSource ? 'atvertie-dati' : 'valsts-kase'}-${resource.id}${yearSuffix}-atlase.csv`)}>{partition ? 'Gada atlase CSV ↓' : reportProfile && reportProfile !== RAIM ? 'Izvēlētās daļas atlase CSV ↓' : 'Visa atlase CSV ↓'}</button>}</div></div>
            {view === 'table' ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Ritināma datu tabula"><table><thead><tr>{fields.map((f) => <th key={f.id} scope="col">{columnLabel(f.id)}</th>)}</tr></thead><tbody>{displayed.records.map((row, i) => <tr key={i}>{fields.map((f) => <td key={f.id}>{typeof row[f.id] === 'object' && row[f.id] !== null ? JSON.stringify(row[f.id]) : String(row[f.id] ?? '—')}</td>)}</tr>)}</tbody></table>{!displayed.records.length && <p>Nav atrastu ierakstu. Mainiet meklējumu.</p>}</div> : numericFields.length ? <>
                <div className="chart-selects"><label>Etiķetes<select value={xField} onChange={(e) => setX(e.target.value)}>{fields.map((f) => <option key={f.id} value={f.id}>{columnLabel(f.id)}</option>)}</select></label><label>Skaitliskā vērtība<select value={yField} onChange={(e) => setY(e.target.value)}>{numericFields.map((f) => <option key={f.id} value={f.id}>{columnLabel(f.id)}</option>)}</select></label></div>
                <p className="caption">Attēloti {points.length} no šīs lapas {displayed.records.length} ierakstiem, bez summēšanas. Tukšas un neskaitliskas vērtības izlaistas. {currencyField ? `Valūta norādīta kolonnā ${currencyField}.` : annual ? 'Vērtības ir eiro (EUR).' : 'Mērvienību pārbaudiet resursa aprakstā.'} {local && 'Vienādas etiķetes diagrammā netiek apvienotas.'}</p>
                <div className="bar-chart" aria-label={`${columnLabel(yField)} pēc ${columnLabel(xField)}`}>{points.map((p, i) => <div className="bar-row" key={i}><span title={p.label}>{p.label}</span><div className="bar-track"><i className="zero" style={{left: `${zero}%`}}/><i className={p.value < 0 ? 'bar negative' : 'bar'} style={{left: `${(Math.min(0, p.value) - low) / span * 100}%`, width: `${Math.abs(p.value) / span * 100}%`}}/></div><strong>{number(p.value)}</strong></div>)}</div>
            </> : <p className="notice">Šajā lapā nav diagrammai izmantojamu skaitlisku vērtību.</p>}
            <div className="pagination"><button disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>← Iepriekšējā</button><span>{currentPage + 1}. lapa · līdz 50 ierakstiem</span><button disabled={(currentPage + 1) * 50 >= displayed.total} onClick={() => setPage(currentPage + 1)}>Nākamā →</button></div>
        </>}
    </section>;
}

import React, {useEffect, useMemo, useState} from 'react';
import {ckan} from '../api.js';
import {csvCell, number, numeric} from '../data.js';
export function download(text, filename, type = 'text/csv;charset=utf-8') {const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);}
export default function Preview({resource}) {
    const [page, setPage] = useState(0), [query, setQuery] = useState(''), [draft, setDraft] = useState('');
    const [data, setData] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0);
    const [view, setView] = useState('table'), [x, setX] = useState(''), [y, setY] = useState('');
    useEffect(() => {const abort = new AbortController(); setLoading(true); setData(null); setError('');
        ckan('datastore_search', {resource_id: resource.id, limit: 50, offset: page * 50, ...(query ? {q: query} : {})}, abort.signal)
            .then((r) => {setData(r); setLoading(false);}).catch((e) => {if (e.name !== 'AbortError') {setError(e.message); setLoading(false);}});
        return () => abort.abort();
    }, [resource.id, page, query, retry]);
    const fields = data?.fields?.filter((f) => f.id !== '_id' && f.id !== '_full_text') || [];
    const numericFields = fields.filter((f) => data.records.some((r) => numeric(r[f.id]) !== null));
    const xField = fields.find((f) => f.id === x)?.id || fields[0]?.id;
    const yField = numericFields.find((f) => f.id === y)?.id || numericFields[0]?.id;
    const points = useMemo(() => (data?.records || []).map((r) => ({label: String(r[xField] ?? ''), value: numeric(r[yField])})).filter((p) => p.value !== null), [data, xField, yField]);
    const low = Math.min(0, ...points.map((p) => p.value)), high = Math.max(0, ...points.map((p) => p.value)), span = high - low || 1;
    const zero = -low / span * 100;
    function exportRows() {download('\uFEFF' + [fields.map((f) => f.id), ...data.records.map((r) => fields.map((f) => r[f.id]))].map((row) => row.map(csvCell).join(',')).join('\r\n'), `priekskatijums-${resource.id}-${page + 1}.csv`);}
    return <section className="preview panel" aria-label="Resursa priekšskatījums">
        <div className="section-heading"><div><span className="eyebrow">DATI NO AVOTA</span><h2>{resource.name || 'Tabulas priekšskatījums'}</h2></div></div>
        <form className="row-search" onSubmit={(e) => {e.preventDefault(); setPage(0); setQuery(draft);}}><label className="sr-only" htmlFor="row-search">Meklēt tabulas ierakstos</label><input id="row-search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Meklēt tabulas ierakstos…"/><button className="button secondary">Meklēt ierakstos</button></form>
        {loading && <p role="status">Ielādē tabulu no data.gov.lv…</p>}
        {error && <div role="alert" className="notice">{error} <button className="text-button" onClick={() => setRetry(retry + 1)}>Mēģināt vēlreiz</button></div>}
        {data && <>
            <div className="preview-toolbar"><p>{number(data.total)} ieraksti · šajā lapā {data.records.length}</p><div className="button-group"><button aria-pressed={view === 'table'} onClick={() => setView('table')}>Tabula</button><button aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Diagramma</button><button onClick={exportRows}>Lejupielādēt šo lapu ↓</button></div></div>
            {view === 'table' ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Ritināma datu tabula"><table><thead><tr>{fields.map((f) => <th key={f.id}>{f.id}</th>)}</tr></thead><tbody>{data.records.map((row, i) => <tr key={i}>{fields.map((f) => <td key={f.id}>{typeof row[f.id] === 'object' && row[f.id] !== null ? JSON.stringify(row[f.id]) : String(row[f.id] ?? '—')}</td>)}</tr>)}</tbody></table>{!data.records.length && <p>Nav atrastu ierakstu. Mainiet meklējumu.</p>}</div> : numericFields.length ? <>
                <div className="chart-selects"><label>Etiķetes<select value={xField} onChange={(e) => setX(e.target.value)}>{fields.map((f) => <option key={f.id}>{f.id}</option>)}</select></label><label>Skaitliskā vērtība<select value={yField} onChange={(e) => setY(e.target.value)}>{numericFields.map((f) => <option key={f.id}>{f.id}</option>)}</select></label></div>
                <p className="caption">Attēloti tikai šīs lapas {data.records.length} ieraksti, bez summēšanas. Tukšas un neskaitliskas vērtības izlaistas. Mērvienību pārbaudiet resursa aprakstā.</p>
                <div className="bar-chart" aria-label={`${yField} pēc ${xField}`}>{points.map((p, i) => <div className="bar-row" key={i}><span title={p.label}>{p.label}</span><div className="bar-track"><i className="zero" style={{left: `${zero}%`}}/><i className={p.value < 0 ? 'bar negative' : 'bar'} style={{left: `${(Math.min(0, p.value) - low) / span * 100}%`, width: `${Math.abs(p.value) / span * 100}%`}}/></div><strong>{number(p.value)}</strong></div>)}</div>
            </> : <p className="notice">Šajā lapā nav diagrammai izmantojamu skaitlisku vērtību.</p>}
            <div className="pagination"><button disabled={!page} onClick={() => setPage(page - 1)}>← Iepriekšējā</button><span>{page + 1}. lapa · līdz 50 ierakstiem</span><button disabled={(page + 1) * 50 >= data.total} onClick={() => setPage(page + 1)}>Nākamā →</button></div>
        </>}
    </section>;
}

import React, {useEffect, useMemo, useState} from 'react';
import {number} from '../data.js';
import {filterNotices, IUB_ORIGIN, noticeType, officialArchive, officialNotice, validateNoticeIndex} from '../iubNotices.js';

const PAGE_SIZE = 30;
const MAX_BYTES = 5 * 1024 * 1024;
const labelDate = (value) => value.split('-').reverse().join('.');
const roleLabels = {buyer: 'Pasūtītājs', 'cpb-acq': 'Centralizēto iepirkumu struktūra (iegāde)', 'cpb-awa': 'Centralizēto iepirkumu struktūra (līguma slēgšanas tiesības)'};

const linkAttrs = {target: '_blank', rel: 'noopener noreferrer'};

function initial(index) {return {from: index.from, to: index.to, buyer: '', query: ''};}

async function fetchIndex(signal) {
    const response = await fetch(`${import.meta.env.BASE_URL}data/iub-notices.json`, {signal, cache: 'no-cache'});
    if (!response.ok) throw new Error('IUB kopija nav pieejama.');
    const reader = response.body?.getReader();
    if (!reader) throw new Error('Neizdevās nolasīt IUB kopiju.');
    const decoder = new TextDecoder('utf-8', {fatal: true});
    let bytes = 0, text = '';
    try {
        for (;;) {
            const {done, value} = await reader.read();
            if (done) break;
            bytes += value.byteLength;
            if (bytes > MAX_BYTES) throw new Error('IUB kopija pārsniedz izmēra ierobežojumu.');
            text += decoder.decode(value, {stream: true});
        }
        return validateNoticeIndex(JSON.parse(text + decoder.decode()));
    } finally {
        try {await reader.cancel();} catch { /* Aborted requests no longer have a readable body. */ }
        reader.releaseLock();
    }
}

export default function IubNotices() {
    const [index, setIndex] = useState(null), [error, setError] = useState(false), [retry, setRetry] = useState(0);
    const [draft, setDraft] = useState(null), [active, setActive] = useState(null);
    const [badRange, setBadRange] = useState(false), [page, setPage] = useState(0);
    useEffect(() => {
        const controller = new AbortController();
        setError(false);
        fetchIndex(controller.signal).then((value) => {
            if (controller.signal.aborted) return;
            setIndex(value); setDraft(initial(value)); setActive(initial(value)); setPage(0);
        }).catch(() => {if (!controller.signal.aborted) setError(true);});
        return () => controller.abort();
    }, [retry]);
    const rows = useMemo(() => index && active ? filterNotices(index.notices, active) : [], [index, active]);
    const display = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    const stale = index && Date.now() - Date.parse(index.checkedAt) > 2 * 86400000;
    function apply(event) {
        event.preventDefault();
        if (!index.dates.includes(draft.from) || !index.dates.includes(draft.to) || draft.from > draft.to) {
            setBadRange(true);
            return;
        }
        setBadRange(false); setActive(draft); setPage(0);
    }
    function change(key, value) {setDraft({...draft, [key]: value}); setBadRange(false);}
    function clear() {setDraft(initial(index)); setActive(initial(index)); setPage(0); setBadRange(false);}
    return <section className="panel iub-notices" aria-labelledby="iub-notice-heading">
        <span className="eyebrow">IEPIRKUMU UZRAUDZĪBAS BIROJS · JSON</span>
        <h2 id="iub-notice-heading" tabIndex={-1}>Iepirkumu paziņojumu meklēšana</h2>
        <p>Atlasiet paziņojumus pēc publicēšanas dienas un pasūtītāja. Šis ir pēdējo 14 dienu izvilkums, nevis viss arhīvs vai līgumu reģistrs. <a className="text-link" href={IUB_ORIGIN} {...linkAttrs}>Pilnais IUB arhīvs ↗</a></p>
        {!index && !error && <p role="status">Ielādē IUB datu kopiju…</p>}
        {error && <p role="alert" className="notice">IUB datu kopiju neizdevās ielādēt. <button className="text-button" type="button" onClick={() => setRetry(retry + 1)}>Mēģināt vēlreiz</button></p>}
        {index && draft && <>
            <p className="data-stamp">Periods: <strong>{labelDate(index.from)} – {labelDate(index.to)}</strong> · Pārbaudīts {new Date(index.checkedAt).toLocaleString('lv-LV', {timeZone: 'Europe/Riga'})} pēc Latvijas laika.</p>
            {(index.standby || stale) && <p className="notice" role="status">Rādīta pēdējā pieejamā kopija. Jaunākos paziņojumus skatiet IUB arhīvā.</p>}
            <form className="iub-notice-filters" onSubmit={apply}>
                <label>No datuma<input type="date" min={index.from} max={index.to} required value={draft.from} onChange={(e) => change('from', e.target.value)}/></label>
                <label>Līdz datumam<input type="date" min={index.from} max={index.to} required value={draft.to} onChange={(e) => change('to', e.target.value)}/></label>
                <label>Pasūtītājs<input type="search" value={draft.buyer} maxLength={120} placeholder="Piem., Rīgas dome" onChange={(e) => change('buyer', e.target.value)}/></label>
                <label>CPV kods, veids vai paziņojuma ID<input type="search" value={draft.query} maxLength={100} onChange={(e) => change('query', e.target.value)}/></label>
                <div className="iub-notice-actions"><button className="button" type="submit">Meklēt paziņojumus</button><button className="button secondary" type="button" onClick={clear}>Notīrīt filtrus</button></div>
            </form>
            {badRange && <p className="notice" role="alert">Izvēlieties sākuma un beigu datumu norādītajā periodā. Sākuma datumam jābūt pirms beigu datuma vai tajā pašā dienā.</p>}
            <p className="caption">Datums norādīts pēc IUB dienas datnes. Nosaukumu rāda tikai pārbaudāma tipa Latvijas juridiskajiem pasūtītājiem. Paziņojumi nav iepirkumu vai līgumu skaits: vienam iepirkumam var būt vairāki paziņojumi.</p>
            <p className="caption">Versijas saglabātas. Ja jaunāka versija atrasta šajās datnēs, vecā ir atzīmēta. Ārpus perioda publicētas versijas šeit nav pārbaudāmas.</p>
            <p role="status" className="iub-notice-count"><strong>{number(rows.length)}</strong> paziņojumi atlasē{active.buyer ? ` · Pasūtītājs: ${active.buyer}` : ''}</p>
            {display.length ? <>
                <div className="table-scroll iub-notice-scroll" role="region" tabIndex={0} aria-label="IUB paziņojumu rezultātu tabula">
                    <table><thead><tr>{['Datums','Pasūtītājs / organizācija','Paziņojuma veids','CPV kods','IUB avots'].map((name) => <th scope="col" key={name}>{name}</th>)}</tr></thead>
                        <tbody>{display.map((r) => <tr key={r.id}>
                            <td>{labelDate(r.date)}</td>
                            <td>{r.buyer ?? 'Nav parādīts'}{r.role && <small>{roleLabels[r.role]}</small>}</td>
                            <td>{noticeType(r.type)}
                                {r.supersededHere && <small>Jaunāka versija atrasta šajā izvilkumā.</small>}
                                {r.predecessor && <small>{r.predecessorHere ? 'Atkārtoti publicēts.' : 'Iepriekšējā versija nav šajā izvilkumā.'} <a href={officialNotice(r.predecessor)} {...linkAttrs}>Iepriekšējā versija ↗</a></small>}</td>
                            <td>{r.cpv ?? 'Nav norādīts'}</td>
                            <td><a className="text-link" aria-label={`Atvērt IUB paziņojumu ${r.id}`} href={officialNotice(r.id)} {...linkAttrs}>Paziņojums ↗</a><small className="iub-notice-id">{r.id}</small><small><a href={officialArchive(r.date)} {...linkAttrs}>Dienas JSON ↗</a></small></td>
                        </tr>)}</tbody></table>
                </div>
                <div className="pagination"><button type="button" disabled={!page} onClick={() => setPage(page - 1)}>← Iepriekšējā</button><span>{page + 1} / {Math.ceil(rows.length / PAGE_SIZE)}</span><button type="button" disabled={(page + 1) * PAGE_SIZE >= rows.length} onClick={() => setPage(page + 1)}>Nākamā →</button></div>
            </> : <p>Šajā atlasē paziņojumi nav atrasti. Mainiet filtrus vai meklējiet pilnajā IUB arhīvā.</p>}
        </>}
    </section>;
}

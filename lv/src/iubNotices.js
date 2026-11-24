import {normalize} from './data.js';

export const IUB_DATASET = '26b07f9b-3442-4bb7-9016-75a904e32776';
const IUB_RESOURCE = '4c976f80-a82d-4378-a773-fe939ee6c795';
export const IUB_ORIGIN = 'https://open.iub.gov.lv/data/notice';
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const TYPE = /^[a-z][a-z0-9-]{0,59}$/;
const CPV = /^[0-9]{8}-[0-9]$/;
const DAY = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const HASH = /^[0-9a-f]{64}$/;
const NAME = /^[\p{L}\p{M}\p{N}_ \-.,()&/\\"«»„“”’'–:]{1,180}$/u;
const BUYER_ROLES = new Set(['buyer', 'cpb-acq', 'cpb-awa']);
const knownTypes = new Map([
    ['contract-execution','Līguma izpilde'], ['contract-modification','Līguma grozījumi'],
    ['pil-contract','PIL: iepirkuma izsludināšana'], ['pil-award','PIL: iepirkuma rezultāti'],
    ['pil-concluded-contract','PIL: noslēgts līgums'], ['pil-planned-contract','PIL: plānots iepirkums'],
    ['pil-discussion','PIL: apspriede ar piegādātājiem'],
    ['pil-prior-information','PIL: iepriekšēja informācija'],
    ['sps-iv-contract','SPSIL: iepirkuma izsludināšana (IV)'],
    ['sps-iv-result','SPSIL: iepirkuma rezultāti (IV)'],
    ['sps-contract','SPSIL: iepirkuma izsludināšana'], ['sps-award','SPSIL: iepirkuma rezultāti'],
    ['mk-contract','Pasūtītāja finansēts projekts: izsludināšana'],
    ['mk-result','Pasūtītāja finansēts projekts: rezultāti'],
]);

export const noticeType = (value) => knownTypes.get(value) ?? `IUB kods: ${value}`;
export const isIubNoticeResource = (r) => r?.id === IUB_RESOURCE && r.url === IUB_ORIGIN && r.format === 'JSON';
export function isIubNoticeDataset(dataset) {
    return dataset?.id === IUB_DATASET && dataset.organization?.name === 'iub' &&
        ['CC0-1.0', 'cc-zero'].includes(dataset.license_id) &&
        dataset.resources?.some(isIubNoticeResource);
}

function exact(re, value) {
    return typeof value === 'string' && re.exec(value)?.[0] === value;
}

function checkedDate(value) {
    if (!exact(DAY, value)) return null;
    const d = new Date(value + 'T00:00:00.000Z');
    return Number.isFinite(+d) && d.toISOString().slice(0, 10) === value ? d : null;
}

export function officialNotice(id) {
    return exact(UUID, id) ? `https://eformsb.pvs.iub.gov.lv/show/${id}` : null;
}

export function officialArchive(day) {
    if (!checkedDate(day)) return null;
    const [y, m, d] = day.split('-');
    return `${IUB_ORIGIN}/${y}/${m}/${d}-${m}-${y}.json`;
}

function buyerValid(s) {
    return exact(NAME, s) && s.trim() === s && /\p{L}/u.test(s) &&
        !/[0-9]{6}|[0-9]{4}-[0-9]{5}|https?[:/]|www\./i.test(s);
}

export function validateNoticeIndex(obj) {
    const fail = () => {throw new Error('IUB datu kopija nav derīga.');};
    if (!obj || typeof obj !== 'object' || Object.keys(obj).length !== 4 || obj.schemaVersion !== 1 ||
            typeof obj.standby !== 'boolean' || typeof obj.checkedAt !== 'string' ||
            !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(obj.checkedAt) ||
            !Number.isFinite(Date.parse(obj.checkedAt)) || !Array.isArray(obj.days) || obj.days.length !== 14) fail();
    const riga = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Riga', year:'numeric',
        month:'2-digit', day:'2-digit', hour:'2-digit', hourCycle:'h23'})
        .formatToParts(new Date(obj.checkedAt)).map(({type,value})=>[type,value]));
    const expectedEnd = checkedDate(`${riga.year}-${riga.month}-${riga.day}`);
    expectedEnd.setUTCDate(expectedEnd.getUTCDate() - (Number(riga.hour) >= 4 ? 1 : 2));
    let previousDay;
    const byId = new Map(), replaced = new Set();
    const notices = [];
    for (const bucket of obj.days) {
        if (!bucket || typeof bucket !== 'object' || Object.keys(bucket).length !== 3 ||
                !exact(HASH, bucket.sourceSha256) || !Array.isArray(bucket.rows) || bucket.rows.length > 1500) fail();
        const day = checkedDate(bucket.date);
        if (!day || (previousDay && +day - +previousDay !== 86400000)) fail();
        previousDay = day;
        for (const row of bucket.rows) {
            if (!Array.isArray(row) || row.length !== 6) fail();
            const [id, type, cpv, buyer, role, predecessor] = row;
            if (!exact(UUID, id) || byId.has(id) || !exact(TYPE, type) || (cpv !== null && !exact(CPV, cpv)) ||
                    (buyer === null ? role !== null : !buyerValid(buyer) || !BUYER_ROLES.has(role)) ||
                    (predecessor !== null && (!exact(UUID, predecessor) || predecessor === id))) fail();
            const notice = {id, type, cpv, buyer, role, predecessor, date: bucket.date};
            notices.push(notice);
            byId.set(id, notice);
        }
    }
    if (+previousDay !== +expectedEnd) fail();
    const visited = new Set();
    for (const {id, type, date, predecessor} of notices) {
        if (byId.has(predecessor)) {
            const old = byId.get(predecessor);
            if (old.date > date || old.type !== type) fail();
            replaced.add(predecessor);
        }
        const seen = new Set();
        for (let next = id; byId.has(next) && !visited.has(next); next = byId.get(next).predecessor) {
            if (seen.has(next)) fail();
            seen.add(next);
        }
        for (const notice of seen) visited.add(notice);
    }
    return {from: obj.days[0].date, to: obj.days.at(-1).date, dates: obj.days.map((d) => d.date),
        checkedAt: obj.checkedAt, standby: obj.standby, notices: notices.reverse().map((row) => ({
            ...row, supersededHere: replaced.has(row.id), predecessorHere: byId.has(row.predecessor) }))};
}

export function filterNotices(notices, {from, to, buyer, query}) {
    const terms = (value) => normalize(value).split(/\s+/).filter(Boolean);
    const nameTerms = terms(buyer);
    const q = terms(query);
    return notices.filter((r) => r.date >= from && r.date <= to &&
        nameTerms.every((term) => normalize(r.buyer).includes(term)) &&
        q.every((term) => normalize([r.id, r.cpv, r.type, noticeType(r.type)].join(' ')).includes(term)));
}

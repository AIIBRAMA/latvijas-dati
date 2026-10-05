// CKAN officially supports JSONP for public GET actions. Only this fixed trusted
// government origin may execute a response. No API keys or arbitrary URLs.
const BASE = 'https://data.gov.lv/dati/api/3/action/';
const ALLOWED = new Set(['package_show', 'datastore_search']);
let sequence = 0;
export function ckan(action, params = {}, signal) {
    if (!ALLOWED.has(action)) return Promise.reject(new Error('Neatļauts datu pieprasījums.'));
    return new Promise((resolve, reject) => {
        if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'));
        const callback = `lvCkan_${Date.now()}_${sequence++}`;
        const url = new URL(BASE + action);
        for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
        url.searchParams.set('callback', callback);
        const script = document.createElement('script');
        let settled = false;
        const cleanup = () => {
            settled = true; clearTimeout(timer); script.remove();
            signal?.removeEventListener('abort', abort);
            // A timed-out network response may still arrive. Keep a harmless tombstone.
            window[callback] = () => {};
            setTimeout(() => {delete window[callback];}, 60000);
        };
        const abort = () => {if (!settled) {cleanup(); reject(new DOMException('Aborted', 'AbortError'));}};
        const timer = setTimeout(() => {if (!settled) {cleanup(); reject(new Error('Datu avots neatbildēja 25 sekundēs. Mēģiniet vēlreiz vai atveriet avota lapu.'));}}, 25000);
        window[callback] = (payload) => {
            if (settled) return;
            cleanup();
            if (!payload?.success) reject(new Error('Avots nevarēja izpildīt pieprasījumu. Resurss var nebūt pieejams tabulas skatā.'));
            else resolve(payload.result);
        };
        script.onerror = () => {if (!settled) {cleanup(); reject(new Error('Neizdevās sazināties ar data.gov.lv. Pārbaudiet savienojumu un mēģiniet vēlreiz.'));}};
        signal?.addEventListener('abort', abort, {once: true});
        script.src = url.href;
        script.referrerPolicy = 'no-referrer';
        document.head.append(script);
    });
}

const PRODUCT = /^https:\/\/geolatvija\.lv\/main\?geoProductId=([1-9][0-9]{0,5})$/;

function exactProductId(value) {
    if (typeof value !== 'string') return null;
    const match = PRODUCT.exec(value);
    // "$" may match before a final line terminator; only the entire input is valid.
    return match?.[0] === value ? match[1] : null;
}

/** Recognize only the catalogue publisher's explicit, unambiguous official link. */
export function geoLatvijaProductUrl(dataset) {
    if (dataset?.organization?.name !== 'geoprodukti') return null;
    const ids = new Set();
    const add = (candidate) => {
        const id = exactProductId(candidate);
        if (id) ids.add(id);
    };
    // Metadata descriptions are plain untrusted text. Inspect only whole
    // whitespace-separated tokens, optionally enclosed in balanced parentheses.
    // This deliberately excludes HTML, snippets inside another URL, and query
    // or fragment suffixes. We never return the supplied string.
    if (typeof dataset.notes === 'string') {
        for (const token of dataset.notes.split(/\s+/u)) {
            add(token.startsWith('(') && token.endsWith(')') ? token.slice(1, -1) : token);
            if (ids.size > 1) return null;
        }
    }
    add(dataset.url);
    if (Array.isArray(dataset.resources)) {
        for (const resource of dataset.resources) {
            add(resource?.url);
            if (ids.size > 1) return null;
        }
    }
    return ids.size === 1 ? `https://geolatvija.lv/main?geoProductId=${[...ids][0]}` : null;
}

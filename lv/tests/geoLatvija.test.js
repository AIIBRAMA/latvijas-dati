import test from 'node:test';
import assert from 'node:assert/strict';
import {geoLatvijaProductUrl} from '../src/geoLatvija.js';
import {hasPreview} from '../src/data.js';

const A = 'https://geolatvija.lv/main?geoProductId=121';
const B = 'https://geolatvija.lv/main?geoProductId=98';
const make = (notes, links = [], url = null) => ({organization: {name:'geoprodukti'},
    notes, url, resources: links.map((url) => ({url, format:'WMS', datastore_active:false}))});

test('accept one exact official product from notes or a resource; not a table', () => {
    const known = make(`Apskatāms kartes avotā (${A})`, [A, 'https://geolatvija.lv']);
    assert.equal(geoLatvijaProductUrl(known), A);
    assert.equal(geoLatvijaProductUrl(make('Saite nav norādīta', [A])), A);
    assert.equal(geoLatvijaProductUrl(make(null, [], A)), A);
    assert.equal(known.resources.some(hasPreview), false);
});
test('return no direct product if unlisted, ambiguous, or from a different publisher', () => {
    assert.equal(geoLatvijaProductUrl(make('Tikai apraksts', ['https://geolatvija.lv'])), null);
    assert.equal(geoLatvijaProductUrl(make(`Karte (${A}) un ${B}`, [A])), null);
    assert.equal(geoLatvijaProductUrl(make(`Karte (${A})`, [B])), null);
    assert.equal(geoLatvijaProductUrl(make(A,[A],B)), null);
    assert.equal(geoLatvijaProductUrl({...make(A), organization: {name:'citadatuvieta'}}), null);
});
test('reject protocol, lookalike host, credentials, arbitrary path, query, fragment, code and nested URLs', () => {
    const bad = [
       'http://geolatvija.lv/main?geoProductId=121',
       'https://geolatvija.lv.evil.test/main?geoProductId=121',
       'https://evil.test@geolatvija.lv/main?geoProductId=121',
       'https://geolatvija.lv@evil.test/main?geoProductId=121',
       'https://geolatvija.lv:443/main?geoProductId=121',
       'https://geolatvija.lv/alias/../main?geoProductId=121',
       'https://geolatvija.lv/main/?geoProductId=121',
       'https://geolatvija.lv/main?geoproductid=121',
       'https://geolatvija.lv/main?geoProductId=0',
       'https://geolatvija.lv/main?geoProductId=0121',
       'https://geolatvija.lv/main?geoProductId=%31%32%31',
       'https://geolatvija.lv/main?geoProductId=1234567',
       `${A}&geoProductId=2`, `${A}&next=somewhere`, `${A}#section`,
       `https://evil.test/?next=(${A})`, `javascript:jump('${A}')`, `<a href="${A}">external</a>`,
    ];
    for (const value of bad) {
        assert.equal(geoLatvijaProductUrl(make(value, [value])), null, value);
    }
    assert.equal(geoLatvijaProductUrl(make(null, [A + '\n'])), null);
    assert.equal(geoLatvijaProductUrl(make(null, ['  ' + A])), null);
});

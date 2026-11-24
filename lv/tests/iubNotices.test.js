import test from 'node:test';
import assert from 'node:assert/strict';
import {filterNotices, IUB_DATASET, isIubNoticeDataset, officialNotice, officialArchive, validateNoticeIndex} from '../src/iubNotices.js';
const ids = ['5a0da6b9-b0ec-495a-872f-13036c160007','b4cd9a9b-b87b-4920-b00b-37320d90de07','28814fb2-de71-4264-8dd2-d3edc325b3a9'];
function sample() {
    return {schemaVersion: 1, checkedAt: '2026-11-24T03:30:00+00:00', standby:false,
        days: Array.from({length:14}, (_, i) => ({date:`2026-11-${i + 10}`,sourceSha256:'0'.repeat(64),rows: i === 0 ? [[ids[0],'pil-contract','12345678-0','Rīgas dome','buyer',null]] : i === 13 ? [[ids[1],'pil-contract','12345678-0','Rīgas dome','buyer',ids[0]],[ids[2],'mk-result',null,null,null,null]] : []}))};
}

test('full window remains when narrowing filters and predecessor assessment does not change by pagination/filter', () => {
    const s = validateNoticeIndex(sample());
    const list = filterNotices(s.notices,{from:s.from,to:s.to,buyer:'rIGAS DoME',query:'12345678'});
    assert.equal(list.length,2);
    assert.equal(list[1].supersededHere,true);
    assert.equal(list[0].predecessorHere,true);
    assert.deepEqual(filterNotices(s.notices,{from:s.from,to:s.from,buyer:'rigas',query:'izsludināšana'}),[list[1]]);
    assert.equal(officialNotice(list[0].id),`https://eformsb.pvs.iub.gov.lv/show/${ids[1]}`);
    assert.equal(officialArchive(s.to),'https://open.iub.gov.lv/data/notice/2026/11/23-11-2026.json');
    assert.equal(officialNotice(ids[0] + '\n'),null);
    assert.equal(officialArchive('2026-11-31'),null);
});

test('missing day, duplicate IDs, untrusted names and impossible historical links refuse index', () => {
    for (const tamper of [
        (p) => p.days.pop(), (p) => p.days[4].date = '2026-11-15', (p) => p.days.at(-1).rows[0][0] = ids[0],
        (p) => p.days[0].rows[0][3] = 'Person Name: secret@example.com',
        (p) => p.days[0].rows[0][3] = 'Person Name 000000-00000',
        (p) => p.days[0].rows[0][3] = '<script>',
        (p) => p.days[0].rows[0][5] = ids[1], (p) => p.days[0].rows[0][4] = 'supplier',
        (p) => p.days[0].rows[0][6] = ['private'],
        (p) => p.days[0].sourceSha256 = 'https://outside.invalid'
    ]) {const p = sample();tamper(p);assert.throws(() => validateNoticeIndex(p));}
});

test('only exact official notice publication resource gets the dedicated view', () => {
    const d={id:IUB_DATASET, organization:{name:'iub'}, license_id:'CC0-1.0',
        resources:[{id:'4c976f80-a82d-4378-a773-fe939ee6c795',url:'https://open.iub.gov.lv/data/notice',format:'JSON'}]};
    assert.equal(isIubNoticeDataset(d), true);
    assert.equal(isIubNoticeDataset({...d,organization:{name:'other'}}), false);
    assert.equal(isIubNoticeDataset({...d,license_id:'other'}), false);
    assert.equal(isIubNoticeDataset({...d,id:'wrong'}), false);
    assert.equal(isIubNoticeDataset({...d,resources:[{...d.resources[0],url:'https://open.iub.gov.lv.not-iub.test/data/notice'}]}), false);
});

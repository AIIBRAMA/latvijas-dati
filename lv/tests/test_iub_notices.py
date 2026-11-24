import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sync_iub_notices import ASSET, day_url, local_window, project, sync, validate_index

ID1 = '5a0da6b9-b0ec-495a-872f-13036c160007'
ID2 = 'b4cd9a9b-b87b-4920-b00b-37320d90de07'
NOW = datetime.fromisoformat('2026-11-24T03:30:00+00:00')
ORG = {'role': 'buyer', 'classification': 'gov', 'personType': 'legal', 'naturalPerson': None,
       'countryCode': 'LVA', 'identifier': '90000000000', 'name': 'Rīgas dome'}


def raw(uid=ID1, clone=None, org=ORG, cpv=''):
    return json.dumps([{'identifier': uid, 'noticeType': 'pil-contract', 'clonedFrom': clone,
                        'organizationData': org, 'cpvType': cpv,
                        'name': 'PRIVATE TEST SENTINEL',
                        'contactPoint': {'electronicMail': 'secret@example.com'}}]).encode()


class IubNotices(unittest.TestCase):
    def test_pii_projection_and_safe_publication_revision(self):
        clone = {'identifier': ID1, 'organizationData': {'name': 'Private data'}}
        self.assertEqual(project(raw(ID2, clone)), [[ID2, 'pil-contract', None, 'Rīgas dome', 'buyer', ID1]])
        for changes in ({'role': None}, {'personType': 'natural'}, {'naturalPerson': ''},
                        {'identifier': 'abc'}, {'name': 'Nosaukums secret@example.com'},
                        {'name': 'Nosaukums 120398-12345'}, {'name': 'Rīga\nVārds'}, {'role': []}):
            self.assertEqual(project(raw(org={**ORG, **changes}))[0][3:5], [None, None])
        with self.assertRaises(ValueError):
            project(raw(ID1, {'identifier': ID1}))
        with self.assertRaises(ValueError):
            project(raw(cpv='00000000'))
        self.assertEqual(project(b'[]'), [])

    def test_date_boundary_and_source_path(self):
        early = datetime.fromisoformat('2026-12-01T01:59:59Z')
        late = datetime.fromisoformat('2026-12-01T02:00:00Z')
        self.assertEqual(local_window(early)[-1].isoformat(), '2026-11-29')
        self.assertEqual(local_window(late)[-1].isoformat(), '2026-11-30')
        self.assertEqual(day_url(local_window(late)[-1]), 'https://open.iub.gov.lv/data/notice/2026/11/30-11-2026.json')

    def test_entrypoint_publishes_full_window_and_switches_only_after_complete(self):
        oldest, *_, latest = local_window(NOW)
        read = lambda d: raw() if d == oldest else raw(ID2, {'identifier': ID1}) if d == latest else b'[]'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'public' / ASSET
            x = sync(root, NOW, read)
            self.assertEqual(sum(len(s['rows']) for s in x['days']), 2)
            self.assertEqual(x['days'][-1]['rows'][0][-1], ID1)
            self.assertNotIn(b'PRIVATE TEST SENTINEL', out.read_bytes())
            self.assertNotIn(b'secret@example.com', out.read_bytes())
            self.assertNotIn(b'90000000000', out.read_bytes())
            prior = out.read_bytes()
            later = datetime.fromisoformat('2026-11-25T08:00:00+00:00')
            def duplicate(_): return raw()
            with self.assertRaises(ValueError):
                sync(root, later, duplicate)
            self.assertEqual(out.read_bytes(), prior)
            y = sync(root, later, duplicate, allow_standby=True)
            self.assertTrue(y['standby'])
            self.assertEqual(y['checkedAt'], NOW.isoformat())
            self.assertEqual(y['days'], x['days'])
            self.assertEqual(validate_index(out.read_bytes()), y)
            self.assertIsNone(sync(root / 'empty', later, duplicate,
                                   allow_standby=True, standby_read=lambda *_: b'{}'))

    def test_cycle_refused(self):
        same_date = [json.loads(raw(ID1, {'identifier': ID2}))[0],
                     json.loads(raw(ID2, {'identifier': ID1}))[0]]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                sync(Path(tmp), NOW, lambda d: json.dumps(same_date).encode() if d == local_window(NOW)[-1] else b'[]')


if __name__ == '__main__':
    unittest.main()

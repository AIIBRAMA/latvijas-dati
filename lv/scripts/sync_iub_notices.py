"""Create a 14-day IUB notice index. Never publish or log the raw notices."""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from budget_estimate_fallback import fetch_pages
from publish_budget_estimates import atomic_bytes

ORIGIN = 'https://open.iub.gov.lv'
ROOT = Path(__file__).resolve().parents[1]
ASSET = 'data/iub-notices.json'
DAYS = 14
MAX_DAY_BYTES = 16 * 1024 * 1024
MAX_INDEX_BYTES = 5 * 1024 * 1024
MAX_DAY_ROWS = 1500
RIGA = ZoneInfo('Europe/Riga')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
CPV = re.compile(r'[0-9]{8}-[0-9]')
TYPE = re.compile(r'[a-z][a-z0-9-]{0,59}')
HASH = re.compile(r'[0-9a-f]{64}')
BUYER_ROLES = {'buyer', 'cpb-acq', 'cpb-awa'}
NAME = re.compile(r'[\w \-.,()&/\\\"«»„“”’\'–:]{1,180}')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def day_url(day):
    return f'{ORIGIN}/data/notice/{day:%Y/%m/%d-%m-%Y}.json'


def download(day):
    url = day_url(day)
    req = urllib.request.Request(url, headers={'User-Agent': 'LatvijasDatiExplorer/1.1'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=18) as r:
        if r.status != 200 or r.geturl() != url or r.headers.get_content_type() != 'application/json':
            raise ValueError('Unexpected IUB response')
        return r.read(MAX_DAY_BYTES + 1)


def reviewed_buyer(label):
    # Don't publish individual-contact fields, identifiers, or suspicious textual labels.
    return (isinstance(label, str) and label.strip() == label and NAME.fullmatch(label)
            and any(c.isalpha() for c in label)
            and not re.search(r'[0-9]{6}|[0-9]{4}-[0-9]{5}|https?[:/]|www\.', label, re.I))


def buyer(record):
    org = record.get('organizationData')
    if not isinstance(org, dict):
        return None, None
    role = org.get('role')
    label = org.get('name')
    registration = org.get('identifier')
    if (isinstance(role, str) and role in BUYER_ROLES and org.get('classification') == 'gov' and
            org.get('personType') == 'legal' and org.get('countryCode') == 'LVA' and
            'naturalPerson' in org and org['naturalPerson'] is None and
            isinstance(registration, str) and re.fullmatch(r'[0-9]{11}', registration) and
            reviewed_buyer(label)):
        return label, role
    return None, None


def is_match(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def project(raw):
    if len(raw) > MAX_DAY_BYTES:
        raise ValueError('IUB daily input too large')
    value = json.loads(raw)
    if not isinstance(value, list) or len(value) > MAX_DAY_ROWS:
        raise ValueError('Unexpected IUB daily input shape or size')
    rows = []
    for record in value:
        if not isinstance(record, dict) or not {'identifier', 'noticeType', 'cpvType', 'clonedFrom', 'organizationData'} <= record.keys():
            raise ValueError('Missing expected IUB notice fields')
        uid, notice_type, cpv = (record[k] for k in ('identifier', 'noticeType', 'cpvType'))
        cpv = None if cpv == '' else cpv
        raw_clone = record['clonedFrom']
        pred = raw_clone.get('identifier') if isinstance(raw_clone, dict) else None
        if (not is_match(UUID, uid) or not is_match(TYPE, notice_type) or
                (cpv is not None and not is_match(CPV, cpv)) or
                (raw_clone is not None and (not is_match(UUID, pred) or pred == uid))):
            raise ValueError('Invalid IUB notice identity, type, CPV or predecessor')
        name, role = buyer(record)
        rows.append([uid, notice_type, cpv, name, role, pred])
    return rows


def local_window(now):
    riga = now.astimezone(RIGA)
    end = riga.date() - timedelta(days=1 if riga.hour >= 4 else 2)
    return [end - timedelta(days=offset) for offset in range(DAYS - 1, -1, -1)]


def day_index(day, read):
    raw = read(day)
    return {'date': day.isoformat(), 'sourceSha256': hashlib.sha256(raw).hexdigest(), 'rows': project(raw)}


def validate_rows(days):
    ids = {}
    for day in days:
        for row in day['rows']:
            if not isinstance(row, list) or len(row) != 6:
                raise ValueError('Invalid IUB published row')
            uid, notice_type, cpv, name, role, pred = row
            if (not is_match(UUID, uid) or uid in ids or not is_match(TYPE, notice_type) or
                    (cpv is not None and not is_match(CPV, cpv)) or
                    (name is None and role is not None) or
                    (name is not None and (role not in BUYER_ROLES or not reviewed_buyer(name))) or
                    (pred is not None and (not is_match(UUID, pred) or pred == uid))):
                raise ValueError('Invalid or duplicate IUB published row')
            ids[uid] = (day['date'], notice_type, pred)
    for _, (day, kind, pred) in ids.items():
        if pred in ids:
            older_day, older_kind, _ = ids[pred]
            if older_day > day or older_kind != kind:
                raise ValueError('Conflicting IUB predecessor in window')
    # Follow each linkage at most once, rejecting any same-day cycle.
    done = set()
    for uid in ids:
        seen = set()
        while uid in ids and uid not in done:
            if uid in seen:
                raise ValueError('Cyclic IUB notice versions')
            seen.add(uid)
            uid = ids[uid][2]
        done.update(seen)


def validate_index(raw):
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError('IUB index too large')
    obj = json.loads(raw)
    if not isinstance(obj, dict) or set(obj) != {'schemaVersion', 'checkedAt', 'days', 'standby'}:
        raise ValueError('Unexpected IUB index shape')
    if type(obj['schemaVersion']) is not int or obj['schemaVersion'] != 1 or type(obj['standby']) is not bool:
        raise ValueError('Unsupported IUB index version')
    checked = datetime.fromisoformat(obj['checkedAt'])
    if checked.tzinfo is None:
        raise ValueError('Expected timezone on IUB verification timestamp')
    days = obj['days']
    if not isinstance(days, list) or len(days) != DAYS:
        raise ValueError('IUB day range is not complete')
    for entry, expected in zip(days, local_window(checked)):
        if (not isinstance(entry, dict) or set(entry) != {'date', 'sourceSha256', 'rows'} or
                entry['date'] != expected.isoformat() or not is_match(HASH, entry['sourceSha256']) or
                not isinstance(entry['rows'], list) or len(entry['rows']) > MAX_DAY_ROWS):
            raise ValueError('Invalid IUB day or non-contiguous window')
    validate_rows(days)
    return obj


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def sync(root, now, read=download, *, allow_standby=False, standby_read=fetch_pages):
    out = root / 'public' / ASSET
    try:
        with ThreadPoolExecutor(6) as pool:
            days = list(pool.map(lambda day: day_index(day, read), local_window(now)))
        raw = encode({'schemaVersion': 1, 'checkedAt': now.isoformat(), 'standby': False, 'days': days})
        obj = validate_index(raw)
    except (OSError, ValueError, TypeError, RecursionError, RuntimeError):
        if not allow_standby:
            raise
        try:
            raw = out.read_bytes() if out.is_file() else standby_read(ASSET, MAX_INDEX_BYTES)
            obj = validate_index(raw)
            obj['standby'] = True
            raw = encode(obj)
        except (OSError, ValueError, TypeError, RecursionError, RuntimeError):
            print('IUB index unavailable; leaving the other portal data unchanged', file=sys.stderr, flush=True)
            return None
    atomic_bytes(out, raw)
    print(f"IUB {obj['days'][0]['date']} through {obj['days'][-1]['date']}: "
          f"{sum(len(day['rows']) for day in obj['days'])} notices; standby={obj['standby']}", flush=True)
    return obj


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allow-standby', action='store_true')
    args = p.parse_args()
    sync(ROOT, datetime.now(timezone.utc), allow_standby=args.allow_standby)


if __name__ == '__main__':
    main()

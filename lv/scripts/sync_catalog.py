"""Download public CKAN metadata atomically. Never download the source data files."""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://data.gov.lv/dati/api/3/action/'
OUT = Path(__file__).resolve().parents[1] / 'public/data/catalog.json'


def request(action, **params):
    url = BASE + action + '?' + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LatvijasDatiExplorer/1.0'})
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = json.load(response)
            if not payload.get('success'):
                raise RuntimeError(str(payload.get('error')))
            return payload['result']
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def normalize(item):
    keys = ['id', 'name', 'title', 'notes', 'metadata_modified', 'metadata_created',
            'license_title', 'license_id', 'license_url', 'url', 'frequency']
    result = {k: item.get(k) for k in keys}
    org = item.get('organization') or {}
    result['organization'] = {k: org.get(k, '') for k in ['name', 'title']}
    result['groups'] = [{k: g.get(k, '') for k in ['name', 'title']} for g in item.get('groups', [])]
    result['tags'] = [t.get('display_name') or t.get('name', '') for t in item.get('tags', [])]
    result['resources'] = [{k: r.get(k) for k in ['id', 'name', 'description', 'format', 'url',
                            'datastore_active', 'last_modified', 'size']} for r in item.get('resources', [])]
    return result


def main():
    items = {}
    start = 0
    while True:
        batch = request('package_search', rows=200, start=start, sort='id asc')
        rows = batch['results']
        for item in rows:
            if not item.get('private') and item.get('state') == 'active':
                items[item['id']] = normalize(item)
        print(f'Fetched {len(items)} / {batch["count"]}', flush=True)
        start += len(rows)
        if start >= batch['count']:
            break
        if not rows:
            raise RuntimeError('Catalog ended prematurely; refusing to publish partial data')
    if len(items) != batch['count']:
        raise RuntimeError('Catalog changed during sync; refusing to publish incomplete data. Retry.')
    payload = {'source': BASE, 'fetchedAt': datetime.now(timezone.utc).isoformat(),
               'count': len(items), 'datasets': list(items.values())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUT.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    os.replace(temporary, OUT)
    print(f'Saved {OUT.name}: {len(items)} datasets', flush=True)


if __name__ == '__main__':
    main()

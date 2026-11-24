"""Publish the reviewed Treasury JSON resource into the local table-preview schema.

This does not deploy the site. The catalog pointer changes only after the complete
source has passed parsing and the browser payload limit. A failed conversion leaves
the existing catalog and previews intact. Use one sync process per checkout.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sync_budget_estimates import (
    DATASET, RESOURCE_ID, SOURCE_URL, MAX_DOWNLOAD,
    download, parse_budget_estimates,
)

ROOT = Path(__file__).resolve().parents[1]
MAX_PREVIEW = 24 * 1024 * 1024


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def atomic_bytes(path, content):
    """Write a complete file next to its target and atomically replace the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '-',
                                         suffix='.tmp', delete=False) as handle:
            name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
        name = None
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def exactly_one(items, key, value, label):
    matches = [item for item in items if isinstance(item, dict) and item.get(key) == value]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one reviewed {label}: {value}')
    return matches[0]


def partition_by_year(sheets):
    """Keep every source row, compacting text dictionaries for each selected year."""
    grouped = {}
    for sheet in sheets:
        fields = sheet['fields']
        year_indexes = [i for i, field in enumerate(fields) if field['id'] == 'Gads']
        if len(year_indexes) != 1 or fields[year_indexes[0]].get('type') != 'number':
            raise ValueError('Budget estimates require one numeric Gads column')
        by_year = {}
        for row in sheet['rows']:
            if len(row) != len(fields):
                raise ValueError('Budget estimates row does not match its fields')
            year = row[year_indexes[0]]
            if type(year) is not int or not 1900 <= year <= 2200:
                raise ValueError('Budget estimates row has an invalid year; cannot partition without data loss')
            by_year.setdefault(str(year), []).append(row)
        for year, rows in by_year.items():
            copied_fields = [{k: v for k, v in field.items() if k != 'dictionary'}
                             for field in fields]
            lookups = {}
            for i, field in enumerate(fields):
                if 'dictionary' in field:
                    copied_fields[i]['dictionary'] = []
                    lookups[i] = {}
            copied_rows = []
            for row in rows:
                copied = list(row)
                for i, lookup in lookups.items():
                    index = row[i]
                    if index is None:
                        continue
                    dictionary = fields[i]['dictionary']
                    if type(index) is not int or not 0 <= index < len(dictionary):
                        raise ValueError('Invalid dictionary index in budget estimates')
                    if index not in lookup:
                        lookup[index] = len(copied_fields[i]['dictionary'])
                        copied_fields[i]['dictionary'].append(dictionary[index])
                    copied[i] = lookup[index]
                copied_rows.append(copied)
            result = {k: v for k, v in sheet.items() if k not in ('fields', 'rows', 'total')}
            result.update(fields=copied_fields, rows=copied_rows, total=len(copied_rows))
            grouped.setdefault(year, []).append(result)
    return grouped


def referenced_preview_paths(catalog):
    paths = set()
    for dataset in catalog.get('datasets', []):
        for resource in dataset.get('resources', []):
            preview = resource.get('local_preview')
            if isinstance(preview, dict):
                paths.add(preview.get('path'))
                for part in preview.get('partitions', []):
                    paths.add(part.get('path'))
    return paths


def publish(source_dir=None, *, root=None):
    root = Path(root) if root is not None else ROOT
    catalog_path = root / 'public/data/catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    dataset = exactly_one(catalog.get('datasets', []), 'id', DATASET, 'dataset')
    resource = exactly_one(dataset.get('resources', []), 'id', RESOURCE_ID, 'resource')
    # The parser reviews one specific endpoint, not an arbitrary catalog URL.
    if resource.get('url') != SOURCE_URL:
        raise ValueError('Budget estimates source URL changed; manual review required')
    if source_dir is not None:
        source_path = Path(source_dir) / f'{RESOURCE_ID}.json'
        if source_path.stat().st_size > MAX_DOWNLOAD:
            raise ValueError('Budget estimates source exceeds size limit')
        content = source_path.read_bytes()
    else:
        content = download(SOURCE_URL)
    if len(content) > MAX_DOWNLOAD:
        raise ValueError('Budget estimates source exceeds size limit')
    sheets = parse_budget_estimates(content)
    if not sheets or any(not sheet.get('rows') or sheet.get('total') != len(sheet['rows'])
                         for sheet in sheets):
        raise ValueError('Empty or inconsistent budget estimates conversion')
    grouped = partition_by_year(sheets)
    if sum(s['total'] for year_sheets in grouped.values() for s in year_sheets) != sum(s['total'] for s in sheets):
        raise ValueError('Partition totals do not match the complete source')
    sha = hashlib.sha256(content).hexdigest()
    converted_at = datetime.now(timezone.utc).isoformat()
    cached_times = set()
    for year in grouped:
        cached = root / 'public/data/json' / f'{RESOURCE_ID}-v1-{sha[:16]}-{year}.json'
        if cached.exists():
            if cached.stat().st_size > MAX_PREVIEW:
                raise ValueError('Existing JSON preview exceeds size limit')
            old_time = json.loads(cached.read_text(encoding='utf-8')).get('convertedAt')
            if not isinstance(old_time, str) or not old_time:
                raise ValueError('Existing JSON preview has no conversion timestamp')
            cached_times.add(old_time)
    if len(cached_times) > 1:
        raise ValueError('Existing year previews have inconsistent conversion timestamps')
    if cached_times:
        converted_at = next(iter(cached_times))
    created, partitions = [], []
    total_bytes = 0
    try:
        for year in sorted(grouped, reverse=True):
            name = f'{RESOURCE_ID}-v1-{sha[:16]}-{year}.json'
            output = root / 'public/data/json' / name
            payload = {'schemaVersion': 1, 'resourceId': RESOURCE_ID, 'sourceFormat': 'JSON',
                       'sourceUrl': SOURCE_URL, 'sourceSha256': sha,
                       'convertedAt': converted_at, 'sheets': grouped[year]}
            encoded = json_bytes(payload)
            if len(encoded) > MAX_PREVIEW:
                raise ValueError(f'Converted JSON year {year} exceeds 24 MiB; further partitioning required')
            # Reuse a verified content-addressed file; never overwrite a previously
            # published preview on a run that could still fail at catalog commit.
            if output.exists():
                if output.stat().st_size > MAX_PREVIEW:
                    raise ValueError('Existing JSON preview exceeds size limit')
                previous = json.loads(output.read_text(encoding='utf-8'))
                old_time = previous.pop('convertedAt', None)
                comparison = dict(payload)
                comparison.pop('convertedAt')
                if previous != comparison or not isinstance(old_time, str) or not old_time:
                    raise ValueError('Existing preview conflicts with source/converter identity; manual review required')
                total_bytes += output.stat().st_size
            else:
                atomic_bytes(output, encoded)
                created.append(output)
                total_bytes += len(encoded)
            partitions.append({'label': year, 'path': 'data/json/' + name,
                               'total': sum(sheet['total'] for sheet in grouped[year])})
        preview = {'sourceFormat': 'JSON', 'partitions': partitions,
                   'sourceUrl': SOURCE_URL, 'sourceSha256': sha,
                   'convertedAt': converted_at, 'total': sum(sheet['total'] for sheet in sheets)}
        resource['local_preview'] = preview
        atomic_bytes(catalog_path, json_bytes(catalog))
    except Exception:
        for output in created:
            try:
                output.unlink()
            except OSError as cleanup_error:
                print(f'Warning: could not remove unreferenced new preview: {cleanup_error}', file=sys.stderr)
        raise

    # Prune only this converter's stale versions after the catalog commit, never
    # another JSON resource or an XLSX preview. Cleanup failure is safe to retain.
    referenced = referenced_preview_paths(catalog)
    for stale in (root / 'public/data/json').glob(f'{RESOURCE_ID}-v1-*.json'):
        if 'data/json/' + stale.name not in referenced:
            try:
                stale.unlink()
            except OSError as cleanup_error:
                print(f'Warning: retained stale JSON preview: {cleanup_error}', file=sys.stderr)
    print(f'{RESOURCE_ID}: {len(partitions)} year partitions, {preview["total"]} rows, '
          f'{total_bytes} JSON bytes', flush=True)
    return preview


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path,
                        help='Use reviewed complete source named RESOURCE_ID.json for reproducible checks')
    args = parser.parse_args(argv)
    publish(args.source_dir)


if __name__ == '__main__':
    main()

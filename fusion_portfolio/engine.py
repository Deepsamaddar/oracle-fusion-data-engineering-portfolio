"""Verified file extraction and atomic, replay-safe loading for the local demo."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCENARIOS = {'apac_procurement', 'emea_payables', 'americas_close'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('updated_at must include a timezone')
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')


def read_manifest(path):
    path = Path(path)
    manifest = json.loads(path.read_text())
    if manifest.get('scenario') not in SCENARIOS:
        raise ValueError('unknown scenario')
    if manifest.get('format') not in {'rest_pages', 'csv'}:
        raise ValueError('unsupported extract format')
    files = manifest.get('files', [])
    if not files:
        raise ValueError('manifest must list files')
    rows, seen = [], set()
    for index, entry in enumerate(files):
        candidate = (path.parent / entry['path']).resolve()
        if not candidate.is_relative_to(path.parent.resolve()) or candidate in seen:
            raise ValueError('unsafe or repeated extract path')
        seen.add(candidate)
        content = candidate.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError('extract checksum mismatch')
        if manifest['format'] == 'rest_pages':
            page = json.loads(content)
            if not isinstance(page.get('items'), list):
                raise ValueError('page must contain items')
            if page.get('hasMore') is not (index < len(files) - 1):
                raise ValueError('incomplete or incorrectly ordered page chain')
            rows.extend(page['items'])
        else:
            rows.extend(csv.DictReader(content.decode('utf-8').splitlines()))
    if len(rows) != manifest.get('expected_rows'):
        raise ValueError('extract row-count mismatch')
    return manifest, rows


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS records (
      scenario TEXT NOT NULL, record_id TEXT NOT NULL, updated_at TEXT NOT NULL,
      payload TEXT NOT NULL, PRIMARY KEY(scenario,record_id));
    CREATE TABLE IF NOT EXISTS runs (
      batch_hash TEXT PRIMARY KEY, scenario TEXT NOT NULL, summary TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS quarantine (
      batch_hash TEXT NOT NULL, row_number INTEGER NOT NULL, reason TEXT NOT NULL,
      payload TEXT NOT NULL, PRIMARY KEY(batch_hash,row_number));
    CREATE TABLE IF NOT EXISTS watermarks (
      scenario TEXT PRIMARY KEY, updated_at TEXT NOT NULL);
    ''')
    return db


def ingest(manifest_path, database, validator, before_commit=None):
    """Validate the complete extract, then commit records, rejects and watermark together.

    before_commit is an injected failure hook for transaction-recovery tests.
    Watermarks are observed source maxima, never used to discard late arrivals.
    """
    manifest, rows = read_manifest(manifest_path)
    scenario = manifest['scenario']
    digest = hashlib.sha256(canonical(manifest).encode()).hexdigest()
    db = connect(database)
    try:
        with db:
            # Serialize concurrent writers before checking whether a batch was loaded.
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT summary FROM runs WHERE batch_hash=?', (digest,)).fetchone()
            if prior:
                return dict(json.loads(prior[0]), replayed=True)
            stats = dict(scenario=scenario, batch_hash=digest, rows_in=len(rows),
                         inserted=0, updated=0, unchanged=0, stale=0, quarantined=0,
                         replayed=False)
            newest = None
            keys = set()
            for number, raw in enumerate(rows, 1):
                try:
                    if not isinstance(raw, dict):
                        raise ValueError('row must be an object')
                    record = validator(scenario, raw)
                    key = str(record['record_id']).strip()
                    if not key:
                        raise ValueError('missing record_id')
                    version = timestamp(record['updated_at'])
                    record['record_id'], record['updated_at'] = key, version
                    if key in keys:
                        raise ValueError('duplicate record_id within batch')
                    keys.add(key)
                    payload = canonical(record)
                    existing = db.execute('SELECT updated_at,payload FROM records WHERE scenario=? AND record_id=?',
                                          (scenario, key)).fetchone()
                    if existing and version == existing[0] and payload != existing[1]:
                        raise ValueError('conflicting payload at the same source version')
                except (ValueError, KeyError, TypeError) as error:
                    stats['quarantined'] += 1
                    db.execute('INSERT INTO quarantine VALUES (?,?,?,?)',
                               (digest, number, str(error), canonical(raw)))
                    continue
                newest = max(newest or version, version)
                if existing and version < existing[0]:
                    stats['stale'] += 1
                elif existing and version == existing[0]:
                    stats['unchanged'] += 1
                else:
                    stats['updated' if existing else 'inserted'] += 1
                    db.execute('INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(scenario,record_id) DO UPDATE SET updated_at=excluded.updated_at,payload=excluded.payload',
                               (scenario, key, version, payload))
            if newest:
                db.execute('INSERT INTO watermarks VALUES (?,?) ON CONFLICT(scenario) DO UPDATE SET updated_at=MAX(updated_at,excluded.updated_at)',
                           (scenario, newest))
            db.execute('INSERT INTO runs VALUES (?,?,?)', (digest, scenario, canonical(stats)))
            if before_commit:
                before_commit(db)
        return stats
    finally:
        db.close()


def records(database, scenario):
    with sqlite3.connect(database) as db:
        return [json.loads(row[0]) for row in db.execute(
            'SELECT payload FROM records WHERE scenario=? ORDER BY record_id', (scenario,))]

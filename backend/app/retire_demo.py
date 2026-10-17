"""Explicit, backed-up retirement of one legacy work; never called at startup."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from uuid import uuid4
from sqlalchemy import MetaData, create_engine, delete, select
from sqlalchemy.engine import make_url
from app.cache import clear_catalog
from app.storage import database_url

LEGACY_ID = 'fengqiao-yebo'
ORDER = ['player_events', 'sessions', 'realms', 'jobs', 'poem_scenes', 'poems']


def data_tables(connection):
    metadata = MetaData()
    metadata.reflect(bind=connection)
    return {name: table for name, table in metadata.tables.items() if name in ORDER}


def identity(raw, nested=False):
    if raw is None or raw == '':
        return set()
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError('Legacy JSON is not an object; cannot determine ownership')
    result = set()
    for field in ('poem_id', 'poemId'):
        if field in document:
            if not isinstance(document[field], str) or not document[field].strip():
                raise ValueError('Invalid poem identity')
            result.add(document[field])
    if nested:
        if 'id' in document:
            if not isinstance(document['id'], str):
                raise ValueError('Invalid snapshot identity')
            result.add(document['id'])
    for field in ('poem', 'poem_snapshot'):
        if field in document:
            if not isinstance(document[field], dict):
                raise ValueError('Invalid embedded poem')
            result |= identity(json.dumps(document[field]), nested=True)
    return result


def deletion_plan(connection):
    tables = data_tables(connection)
    rows = {name: list(connection.execute(select(table)).mappings()) for name, table in tables.items()}
    targets = {name: [] for name in ORDER}
    job_claims = {}
    for job in rows.get('jobs', []):
        claims = set()
        for field in ('request_json', 'input_scene_json'):
            claims |= identity(job.get(field))
        claims |= identity(job.get('poem_snapshot_json'), nested=True)
        job_claims[job['id']] = claims
    for realm in rows.get('realms', []):
        if realm['id'] not in job_claims:
            raise ValueError('Orphan realm; cannot safely identify ownership')
        job_claims[realm['id']] |= identity(realm['scene_json'])
    for key, claims in job_claims.items():
        if len(claims) != 1:
            raise ValueError(f'Conflicting or missing work identity for job {key}')
        if LEGACY_ID in claims:
            targets['jobs'].append(key)
    realm_ids = {r['id'] for r in rows.get('realms', [])}
    targets['realms'] = sorted(realm_ids & set(targets['jobs']))
    for session in rows.get('sessions', []):
        realm_id = session['realm_id']
        if realm_id not in realm_ids:
            raise ValueError('Orphan session; cannot safely identify ownership')
        report_claims = identity(session.get('report_json'))
        if report_claims and report_claims != job_claims[realm_id]:
            raise ValueError('Report ownership conflicts with session realm')
        if realm_id in targets['realms']:
            targets['sessions'].append(session['id'])
    session_ids = {s['id'] for s in rows.get('sessions', [])}
    for event in rows.get('player_events', []):
        if event['session_id'] not in session_ids:
            raise ValueError('Orphan event; refusing ambiguous deletion')
        if event['session_id'] in targets['sessions']:
            targets['player_events'].append([event['session_id'], event['event_id']])
    for row in rows.get('poem_scenes', []):
        claims = identity(row['scene_json']) | {row['poem_id']}
        if len(claims) != 1:
            raise ValueError('Poem scene identity conflict')
        if LEGACY_ID in claims:
            targets['poem_scenes'].append(row['poem_id'])
    for row in rows.get('poems', []):
        claims = identity(row['poem_json'], nested=True) | {row['id']}
        if len(claims) != 1:
            raise ValueError('Poem identity conflict')
        if LEGACY_ID in claims:
            targets['poems'].append(row['id'])
    return {'workId': LEGACY_ID, 'targets': {name: sorted(values) for name, values in targets.items()},
            'counts': {name: len(values) for name, values in targets.items()}, 'tableCounts': {name: len(values) for name, values in rows.items()}}


def fingerprint(connection, exclude=None):
    result = {}
    for name, table in data_tables(connection).items():
        rows = list(connection.execute(select(table)).mappings())
        if exclude:
            keys = table.primary_key.columns.keys()
            targets = {tuple(v) if isinstance(v, list) else (v,) for v in exclude['targets'][name]}
            rows = [r for r in rows if tuple(r[k] for k in keys) not in targets]
        serialized = sorted(json.dumps(dict(row), sort_keys=True, ensure_ascii=False, default=str) for row in rows)
        result[name] = hashlib.sha256('\n'.join(serialized).encode('utf-8')).hexdigest()
    return result


def apply_deletion(connection, preview):
    # Caller owns transaction. Full table fingerprints protect unrelated rows and detect concurrent changes.
    current = deletion_plan(connection)
    if current != preview:
        raise ValueError('Database changed after preview')
    before = fingerprint(connection, preview)
    tables = data_tables(connection)
    for name in ORDER:
        if name not in tables:
            continue
        table = tables[name]
        for key in preview['targets'][name]:
            values = key if isinstance(key, list) else [key]
            condition = [table.c[column] == value for column, value in zip(table.primary_key.columns.keys(), values)]
            connection.execute(delete(table).where(*condition))
    if fingerprint(connection) != before:
        raise ValueError('Unrelated rows changed; transaction must roll back')


def sqlite_backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError('Backup must be a new file distinct from the source')
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as old:
        with sqlite3.connect(destination) as backup:
            old.backup(backup)
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup failed integrity check')
    copied = create_engine('sqlite:///' + destination.as_posix())
    try:
        with copied.connect() as connection:
            return fingerprint(connection)
    finally:
        copied.dispose()


def postgres_backup(destination, compose_file, database_name='echoes'):
    """pg_dump/restore execute in the database container, never expose credentials."""
    prefix = ['docker', 'compose', '-f', str(Path(compose_file).resolve()), 'exec', '-T', 'postgres']
    temporary = 'eov_restore_' + uuid4().hex
    def run(args):
        subprocess.run(prefix + args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with Path(destination).open('xb') as handle:
        subprocess.run(prefix + ['pg_dump', '-U', 'echoes', '-d', database_name, '-Fc'], check=True,
                       stdout=handle, stderr=subprocess.PIPE)
    run(['createdb', '-U', 'echoes', temporary])
    try:
        with Path(destination).open('rb') as handle:
            subprocess.run(prefix + ['pg_restore', '-U', 'echoes', '-d', temporary, '--exit-on-error'],
                           stdin=handle, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Compare logical content without depending on pg_dump output order.
        # Query canonical JSON arrays and compare them in the caller.
        restored = {}
        for name in ORDER:
            exists = subprocess.run(prefix + ['psql', '-U', 'echoes', '-d', temporary, '-At', '-c', f"SELECT to_regclass('{name}') IS NOT NULL"], check=True, capture_output=True, text=True).stdout.strip()
            if exists == 't':
                raw = subprocess.run(prefix + ['psql', '-U', 'echoes', '-d', temporary, '-At', '-c', f"SELECT coalesce(json_agg(t),'[]'::json) FROM {name} t"], check=True, capture_output=True, text=True, encoding='utf-8').stdout
                rows = json.loads(raw)
                serialized = sorted(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows)
                restored[name] = hashlib.sha256('\n'.join(serialized).encode('utf-8')).hexdigest()
        return restored
    finally:
        run(['dropdb', '-U', 'echoes', temporary])


def retire(url, backup_dir, apply=False, compose_file=None):
    parsed = make_url(url)
    if parsed.drivername.startswith('sqlite') and (not parsed.database or not Path(parsed.database).is_file()):
        raise FileNotFoundError('Configured SQLite database does not exist; no database created')
    db = create_engine(url)
    try:
        with db.connect() as connection:
            preview = deletion_plan(connection)
            original = fingerprint(connection)
        if not apply:
            return {**preview, 'applied': False}
        directory = Path(backup_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stem = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
        (directory / (stem + '-preview.json')).write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding='utf-8')
        if parsed.drivername.startswith('sqlite'):
            backup = directory / (stem + '.sqlite3')
            restored = sqlite_backup(parsed.database, backup)
        elif parsed.drivername.startswith('postgresql') and compose_file:
            backup = directory / (stem + '.dump')
            restored = postgres_backup(backup, compose_file)
        else:
            raise ValueError('PostgreSQL cleanup requires the project Docker Compose backup/restore path')
        if restored != original:
            raise ValueError('Restored backup does not match original tables; no deletion performed')
        with db.begin() as connection:
            if parsed.drivername.startswith('sqlite'):
                connection.exec_driver_sql('PRAGMA foreign_keys=ON')
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            else:
                names = data_tables(connection)
                if names:
                    connection.exec_driver_sql('LOCK TABLE ' + ','.join(sorted(names)) + ' IN ACCESS EXCLUSIVE MODE')
            if fingerprint(connection) != original:
                raise ValueError('Database changed since backup; refusing deletion')
            apply_deletion(connection, preview)
        report = {**preview, 'applied': True, 'backup': str(backup.resolve()), 'backupRestoredAndVerified': True,
                  'backupSha256': hashlib.sha256(backup.read_bytes()).hexdigest(), 'unrelatedRowsUnchanged': True}
        (directory / (stem + '-report.json')).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        clear_catalog()
        return report
    finally:
        db.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Preview or back up and retire the old demo')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-dir', required=True)
    parser.add_argument('--compose-file')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(retire(database_url(), args.backup_dir, args.apply, args.compose_file), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError):
        print(json.dumps({'ok': False, 'code': 'RETIREMENT_FAILED', 'message': 'Backup, ownership or database check failed; inspect locally before retrying'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

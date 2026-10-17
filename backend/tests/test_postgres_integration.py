"""Opt-in real PostgreSQL checks, restricted to a disposable local audit instance."""
import json
import os
import shutil
import sqlite3
import time
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app import storage
from app.content import POEM_ID, ROOT, poem_projection
from app.import_content import import_record
from app.migrate_sqlite import import_database
from app.main import app

AUDIT_URL = os.environ.get('EOV_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not AUDIT_URL, reason='requires disposable local PostgreSQL audit instance')


@pytest.fixture
def pg(tmp_path, monkeypatch):
    url = make_url(AUDIT_URL)
    if (url.drivername != 'postgresql+psycopg' or url.host != '127.0.0.1'
            or url.username != 'audit' or url.database != 'eov_audit' or url.query):
        pytest.fail('Refusing any database other than the disposable local audit instance')
    admin = create_engine(url, connect_args={'connect_timeout': 3})
    schema = 'audit_' + uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql('CREATE SCHEMA ' + schema)
    scoped = url.update_query_dict({'options': '-c search_path=' + schema}).render_as_string(hide_password=False)
    source = tmp_path / 'source'
    source.mkdir()
    for name in ('content-pack.json', 'resource-manifest.json'):
        shutil.copyfile(ROOT / 'content/shuidiaogetou-2' / name, source / name)
    monkeypatch.setenv('DATABASE_URL', scoped)
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(source))
    storage.initialize()
    with storage.database() as db:
        db.execute('INSERT INTO poems VALUES(?,?,?,?)', ('unrelated-audit-marker', 'marker', 'test', '{"marker":true}'))
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, source, admin, schema
        with storage.database() as db:
            assert db.execute('SELECT poem_json FROM poems WHERE id=?', ('unrelated-audit-marker',)).fetchone()[0] == '{"marker":true}'
            assert db.execute('SELECT count(*) FROM poems').fetchone()[0] == 2
    finally:
        cached = storage._engines.pop(scoped, None)
        if cached:
            cached.dispose()
        admin.dispose()
        # Each schema belongs to this disposable container and is removed with it.


def assert_error(response, status, code):
    assert response.status_code == status
    data = response.json()
    assert data['error']['code'] == code
    assert str(UUID(data['request_id'])) == response.headers['X-Request-ID']
    assert 'disposable-audit-only' not in response.text
    assert 'audit_' not in response.text


def test_pg_http_catalog_lookup_validation_and_identity(pg):
    client, _, _, _ = pg
    expected = json.loads((ROOT / 'examples/client-poems.json').read_text(encoding='utf-8'))[0]
    assert client.get('/health').status_code == 200
    assert client.get('/openapi.json').json()['info']['version'] == '0.5.0'
    catalog = client.get('/api/v1/poems').json()
    assert catalog['total'] == 1
    assert {key: catalog['items'][0][key] for key in expected} == expected
    assert client.get('/api/v1/poems/lookup', params={'title': '水调歌头', 'author': '苏轼'}).json()['matches'][0]['poem'] == expected
    assert client.get('/api/v1/poems/lookup', params={'title': '不存在'}).json()['matches'] == []
    assert_error(client.get('/api/v1/poems?limit=0'), 422, 'VALIDATION_ERROR')
    assert_error(client.get('/api/v1/sessions'), 404, 'HTTP_ERROR')
    denied = client.post('/api/v1/poems')
    assert_error(denied, 405, 'HTTP_ERROR')
    assert denied.headers['Allow'] == 'GET'
    with storage.database() as db:
        assert db.execute('SELECT id FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0] == POEM_ID


def test_pg_server_applies_deadlines_and_preserves_search_path(pg):
    _, _, _, schema = pg
    with storage.database() as db:
        assert db.execute('SHOW statement_timeout').fetchone()[0] == '5s'
        assert db.execute('SHOW lock_timeout').fetchone()[0] == '1s'
        assert db.execute('SHOW search_path').fetchone()[0] == schema


def test_pg_table_lock_returns_503_then_recovers(pg):
    client, _, admin, schema = pg
    with admin.connect() as blocker:
        transaction = blocker.begin()
        blocker.exec_driver_sql('LOCK TABLE ' + schema + '.poems IN ACCESS EXCLUSIVE MODE')
        try:
            started = time.perf_counter()
            assert_error(client.get('/health'), 503, 'DATABASE_UNAVAILABLE')
            assert .7 <= time.perf_counter() - started < 4
        finally:
            transaction.rollback()
    assert client.get('/health').status_code == 200
    assert client.get('/api/v1/poems').json()['total'] == 1


def test_pg_long_statement_is_cancelled_and_connection_recovers(pg):
    client, _, _, _ = pg
    started = time.perf_counter()
    with pytest.raises(DBAPIError) as caught:
        with storage.database() as db:
            db.execute('SELECT pg_sleep(12)')
    assert caught.value.orig.sqlstate == '57014'
    assert 4 <= time.perf_counter() - started < 8
    assert client.get('/health').status_code == 200


def test_pg_connection_pool_exhaustion_returns_503_then_recovers(pg):
    client, _, _, _ = pg
    connections = []
    try:
        connections = [storage.engine().connect() for _ in range(15)]
        started = time.perf_counter()
        assert_error(client.get('/health'), 503, 'DATABASE_UNAVAILABLE')
        assert 1.5 <= time.perf_counter() - started < 6
    finally:
        for connection in connections:
            connection.close()
    assert client.get('/health').status_code == 200


def test_pg_terminated_idle_connection_is_replaced(pg):
    client, _, admin, _ = pg
    with storage.database() as db:
        pid = db.execute('SELECT pg_backend_pid()').fetchone()[0]
    with admin.begin() as connection:
        assert connection.execute(text('SELECT pg_terminate_backend(:pid)'), {'pid': pid}).scalar() is True
    assert client.get('/health').status_code == 200
    with storage.database() as db:
        assert db.execute('SELECT pg_backend_pid()').fetchone()[0] != pid


def test_pg_corrupt_sql_is_distinct_from_content_fault_and_recovers(pg):
    client, source, _, _ = pg
    with storage.database() as db:
        original = db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0]
        db.execute('UPDATE poems SET poem_json=? WHERE id=?', ('broken', POEM_ID))
    assert_error(client.get('/api/v1/poems'), 500, 'LOCAL_DATA_INVALID')
    with storage.database() as db:
        db.execute('UPDATE poems SET poem_json=? WHERE id=?', (original, POEM_ID))
    assert client.get('/api/v1/poems').status_code == 200
    path = source / 'content-pack.json'
    content = path.read_bytes()
    path.write_bytes(b'broken')
    assert_error(client.get('/api/v1/poems'), 503, 'CONTENT_UNAVAILABLE')
    assert client.get('/health').status_code == 200
    path.write_bytes(content)
    assert client.get('/api/v1/poems').status_code == 200


def test_pg_reinitialization_does_not_overwrite_existing_records(pg):
    with storage.database() as db:
        original = db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0]
        changed = json.loads(original)
        changed['title'] = 'synthetic-maintained-title'
        db.execute('UPDATE poems SET poem_json=? WHERE id=?', (json.dumps(changed), POEM_ID))
    storage.initialize()
    with storage.database() as db:
        assert json.loads(db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0])['title'] == 'synthetic-maintained-title'
        db.execute('UPDATE poems SET poem_json=? WHERE id=?', (original, POEM_ID))


@pytest.mark.parametrize('failure', ['invalid_url', 'scan', 'delete'])
def test_pg_import_commits_despite_optional_cache_failure(pg, monkeypatch, failure):
    from unittest.mock import Mock
    from redis.exceptions import ConnectionError
    from app import cache
    if failure == 'invalid_url': monkeypatch.setenv('REDIS_URL', 'invalid-secret-canary')
    else:
        client = Mock()
        client.scan_iter.return_value = ['eov:catalog:synthetic']
        getattr(client, 'scan_iter' if failure == 'scan' else 'delete').side_effect = ConnectionError('secret-canary')
        monkeypatch.setattr(cache, '_client', lambda: client)
    poem = poem_projection().model_copy(update={'title': 'synthetic-imported-title'})
    assert import_record({'poem': poem.model_dump()}, replace=True) == {'poem_id': POEM_ID}
    with storage.database() as db:
        assert json.loads(db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0])['title'] == poem.title


def test_pg_import_database_failure_rolls_back_even_when_cache_is_invalid(pg, monkeypatch):
    monkeypatch.setenv('REDIS_URL', 'invalid-secret-canary')
    with storage.database() as db:
        original = db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0]
    engine = storage.engine()
    def fail_after_write(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO poems'):
            raise RuntimeError('synthetic failure after write, before commit')
    event.listen(engine, 'after_cursor_execute', fail_after_write)
    try:
        with pytest.raises(RuntimeError, match='before commit'):
            import_record({'poem': poem_projection().model_copy(update={'title': 'must-roll-back'}).model_dump()}, replace=True)
    finally: event.remove(engine, 'after_cursor_execute', fail_after_write)
    with storage.database() as db:
        assert db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0] == original


@pytest.mark.parametrize('failure', ['invalid_url', 'scan', 'delete'])
def test_pg_sqlite_import_cache_failure_idempotence_and_conflict(pg, tmp_path, monkeypatch, failure):
    from unittest.mock import Mock
    from redis.exceptions import ConnectionError
    from app import cache
    if failure == 'invalid_url': monkeypatch.setenv('REDIS_URL', 'invalid-secret-canary')
    else:
        client = Mock()
        client.scan_iter.return_value = ['eov:catalog:synthetic']
        getattr(client, 'scan_iter' if failure == 'scan' else 'delete').side_effect = ConnectionError('secret-canary')
        monkeypatch.setattr(cache, '_client', lambda: client)
    source = tmp_path / 'source.sqlite3'
    poem = poem_projection()
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE poems(id TEXT PRIMARY KEY, poem_json TEXT NOT NULL)')
        db.execute('INSERT INTO poems VALUES(?,?)', (POEM_ID, poem.model_dump_json()))
    source_before = source.read_bytes()
    with storage.database() as db: db.execute('DELETE FROM poems WHERE id=?', (POEM_ID,))
    assert import_database(source) == {'poems': 1}
    assert import_database(source) == {'poems': 0}
    changed = poem.model_copy(update={'title': 'synthetic-conflict'})
    with storage.database() as db:
        db.execute('UPDATE poems SET poem_json=? WHERE id=?', (changed.model_dump_json(), POEM_ID))
    with pytest.raises(ValueError, match='Conflicting current poem'): import_database(source)
    with storage.database() as db:
        assert db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0] == changed.model_dump_json()
    assert source.read_bytes() == source_before

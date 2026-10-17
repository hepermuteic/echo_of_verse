"""Failure injection uses disposable databases/content, never deployment state."""
import copy
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app import storage
from app.content import POEM_ID, ROOT
from app.demo_content import export_pack, load_source, verify_checksums
from app.demo_models import Review
from app.main import app


@pytest.fixture
def http(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    for name in ('content-pack.json', 'resource-manifest.json'):
        shutil.copyfile(ROOT / 'content/shuidiaogetou-2' / name, source / name)
    monkeypatch.setenv('EOV_DB_PATH', str(tmp_path / 'isolated.sqlite3'))
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(source))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, source
    storage._engines.pop(storage.database_url()).dispose()


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert body['error']['code'] == code
    assert str(UUID(body['request_id'])) == response.headers['X-Request-ID']
    assert 'secret-canary' not in response.text
    return body


def test_method_not_allowed_retains_allow_header(http):
    client, _ = http
    for path in ('/health', '/api/v1/poems', '/api/v1/poems/lookup'):
        response = client.post(path, json={'ignored': True})
        assert_error(response, 405, 'HTTP_ERROR')
        assert response.headers['Allow'] == 'GET'


@pytest.mark.parametrize('path', ['/api/v1/poems', '/api/v1/poems/lookup?title=水调歌头'])
def test_content_projection_does_not_hold_database(http, monkeypatch, path):
    from app.content import client_content
    def projection():
        assert storage.engine().pool.checkedout() == 0
        return client_content()
    monkeypatch.setattr('app.main.client_content', projection)
    assert http[0].get(path).status_code == 200


@pytest.mark.parametrize('name', ['client-default-settings.json', 'CLIENT_MAPPING.md'])
def test_missing_release_artifact_cannot_be_hidden_by_rewriting_checksums(http, tmp_path, monkeypatch, name):
    client, source = http
    pack, manifest = load_source(source)
    review = Review(status='reviewed', reviewer='synthetic-test-only', reviewedAt='2026-10-15')
    pack.poem.review = review
    for item in pack.sources:
        item.review = review
    for item in pack.texts:
        item.en = 'Synthetic test translation'
        item.reviewZh = item.reviewEn = review
    for item in pack.presentations:
        item.confirmed = True
    for item in pack.parameters:
        item.confirmed = True
    for item in manifest.assets:
        item.status, item.license = 'ready', 'synthetic-test-only'
    assert export_pack(pack, manifest, tmp_path / 'release', release=True)['ok']
    released = tmp_path / 'release' / pack.contentVersion
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(released))
    assert client.get('/api/v1/poems').status_code == 200
    (released / name).unlink()
    checks = json.loads((released / 'checksums.json').read_text())
    del checks[name]
    (released / 'checksums.json').write_text(json.dumps(checks))
    with pytest.raises(ValueError):
        verify_checksums(released)
    assert_error(client.get('/api/v1/poems'), 503, 'CONTENT_UNAVAILABLE')


@pytest.mark.parametrize('payload', [b'\xff\xfe\x00', b'{', b'null'])
def test_content_fault_and_repair_need_no_restart(http, payload):
    client, source = http
    path = source / 'content-pack.json'
    original = path.read_bytes()
    path.write_bytes(payload)
    failed = assert_error(client.get('/api/v1/poems'), 503, 'CONTENT_UNAVAILABLE')
    assert client.get('/health').status_code == 200
    assert client.get('/api/v1/poems/lookup', params={'title': '不存在'}).json()['matches'] == []
    path.write_bytes(original)
    recovered = client.get('/api/v1/poems')
    assert recovered.status_code == 200
    assert recovered.json()['items'][0]['id'] == 'shuidiaogetou'
    assert recovered.headers['X-Request-ID'] != failed['request_id']


def test_unexpected_failure_has_safe_correlated_error_and_recovers(http, monkeypatch):
    client, _ = http
    def fail():
        raise RuntimeError('secret-canary private/path SQL failure')
    with monkeypatch.context() as patch:
        patch.setattr('app.main.client_content', fail)
        assert_error(client.get('/api/v1/poems'), 500, 'INTERNAL_ERROR')
    assert client.get('/api/v1/poems').status_code == 200


@pytest.mark.parametrize('params', [
    {'title': 'x' * 129}, {'title': '\x00'}, {'title': '《》'},
    {'title': '水调歌头', 'author': ' '}, {'title': '水调歌头', 'unknown': 'secret-canary'},
])
def test_invalid_or_unknown_names_never_mutate_database(http, params):
    client, _ = http
    response = client.get('/api/v1/poems/lookup', params=params)
    assert response.status_code in (200, 422)
    if response.status_code == 422:
        assert_error(response, 422, 'VALIDATION_ERROR')
    else:
        assert response.json()['matches'] == []
    with storage.database() as db:
        assert db.execute('SELECT id FROM poems').fetchall()[0][0] == POEM_ID
        assert db.execute('SELECT count(*) FROM poems').fetchone()[0] == 1


def test_sql_parameters_are_not_executable(http):
    client, _ = http
    for title in ["'; DROP TABLE poems;--", "' OR '1'='1", '%', '_']:
        response = client.get('/api/v1/poems/lookup', params={'title': title})
        assert response.status_code == 200 and response.json()['matches'] == []
    assert client.get('/api/v1/poems').json()['total'] == 1


def test_sqlite_lock_returns_503_then_recovers(http):
    client, _ = http
    storage.engine().dispose()
    with sqlite3.connect(storage.db_path(), timeout=1) as locked:
        locked.execute('PRAGMA journal_mode=DELETE')
        locked.execute('BEGIN EXCLUSIVE')
        started = time.perf_counter()
        assert_error(client.get('/health'), 503, 'DATABASE_UNAVAILABLE')
        assert time.perf_counter() - started < 5
        locked.rollback()
    assert client.get('/health').status_code == 200


def test_database_path_failure_is_503_without_fallback_or_data_loss(http, tmp_path, monkeypatch):
    client, _ = http
    blocker = tmp_path / 'not-a-directory'
    blocker.write_bytes(b'synthetic-existing-file')
    with monkeypatch.context() as patch:
        patch.setenv('EOV_DB_PATH', str(blocker / 'database.sqlite3'))
        assert_error(client.get('/health'), 503, 'DATABASE_UNAVAILABLE')
    assert blocker.read_bytes() == b'synthetic-existing-file'
    assert client.get('/api/v1/poems').json()['total'] == 1


def test_pool_exhaustion_is_bounded_and_recovers(http):
    client, _ = http
    connections = []
    try:
        # Default QueuePool: five persistent plus ten overflow connections.
        connections = [storage.engine().connect() for _ in range(15)]
        started = time.perf_counter()
        assert_error(client.get('/health'), 503, 'DATABASE_UNAVAILABLE')
        assert time.perf_counter() - started < 7
    finally:
        for connection in connections:
            connection.close()
    assert client.get('/health').status_code == 200


def test_postgres_silent_peer_connect_timeout_is_bounded(http, monkeypatch):
    client, _ = http
    done = threading.Event()
    accepted = threading.Event()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(6)
        port = listener.getsockname()[1]
        def silent_peer():
            try:
                connection, _ = listener.accept()
                with connection:
                    accepted.set()
                    done.wait(7)
            except OSError:
                pass
        thread = threading.Thread(target=silent_peer, daemon=True)
        thread.start()
        url = f'postgresql+psycopg://test:secret-canary@127.0.0.1:{port}/synthetic?sslmode=disable'
        try:
            with monkeypatch.context() as patch:
                patch.setenv('DATABASE_URL', url)
                started = time.perf_counter()
                assert_error(client.get('/health'), 503, 'DATABASE_UNAVAILABLE')
                assert time.perf_counter() - started < 7
                assert accepted.is_set()
        finally:
            done.set()
            thread.join(timeout=8)
            cached = storage._engines.pop(url, None)
            if cached:
                cached.dispose()
    assert client.get('/health').status_code == 200


def test_postgres_read_deadlines_preserve_other_session_options(monkeypatch):
    url = 'postgresql+psycopg://test@127.0.0.1/synthetic?options=-c%20search_path%3Dpoetry'
    monkeypatch.setenv('DATABASE_URL', url)
    engine = storage.engine()
    captured = {}
    def capture(dialect, connection_record, args, kwargs):
        captured.update(kwargs)
        raise dialect.dbapi.OperationalError('synthetic connection stopped before network')
    event.listen(engine, 'do_connect', capture)
    try:
        with pytest.raises(OperationalError):
            engine.connect()
        assert captured['connect_timeout'] == 3
        assert '-c search_path=poetry' in captured['options']
        assert '-c statement_timeout=5000' in captured['options']
        assert '-c lock_timeout=1000' in captured['options']
    finally:
        storage._engines.pop(url).dispose()


def test_invalid_startup_configuration_fails_before_creating_database(tmp_path):
    import os
    config = tmp_path / 'invalid.toml'
    config.write_text('config_version = "unsupported"')
    database = tmp_path / 'must-not-exist.sqlite3'
    env = dict(os.environ, EOV_CONFIG_FILE=str(config), EOV_DB_PATH=str(database))
    env.pop('DATABASE_URL', None)
    env.pop('REDIS_URL', None)
    result = subprocess.run([sys.executable, '-c', 'from app.storage import initialize; initialize()'],
                            cwd=ROOT, env=env, capture_output=True, timeout=8)
    assert result.returncode != 0
    assert not database.exists()


def test_parallel_exports_publish_once_without_partial_output(tmp_path):
    pack, manifest = load_source(ROOT / 'content/shuidiaogetou-2')
    def publish(_):
        try:
            return export_pack(copy.deepcopy(pack), copy.deepcopy(manifest), tmp_path)['ok']
        except FileExistsError:
            return False
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(publish, range(2))) == [False, True]
    assert [p.name for p in tmp_path.iterdir()] == [pack.contentVersion]
    verify_checksums(tmp_path / pack.contentVersion)


def test_failed_atomic_rename_leaves_no_partial_version(tmp_path, monkeypatch):
    pack, manifest = load_source(ROOT / 'content/shuidiaogetou-2')
    def fail(*args):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr('app.demo_content.os.rename', fail)
    with pytest.raises(OSError):
        export_pack(pack, manifest, tmp_path)
    assert list(tmp_path.iterdir()) == []

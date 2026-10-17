"""Optional cache errors must not reverse or misreport committed maintenance work."""
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app import cache, storage
from app.content import POEM_ID, poem_projection
from app.import_content import import_record, main


@pytest.mark.parametrize('operation', ['get', 'put', 'clear_catalog'])
@pytest.mark.parametrize('stage', ['invalid_url', 'configuration', 'operation', 'delete'])
def test_cache_failure_is_best_effort_and_logs_no_secrets(operation, stage, monkeypatch, caplog):
    client = Mock()
    client.scan_iter.return_value = ['eov:catalog:synthetic']
    if stage == 'invalid_url':
        monkeypatch.setenv('REDIS_URL', 'invalid-secret-canary')
    elif stage == 'configuration':
        def unavailable(): raise OSError('secret-canary private/path')
        monkeypatch.setattr(cache, '_client', unavailable)
    else:
        name = {'get': 'get', 'put': 'setex', 'clear_catalog': 'scan_iter'}[operation]
        if stage == 'delete' and operation == 'clear_catalog': name = 'delete'
        getattr(client, name).side_effect = ConnectionError('redis://user:secret-canary@private-host')
        monkeypatch.setattr(cache, '_client', lambda: client)
    args = ('key', {'value': True}) if operation == 'put' else ('key',) if operation == 'get' else ()
    assert getattr(cache, operation)(*args) is None
    assert 'cache skipped' in caplog.text
    assert all(value not in caplog.text for value in ('secret-canary', 'private/path', 'private-host'))
    assert all(record.exc_info is None for record in caplog.records)


def test_import_cli_reports_committed_success_with_invalid_redis(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('EOV_DB_PATH', str(tmp_path / 'import.sqlite3'))
    monkeypatch.setenv('REDIS_URL', 'invalid-secret-canary')
    source = tmp_path / 'poem.json'
    source.write_text('{"poem":' + poem_projection().model_dump_json() + '}', encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['import_content', '--file', str(source)])
    assert main() == 0
    assert POEM_ID in capsys.readouterr().out
    with storage.database() as db:
        assert db.execute('SELECT count(*) FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0] == 1


def test_cache_downgrade_does_not_hide_database_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv('EOV_DB_PATH', str(tmp_path / 'rollback.sqlite3'))
    monkeypatch.setenv('REDIS_URL', 'invalid-secret-canary')
    storage.initialize(seed_demo=False)
    engine = storage.engine()
    def reject(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO poems'):
            raise OperationalError('synthetic rejected write', None, RuntimeError('test'))
    event.listen(engine, 'before_cursor_execute', reject)
    try:
        with pytest.raises(OperationalError): import_record({'poem': poem_projection().model_dump()})
    finally: event.remove(engine, 'before_cursor_execute', reject)
    with storage.database() as db: assert db.execute('SELECT count(*) FROM poems').fetchone()[0] == 0

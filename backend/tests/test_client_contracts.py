import copy
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.client_contracts import ClientPoem, ClientSettings, FRONTEND_COMMIT, SaveSlot
from app.client_content import client_documents, project_client_poem
from app.content import POEM_ID, ROOT
from app.demo_content import export_pack, fixtures, load_source, main, validate_pack, verify_checksums
from app.demo_models import ContentPack, JourneySnapshot
from app.main import app
from app.storage import database, initialize

SOURCE = ROOT / 'content/shuidiaogetou-2'
EXPECTED = json.loads((Path(__file__).parent / 'fixtures/frontend-poem.e24415f.json').read_text(encoding='utf-8'))
DEFAULTS = dict(master=80, music=20, ambient=70, voice=90, mouse=50, size=1, sub=0,
                quality=1, brush=True, reduce=False, subOn=True)


@pytest.fixture
def current():
    return load_source(SOURCE)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('EOV_DB_PATH', str(tmp_path / 'isolated.sqlite3'))
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(SOURCE))
    with TestClient(app) as http:
        yield http


def test_exact_pinned_frontend_projection_and_http_export_parity(current, client, tmp_path):
    pack, manifest = current
    assert pack.clientPresentation.sourceCommit == FRONTEND_COMMIT
    assert project_client_poem(pack).model_dump(mode='json') == EXPECTED
    listing = client.get('/api/v1/poems').json()
    item = listing['items'][0]
    assert listing['total'] == 1 and listing['limit'] == 20 and listing['offset'] == 0
    assert {key: item[key] for key in EXPECTED} == EXPECTED
    assert set(item) == set(EXPECTED) | {'contentVersion', 'contentStatus', 'content_review_status'}
    for title in ['水调歌头', '《水调歌头·明月几时有》']:
        response = client.get('/api/v1/poems/lookup', params={'title': title, 'author': '苏轼'}).json()
        assert response['matches'][0] == {
            'poem': EXPECTED, 'contentVersion': 'shuidiaogetou-2', 'contentStatus': 'draft',
            'content_review_status': 'demo_unreviewed'}
    assert export_pack(pack, manifest, tmp_path)['ok']
    output = tmp_path / pack.contentVersion
    verify_checksums(output)
    assert json.loads((output / 'client-poems.json').read_text(encoding='utf-8')) == [EXPECTED]
    assert ClientPoem.model_validate_json((output / 'client-poems.json').read_text(encoding='utf-8').strip()[1:-1]).model_dump(mode='json') == EXPECTED
    assert json.loads((output / 'client-default-settings.json').read_text()) == DEFAULTS
    for filename, model in [('client-poem.schema.json', ClientPoem), ('client-save-slot.schema.json', SaveSlot), ('client-settings.schema.json', ClientSettings)]:
        assert json.loads((output / filename).read_text(encoding='utf-8')) == model.model_json_schema()
    assert (output / 'CLIENT_MAPPING.md').is_file()
    assert (output / 'LEGACY_UNITY_RESOURCE_MAPPING.md').is_file()
    assert not (output / 'UNITY_MAPPING.md').exists()
    assert load_source(output)[0].model_dump() == pack.model_dump()
    with pytest.raises(FileExistsError):
        export_pack(pack, manifest, tmp_path)
    (output / 'client-default-settings.json').write_text('{}')
    with pytest.raises(ValueError):
        verify_checksums(output)


def test_empty_results_validation_and_no_state_mutation(client):
    absent = client.get('/api/v1/poems/lookup', params={'title': '枫桥夜泊'}).json()
    assert absent['matches'] == [] and not absent['poem_exists']
    assert absent['contentVersion'] is None and absent['contentStatus'] == 'missing'
    assert client.get('/api/v1/poems', params={'offset': 1}).json()['items'] == []
    for params in [{'title': ''}, {'author': '苏轼'}, {'title': '水调歌头', 'language': 'en'}]:
        response = client.get('/api/v1/poems/lookup', params=params)
        assert response.status_code == 422
        assert response.json()['request_id'] == response.headers['X-Request-ID']
    with database() as db:
        assert db.execute('SELECT id FROM poems').fetchone()[0] == POEM_ID
        assert len(db.execute('SELECT id FROM poems').fetchall()) == 1


@pytest.mark.parametrize('case', ['missing', 'corrupt', 'no-view', 'missing-text', 'wrong-group', 'bad-resource', 'legacy-only'])
def test_unavailable_content_is_503_but_unknown_lookup_stays_empty(client, current, tmp_path, monkeypatch, case):
    pack, manifest = current
    if case != 'missing':
        data = pack.model_dump(mode='json')
        if case == 'no-view': data.pop('clientPresentation')
        if case == 'missing-text': data['clientPresentation']['imagery'][0]['noteTextId'] = 'absent'
        if case == 'wrong-group': data['clientPresentation']['stanzaSegmentIds'][0].reverse()
        if case == 'legacy-only': data = load_source(ROOT / 'content/shuidiaogetou-1')[0].model_dump(mode='json')
        (tmp_path / 'content-pack.json').write_text('broken' if case == 'corrupt' else json.dumps(data), encoding='utf-8')
        assets = manifest.model_dump(mode='json')
        if case == 'bad-resource': assets['assets'][0]['format'] = 'invented-godot-format'
        (tmp_path / 'resource-manifest.json').write_text(json.dumps(assets), encoding='utf-8')
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(tmp_path))
    for path in ['/api/v1/poems', '/api/v1/poems/lookup?title=水调歌头']:
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'CONTENT_UNAVAILABLE'
        assert response.json()['request_id'] == response.headers['X-Request-ID']
        assert 'tmp' not in response.json()['error']['message']
    assert client.get('/api/v1/poems/lookup', params={'title': '不存在'}).json()['status'] == 'not_found'
    assert client.get('/health').status_code == 200


def test_database_unavailable_is_distinct_from_content_unavailable(client, monkeypatch):
    @contextmanager
    def unavailable():
        raise sqlite3.OperationalError('synthetic private database path')
        yield
    monkeypatch.setattr('app.main.database', unavailable)
    response = client.get('/api/v1/poems')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'DATABASE_UNAVAILABLE'
    assert 'private' not in response.text


def test_fresh_database_missing_content_does_not_prevent_service_start(tmp_path, monkeypatch):
    monkeypatch.setenv('EOV_DB_PATH', str(tmp_path / 'fresh.sqlite3'))
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(tmp_path / 'missing-content'))
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/v1/poems').json()['total'] == 0
    with database() as db:
        assert db.execute('SELECT count(*) FROM poems').fetchone()[0] == 0


def test_corrupt_sql_is_not_silently_hidden_by_client_projection(client):
    with database() as db:
        db.execute('UPDATE poems SET poem_json=? WHERE id=?', ('broken', POEM_ID))
    response = client.get('/api/v1/poems')
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'LOCAL_DATA_INVALID'


@pytest.mark.parametrize('case', ['repeat', 'empty', 'reorder', 'act', 'text', 'optional-review'])
def test_client_references_are_validated_and_exports_fail_atomically(current, tmp_path, case):
    pack, manifest = copy.deepcopy(current)
    view = pack.clientPresentation
    if case == 'repeat': view.stanzaSegmentIds[1][0] = view.stanzaSegmentIds[0][0]
    if case == 'empty': view.stanzaSegmentIds[0] = []
    if case == 'reorder': view.stanzaSegmentIds.reverse()
    if case == 'act': view.acts.reverse()
    if case == 'text': view.imagery[0].sourceTextId = 'absent'
    if case == 'optional-review': next(t for t in pack.texts if t.textId == view.imagery[0].noteTextId).required = False
    report = export_pack(pack, manifest, tmp_path)
    assert not report['ok'] and 'CLIENT_PRESENTATION_INVALID' in {i['code'] for i in report['issues']}
    assert list(tmp_path.iterdir()) == []


def test_release_remains_blocked_and_game_events_are_unchanged(current, tmp_path):
    pack, manifest = current
    legacy, old_manifest = load_source(ROOT / 'content/shuidiaogetou-1')
    for field in ['poem', 'events', 'acts', 'presentations', 'parameters', 'reflectionRules', 'objects', 'regions', 'spawns', 'environments']:
        assert getattr(pack, field) == getattr(legacy, field)
    assert manifest == old_manifest
    assert all(t.reviewZh.status == 'demo_unreviewed' for t in pack.texts if t.textId.startswith('client.'))
    assert not export_pack(pack, manifest, tmp_path, release=True)['ok']
    assert list(tmp_path.iterdir()) == []
    for fixture in fixtures(pack):
        assert fixture['input']['contentVersion'] == 'shuidiaogetou-2'
    # A UI SaveSlot is never accepted as an event snapshot, even at lineIndex=8.
    saved = SaveSlot(poemId='shuidiaogetou', lineIndex=8, act=2, savedAt=0)
    with pytest.raises(ValueError): JourneySnapshot.model_validate(saved.model_dump())


@pytest.mark.parametrize('field,value', [('poemId', POEM_ID), ('lineIndex', -1), ('lineIndex', 9), ('lineIndex', True), ('lineIndex', 1.5), ('act', 3), ('act', False), ('savedAt', -1), ('savedAt', float('inf')), ('savedAt', '10')])
def test_save_slot_invalid_inputs(field, value):
    data = dict(poemId='shuidiaogetou', lineIndex=0, act=0, savedAt=0)
    data[field] = value
    with pytest.raises(ValueError): SaveSlot.model_validate(data)


@pytest.mark.parametrize('field,value', [('master', -1), ('music', 101), ('ambient', True), ('voice', '90'), ('mouse', 50.5), ('size', 3), ('sub', -1), ('quality', True), ('brush', 1), ('reduce', 'false'), ('subOn', None)])
def test_settings_invalid_inputs(field, value):
    with pytest.raises(ValueError): ClientSettings.model_validate({field: value})


def test_settings_defaults_boundaries_optional_fields_and_schema_examples(current):
    assert ClientSettings().model_dump() == DEFAULTS
    assert ClientSettings(master=0, music=100, size=0, sub=2).master == 0
    for line in [0, 8]:
        assert SaveSlot(poemId='shuidiaogetou', lineIndex=line, act=2, savedAt=1720000000000).lineIndex == line
    bare = {key: value for key, value in EXPECTED.items() if key not in ['preface', 'acts', 'imagery', 'note']}
    assert ClientPoem.model_validate(bare).model_dump(mode='json') == bare
    docs = client_documents(current[0])
    for name, value in docs.items():
        assert json.loads((ROOT / 'examples' / name).read_text(encoding='utf-8')) == value
    assert ContentPack.model_json_schema()['properties']['schemaVersion']['enum'] == ['1.0', '1.1', '1.2']


def test_cli_current_export_and_release(current, tmp_path, capsys):
    assert main(['validate', '--source', str(SOURCE)]) == 0
    assert main(['export', '--source', str(SOURCE), '--output', str(tmp_path / 'draft')]) == 0
    assert main(['release', '--source', str(SOURCE), '--output', str(tmp_path / 'release')]) == 1
    assert not (tmp_path / 'release').exists()


def test_released_client_content_requires_review_and_intact_handoff(current, client, tmp_path, monkeypatch):
    from app.demo_models import Review
    pack, manifest = copy.deepcopy(current)
    synthetic = Review(status='reviewed', reviewer='synthetic-test-only', reviewedAt='2026-10-15')
    pack.poem.review = synthetic
    for source in pack.sources: source.review = synthetic
    for text in pack.texts:
        text.en = 'Synthetic test translation'
        text.reviewZh = synthetic
        text.reviewEn = synthetic
    for presentation in pack.presentations: presentation.confirmed = True
    for parameter in pack.parameters: parameter.confirmed = True
    for asset in manifest.assets:
        asset.status = 'ready'
        asset.license = 'synthetic test only'
    assert export_pack(pack, manifest, tmp_path, release=True)['ok']
    output = tmp_path / pack.contentVersion
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(output))
    response = client.get('/api/v1/poems')
    assert response.status_code == 200
    assert response.json()['items'][0]['contentStatus'] == 'released'
    # Changes to any extra client artifact invalidate the complete release.
    (output / 'client-default-settings.json').write_text('{}')
    response = client.get('/api/v1/poems')
    assert response.status_code == 503 and response.json()['error']['code'] == 'CONTENT_UNAVAILABLE'


def test_content_schema_version_requires_client_binding(current):
    data = current[0].model_dump(mode='json')
    for version, value in [('1.1', None), ('1.0', data['clientPresentation'])]:
        bad = {**data, 'schemaVersion': version, 'clientPresentation': value}
        with pytest.raises(ValueError): ContentPack.model_validate(bad)
    schema = ContentPack.model_json_schema()
    assert schema['allOf'][0]['then']['required'] == ['clientPresentation']

import copy
import json
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from app.content import POEM_ID, ROOT, content_state, poem_projection
from app.contracts import Poem
from app.demo_models import ContentPack, JourneySnapshot, Parameter, ReflectionRule, Review
from app.demo_content import load_source, validate_pack, evaluate_reflection, fixtures, export_pack, verify_checksums, main
from app.resources import ResourceManifest, AssetRecord, AssetReference
from app.storage import initialize, database
from app.import_content import import_record
from app.retire_demo import retire, deletion_plan, apply_deletion, fingerprint
from app.main import app


@pytest.fixture
def source():
    return load_source(ROOT / 'content/shuidiaogetou-1')


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    monkeypatch.setenv('EOV_DB_PATH', str(tmp_path / 'demo.sqlite3'))
    monkeypatch.delenv('EOV_CONTENT_SOURCE', raising=False)
    initialize()
    return tmp_path / 'demo.sqlite3'


def test_single_demo_api_and_removed_routes(local_db):
    with TestClient(app) as client:
        health = client.get('/health')
        assert health.json()['mode'] == 'offline_content'
        for title in ['水调歌头', ' 《水调歌头·明月几时有》 ']:
            result = client.get('/api/v1/poems/lookup', params={'title': title, 'author': '苏轼'})
            assert result.json()['contentStatus'] == 'draft'
            assert result.json()['matches'][0]['poem']['id'] == 'shuidiaogetou'
            assert 'can_experience' not in result.json()
        assert not client.get('/api/v1/poems/lookup', params={'title': '不存在'}).json()['poem_exists']
        assert not client.get('/api/v1/poems/lookup', params={'title': '水调歌头', 'author': '他人'}).json()['poem_exists']
        for url in ['/api/v1/generations', '/api/v1/generations/id', '/api/v1/realms/id', '/api/v1/sessions',
                    '/api/v1/sessions/id/events', '/api/v1/sessions/id/finish', '/api/v1/sessions/id/report']:
            for method in (client.get, client.post):
                response = method(url)
                assert response.status_code == 404
                assert response.json()['error']['code'] == 'HTTP_ERROR'
                assert response.json()['request_id'] == response.headers['X-Request-ID']
        assert set(client.get('/openapi.json').json()['paths']) == {'/health', '/api/v1/poems', '/api/v1/poems/lookup'}
        for params in ({'limit': 0}, {'offset': -1}, {'unknown': 'x'}):
            assert client.get('/api/v1/poems', params=params).status_code == 422
        assert client.get('/api/v1/poems/lookup', params={'title': '《》'}).status_code == 422


def test_seed_is_additive_and_catalog_filters_other_records(local_db):
    with database() as db:
        db.execute('INSERT INTO poems VALUES(?,?,?,?)', ('other', '其他', '作者', json.dumps({'id': 'other', 'title': '其他', 'author': '作者', 'lines': ['合成文本']})))
        db.execute('UPDATE poems SET title_key=?,poem_json=? WHERE id=?', ('custom', poem_projection().model_copy(update={'title': '手工维护标题'}).model_dump_json(), POEM_ID))
    initialize()
    with TestClient(app) as client:
        result = client.get('/api/v1/poems').json()
        assert result['total'] == 1 and result['items'][0]['title'] == '水调歌头'
        assert client.get('/api/v1/poems', params={'offset': 1}).json()['items'] == []
    with database() as db:
        assert db.execute('SELECT count(*) FROM poems').fetchone()[0] == 2
        assert read_stored_title(db) == '手工维护标题'
    engine = create_engine('sqlite:///' + local_db.as_posix())
    assert inspect(engine).get_table_names() == ['poems']
    engine.dispose()


def test_import_only_current_poem(local_db):
    with pytest.raises(ValueError):
        import_record({'poem': poem_projection().model_dump(), 'scene': {}})
    with pytest.raises(ValueError):
        import_record({'poem': Poem(id='other', title='其他', author='作者', lines=['合成']).model_dump()})
    with pytest.raises(ValueError):
        import_record({'poem': poem_projection().model_dump()})
    import_record({'poem': poem_projection().model_dump()}, replace=True)


def test_content_state_missing_corrupt_and_released_integrity(source, tmp_path, monkeypatch):
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(tmp_path))
    assert content_state()['contentStatus'] == 'missing'
    (tmp_path / 'content-pack.json').write_text('{}')
    assert content_state()['contentStatus'] == 'invalid'
    pack, manifest = approved(*source)
    export_pack(pack, manifest, tmp_path, release=True)
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(tmp_path / pack.contentVersion))
    assert content_state()['contentStatus'] == 'released'
    notes = tmp_path / pack.contentVersion / 'RELEASE_NOTES.md'
    notes.write_text(notes.read_text() + 'tampered')
    assert content_state()['contentStatus'] == 'invalid'


def test_draft_honest_and_release_blocked(source):
    pack, manifest = source
    report = validate_pack(pack, manifest)
    assert report['ok'] and report['englishCoverage']['covered'] == 0
    assert not validate_pack(pack, manifest, release=True)['ok']
    assert all(a.status == 'declared' for a in manifest.assets)


@pytest.mark.parametrize('case,code', [
    ('duplicate', 'DUPLICATE_ID'), ('missing_text', 'MISSING_REFERENCE'), ('early_return', 'EARLY_RETURN_BLOCKED'),
    ('cycle', 'EVENT_CYCLE'), ('moon', 'MOON_DEPENDENCY'), ('exit', 'ACT_EXIT'), ('cross_act', 'CROSS_ACT_DEPENDENCY'),
    ('asset_missing', 'ASSET_MISSING'), ('type', 'ASSET_TYPE'), ('catalog', 'CATALOG_VERSION'),
    ('binding', 'BINDING_ACT'), ('transform', 'TRANSFORM'), ('claim', 'UNSUPPORTED_EXPERIENCE'),
    ('default_claim', 'DEFAULT_CLAIM'), ('unit', 'PARAMETER_UNIT')])
def test_semantic_rejections(source, case, code):
    pack, manifest = copy.deepcopy(source)
    if case == 'duplicate': pack.events.append(pack.events[0])
    if case == 'missing_text': pack.events[0].nodeTextId = 'unknown'
    if case == 'early_return': pack.events[2].prerequisites.append('act2.high.visited')
    if case == 'cycle': pack.events[0].prerequisites = ['act3.moon.confirmed']
    if case == 'moon': pack.events[4].prerequisites = ['act2.return.confirmed']
    if case == 'exit': pack.acts[1].exitEventId = 'act2.high.visited'
    if case == 'cross_act': pack.events[2].prerequisites.append('act3.shadow.responded')
    if case == 'asset_missing': pack.objects[0].asset.assetVersion = 'absent'
    if case == 'type': manifest.assets[0] = AssetRecord(asset_id='sdt.courtyard', asset_version='1', asset_type='audio', delivery='builtin', format='unity_audioclip', address='sdt.courtyard', source='synthetic', license='test')
    if case == 'catalog': pack.resourceCatalogVersion = 'other'
    if case == 'binding': pack.events[0].trigger.objectId = 'return.main'
    if case == 'transform': pack.objects[0].rotation = (0, 0, 0, 0)
    if case == 'claim': pack.reflectionRules[0].when.allEvents = []
    if case == 'default_claim': next(t for t in pack.texts if t.textId == pack.defaultReflectionTextId).experienceEventIds = ['act2.high.visited']
    if case == 'unit': pack.parameters[0].unit = 'seconds'
    report = validate_pack(pack, manifest)
    assert not report['ok'] and code in {i['code'] for i in report['issues']}


def test_new_arbitrary_resource_and_version(source):
    pack, manifest = copy.deepcopy(source)
    pack.objects[0].asset.assetId = 'custom.new-cup'
    record = manifest.assets[1].model_copy(update={'asset_id': 'custom.new-cup', 'address': 'custom.new-cup'})
    manifest.assets.append(record)
    assert validate_pack(pack, manifest)['ok']


@pytest.mark.parametrize('case', ['duplicate', 'missing', 'cycle', 'ready_dependency'])
def test_resource_graph(case):
    a = {'asset_id': 'a', 'asset_version': '1', 'asset_type': 'prefab', 'delivery': 'builtin', 'format': 'unity_prefab', 'address': 'a', 'source': 'synthetic', 'license': 'test', 'dependencies': [{'asset_id': 'b', 'asset_version': '1'}]}
    b = {**a, 'asset_id': 'b', 'dependencies': []}
    if case == 'duplicate': b = a
    if case == 'missing': a['dependencies'][0]['asset_version'] = '2'
    if case == 'cycle': b['dependencies'] = [{'asset_id': 'a', 'asset_version': '1'}]
    if case == 'ready_dependency': a['status'] = 'ready'
    with pytest.raises(ValueError):
        ResourceManifest(catalog_version='synthetic', assets=[a, b])


def test_reflection_routes_no_fabrication_and_order(source):
    pack, _ = source
    cases = fixtures(pack)
    assert cases[0]['expected']['ruleId'] == 'reflection.high'
    for case in cases[1:]:
        assert case['expected']['ruleId'] is None
        assert 'act2.high.visited' not in [node['eventId'] for node in case['expected']['nodes']]
    assert [n['eventId'] for n in cases[0]['expected']['nodes']] == [e['eventId'] for e in cases[0]['input']['committedEvents']]
    snapshot = JourneySnapshot.model_validate(cases[1]['input'])
    snapshot.committedEvents[2], snapshot.committedEvents[3] = snapshot.committedEvents[3], snapshot.committedEvents[2]
    with pytest.raises(ValueError): evaluate_reflection(pack, snapshot)
    snapshot = JourneySnapshot.model_validate(cases[1]['input'])
    snapshot.contentVersion = 'unknown'
    with pytest.raises(ValueError): evaluate_reflection(pack, snapshot)


def test_reflection_uses_actual_order_and_rejects_closed_act(source):
    pack, _ = copy.deepcopy(source)
    # Configuration array order is irrelevant; confirmations remain ordered.
    pack.events.reverse()
    case = fixtures(pack)[0]
    assert [node['eventId'] for node in case['expected']['nodes']] == [item['eventId'] for item in case['input']['committedEvents']]
    invalid = copy.deepcopy(case['input'])
    invalid['committedEvents'] = [{'eventId': identity, 'sequence': i} for i, identity in enumerate([
        'act1.cup.confirmed', 'act2.return.confirmed', 'act2.high.visited', 'act3.shadow.responded', 'act3.moon.confirmed'])]
    with pytest.raises(ValueError): evaluate_reflection(pack, JourneySnapshot.model_validate(invalid))


def read_stored_title(db):
    return json.loads(db.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()[0])['title']


def test_existing_projection_rejects_invalid_client_content(local_db, tmp_path, monkeypatch):
    (tmp_path / 'content-pack.json').write_text('{}')
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(tmp_path))
    with TestClient(app) as client:
        response = client.get('/api/v1/poems/lookup', params={'title': '水调歌头'})
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'CONTENT_UNAVAILABLE'


def test_dwell_and_tie_break_use_synthetic_parameters(source):
    pack, manifest = copy.deepcopy(source)
    pack.parameters.append(Parameter(parameterId='synthetic.dwell', value=10, unit='seconds', confirmed=True))
    pack.reflectionRules = [ReflectionRule(ruleId=name, priority=20, when={'dwellMin': [{'regionId': 'courtyard.move', 'parameterId': 'synthetic.dwell'}]}, textId=pack.defaultReflectionTextId) for name in ['z', 'a']]
    assert validate_pack(pack, manifest)['ok']
    snapshot = JourneySnapshot.model_validate(fixtures(pack)[1]['input'])
    snapshot.regionDwell = []
    assert evaluate_reflection(pack, snapshot)['ruleId'] is None
    snapshot = JourneySnapshot.model_validate({**snapshot.model_dump(), 'regionDwell': [{'regionId': 'courtyard.move', 'effectiveSeconds': 9.9}]})
    assert evaluate_reflection(pack, snapshot)['ruleId'] is None
    snapshot.regionDwell[0].effectiveSeconds = 10
    assert evaluate_reflection(pack, snapshot)['ruleId'] == 'a'


def approved(pack, manifest):
    pack, manifest = copy.deepcopy((pack, manifest))
    review = Review(status='reviewed', reviewer='synthetic-test-reviewer', reviewedAt='2026-10-09')
    pack.poem.review = review
    for source in pack.sources: source.review = review
    for text_entry in pack.texts:
        text_entry.en = 'Synthetic English fixture'
        text_entry.reviewZh = review; text_entry.reviewEn = review
    for presentation in pack.presentations: presentation.confirmed = True
    for parameter in pack.parameters: parameter.confirmed = True
    for asset in manifest.assets:
        asset.status = 'ready'; asset.license = 'synthetic test only'
    return pack, manifest


def test_export_release_checksum_and_refusal(source, tmp_path):
    pack, manifest = source
    report = export_pack(pack, manifest, tmp_path)
    assert report['ok']
    output = tmp_path / pack.contentVersion
    verify_checksums(output)
    assert load_source(output)[0].model_dump() == pack.model_dump()
    with pytest.raises(FileExistsError): export_pack(pack, manifest, tmp_path)
    blocked = tmp_path / 'blocked'
    assert not export_pack(pack, manifest, blocked, True)['ok']
    assert not blocked.exists()
    pack, manifest = approved(pack, manifest)
    formal = tmp_path / 'formal'
    assert export_pack(pack, manifest, formal, True)['ok']
    assert load_source(formal / pack.contentVersion)[0].publication == 'released'
    verify_checksums(formal / pack.contentVersion)
    (formal / pack.contentVersion / 'extra.txt').write_text('extra')
    with pytest.raises(ValueError): verify_checksums(formal / pack.contentVersion)


def test_cli_codes(source, tmp_path, capsys):
    directory = ROOT / 'content/shuidiaogetou-1'
    assert main(['validate', '--source', str(directory)]) == 0
    assert main(['release', '--source', str(directory), '--output', str(tmp_path)]) == 1
    assert main(['validate', '--source', str(tmp_path / 'absent')]) == 2
    (tmp_path / 'content-pack.json').write_text('{}')
    assert main(['validate', '--source', str(tmp_path)]) == 1


def test_export_failure_leaves_no_partial_version(source, tmp_path, monkeypatch):
    import app.demo_content as module
    pack, manifest = source
    def failed(*args):
        raise OSError('Synthetic checksum verification failure')
    monkeypatch.setattr(module, 'verify_checksums', failed)
    with pytest.raises(OSError): export_pack(pack, manifest, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('value', [True, '10', -1, float('inf')])
def test_effective_dwell_rejects_non_numeric_or_invalid_values(value):
    from app.demo_models import RegionDwell
    with pytest.raises(ValueError): RegionDwell(regionId='synthetic', effectiveSeconds=value)


def test_generated_machine_contracts_match_models():
    examples = ROOT / 'examples'
    for name, model in [('content-pack.schema.json', ContentPack), ('resource-manifest.schema.json', ResourceManifest), ('journey-snapshot.schema.json', JourneySnapshot)]:
        assert json.loads((examples / name).read_text(encoding='utf-8')) == model.model_json_schema()
    assert json.loads((examples / 'openapi.json').read_text(encoding='utf-8')) == app.openapi()


def legacy_database(path):
    db = create_engine('sqlite:///' + path.as_posix())
    with db.begin() as c:
        c.exec_driver_sql('CREATE TABLE poems(id TEXT PRIMARY KEY,title_key TEXT,author_key TEXT,poem_json TEXT)')
        c.exec_driver_sql('CREATE TABLE poem_scenes(poem_id TEXT PRIMARY KEY REFERENCES poems(id),scene_json TEXT)')
        c.exec_driver_sql('CREATE TABLE jobs(id TEXT PRIMARY KEY,request_json TEXT,input_scene_json TEXT,poem_snapshot_json TEXT)')
        c.exec_driver_sql('CREATE TABLE realms(id TEXT PRIMARY KEY REFERENCES jobs(id),scene_json TEXT)')
        c.exec_driver_sql('CREATE TABLE sessions(id TEXT PRIMARY KEY,realm_id TEXT REFERENCES realms(id),report_json TEXT)')
        c.exec_driver_sql('CREATE TABLE player_events(session_id TEXT REFERENCES sessions(id),event_id TEXT,payload_json TEXT,PRIMARY KEY(session_id,event_id))')
        for identity in ['fengqiao-yebo', 'keep']:
            poem = json.dumps({'id': identity, 'title': 'Synthetic migration data', 'author': 'test', 'lines': ['fixture']})
            scene = json.dumps({'poem_id': identity})
            c.exec_driver_sql('INSERT INTO poems VALUES(?,?,?,?)', (identity, identity, 'test', poem))
            c.exec_driver_sql('INSERT INTO poem_scenes VALUES(?,?)', (identity, scene))
            c.exec_driver_sql('INSERT INTO jobs VALUES(?,?,?,?)', (identity, scene, scene, poem))
            c.exec_driver_sql('INSERT INTO realms VALUES(?,?)', (identity, scene))
            c.exec_driver_sql('INSERT INTO sessions VALUES(?,?,?)', (identity, identity, '{}'))
            c.exec_driver_sql('INSERT INTO player_events VALUES(?,?,?)', (identity, 'event', '{}'))
    return db


def test_retirement_preview_backup_restore_preservation_and_repeat(tmp_path):
    path = tmp_path / 'old.sqlite3'; db = legacy_database(path)
    with db.connect() as c: original = fingerprint(c)
    preview = retire(str(db.url), tmp_path / 'backups')
    assert not preview['applied'] and set(preview['counts'].values()) == {1}
    assert not (tmp_path / 'backups').exists()
    report = retire(str(db.url), tmp_path / 'backups', apply=True)
    assert report['backupRestoredAndVerified'] and report['unrelatedRowsUnchanged']
    restore = create_engine('sqlite:///' + Path(report['backup']).as_posix())
    with restore.connect() as c: assert fingerprint(c) == original
    restore.dispose()
    with db.connect() as c:
        for table in ['poems', 'poem_scenes', 'jobs', 'realms', 'sessions', 'player_events']:
            assert c.exec_driver_sql('SELECT count(*) FROM ' + table).scalar() == 1
    assert set(retire(str(db.url), tmp_path / 'repeat')['counts'].values()) == {0}
    db.dispose()


@pytest.mark.parametrize('case', ['corrupt', 'conflict', 'missing'])
def test_retirement_ambiguity_never_deletes(tmp_path, case):
    db = legacy_database(tmp_path / 'old.sqlite3')
    with db.begin() as c:
        changed = 'broken' if case == 'corrupt' else json.dumps({'poem_id': 'conflict'}) if case == 'conflict' else '{}'
        c.exec_driver_sql('UPDATE jobs SET request_json=?,input_scene_json=NULL,poem_snapshot_json=NULL WHERE id=?', (changed, 'fengqiao-yebo'))
        if case == 'missing': c.exec_driver_sql('UPDATE realms SET scene_json=? WHERE id=?', ('{}', 'fengqiao-yebo'))
    with pytest.raises(ValueError): retire(str(db.url), tmp_path / 'backup', apply=True)
    with db.connect() as c: assert c.exec_driver_sql('SELECT count(*) FROM poems').scalar() == 2
    assert not (tmp_path / 'backup').exists()
    db.dispose()


def test_retirement_transaction_rollback(tmp_path):
    db = legacy_database(tmp_path / 'old.sqlite3')
    with db.connect() as c:
        original = fingerprint(c); preview = deletion_plan(c)
    with pytest.raises(RuntimeError):
        with db.begin() as c:
            apply_deletion(c, preview)
            raise RuntimeError('Synthetic post-delete failure')
    with db.connect() as c: assert fingerprint(c) == original
    db.dispose()


@pytest.mark.parametrize('case', ['node', 'explanation', 'optional_event', 'dialogue',
                                  'insight', 'default', 'rule', 'client_imagery', 'client_note'])
def test_displayed_text_cannot_opt_out_of_release_review(case, tmp_path):
    pack, manifest = approved(*load_source(ROOT / 'content/shuidiaogetou-2'))
    if case == 'node': identity = pack.events[0].nodeTextId
    elif case == 'explanation': identity = pack.events[0].explanationTextId
    elif case == 'optional_event': identity = next(e for e in pack.events if not e.required).nodeTextId
    elif case == 'dialogue':
        step = next(s for s in pack.presentations[0].steps if s.textId)
        step.required = False  # Even optional dialogue is displayed if selected.
        identity = step.textId
    elif case == 'insight': identity = pack.insights[0].textId
    elif case == 'default': identity = pack.defaultReflectionTextId
    elif case == 'rule': identity = pack.reflectionRules[0].textId
    elif case == 'client_imagery': identity = pack.clientPresentation.imagery[0].noteTextId
    else:
        identity = pack.clientPresentation.imagery[0].noteTextId
        pack.clientPresentation.noteTextId = identity
    text_entry = next(t for t in pack.texts if t.textId == identity)
    text_entry.required = False
    text_entry.reviewZh = Review()
    for release in (False, True):
        report = validate_pack(pack, manifest, release=release)
        assert not report['ok']
        assert any(i['code'] == 'REQUIRED_TEXT' and identity in i['message'] for i in report['issues'])
        assert any(i['code'] == 'UNREVIEWED' and i['objectId'] == identity
                   and i['severity'] == ('error' if release else 'warning') for i in report['issues'])
    assert not export_pack(pack, manifest, tmp_path / 'release', release=True)['ok']
    assert not (tmp_path / 'release').exists()


@pytest.mark.parametrize('case', ['trigger_only', 'required_step', 'optional_event_step'])
def test_mandatory_usage_cannot_hide_declared_object_resource(case):
    pack, manifest = approved(*load_source(ROOT / 'content/shuidiaogetou-2'))
    identity = {'trigger_only': 'cup.main', 'required_step': 'shadow.main',
                'optional_event_step': 'cloud-steps.main'}[case]
    if case == 'trigger_only':
        for presentation in pack.presentations:
            for step in presentation.steps:
                if step.objectId == identity: step.required = False
    binding = next(o for o in pack.objects if o.objectId == identity)
    binding.required = False
    resource = next(a for a in manifest.assets if (a.asset_id, a.asset_version) ==
                    (binding.asset.assetId, binding.asset.assetVersion))
    resource.status = 'declared'
    for release in (False, True):
        report = validate_pack(pack, manifest, release=release)
        assert not report['ok']
        assert any(i['code'] == 'REQUIRED_OBJECT' and identity in i['message'] for i in report['issues'])
        assert any(i['code'] == 'ASSET_PENDING' and i['objectId'] == resource.asset_id
                   and i['severity'] == ('error' if release else 'warning') for i in report['issues'])


def test_unused_optional_text_and_decoration_remain_optional():
    pack, manifest = approved(*load_source(ROOT / 'content/shuidiaogetou-2'))
    unused = pack.texts[0].model_copy(update={'textId': 'synthetic.unused', 'required': False,
        'requiresEnglish': False, 'en': None, 'reviewZh': Review(), 'reviewEn': Review()})
    pack.texts.append(unused)
    decoration = next(o for o in pack.objects if o.objectId == 'distant-light.main')
    assert not decoration.required
    next(a for a in manifest.assets if a.asset_id == decoration.asset.assetId).status = 'declared'
    assert validate_pack(pack, manifest, release=True)['ok']


def test_usage_required_resource_still_checks_transitive_dependencies():
    pack, manifest = approved(*load_source(ROOT / 'content/shuidiaogetou-2'))
    binding = next(o for o in pack.objects if o.objectId == 'shadow.main')
    binding.required = False
    resource = next(a for a in manifest.assets if a.asset_id == binding.asset.assetId)
    dependency = manifest.assets[0].model_copy(update={'asset_id': 'synthetic.dependency', 'dependencies': [],
                                                      'status': 'declared'})
    manifest.assets.append(dependency)
    resource.status = 'declared'
    resource.dependencies = [AssetReference(asset_id=dependency.asset_id, asset_version=dependency.asset_version)]
    manifest = ResourceManifest.model_validate(manifest.model_dump())
    report = validate_pack(pack, manifest, release=True)
    assert any(i['code'] == 'ASSET_PENDING' and i['objectId'] == dependency.asset_id for i in report['issues'])


@pytest.mark.parametrize('failure', ['invalid_url', 'scan', 'delete'])
def test_retirement_success_survives_optional_cache_failure(tmp_path, monkeypatch, failure):
    from redis.exceptions import ConnectionError
    from unittest.mock import Mock
    from app import cache
    if failure == 'invalid_url': monkeypatch.setenv('REDIS_URL', 'invalid-secret-canary')
    else:
        client = Mock()
        client.scan_iter.return_value = ['eov:catalog:synthetic']
        getattr(client, 'scan_iter' if failure == 'scan' else 'delete').side_effect = ConnectionError('secret-canary')
        monkeypatch.setattr(cache, '_client', lambda: client)
    path = tmp_path / 'legacy.sqlite3'
    db = legacy_database(path)
    try:
        with db.connect() as connection: original = fingerprint(connection)
        report = retire(str(db.url), tmp_path / 'backups', apply=True)
        assert report['applied'] and report['backupRestoredAndVerified'] and report['unrelatedRowsUnchanged']
        restored = create_engine('sqlite:///' + report['backup'])
        try:
            with restored.connect() as connection: assert fingerprint(connection) == original
        finally: restored.dispose()
        with db.connect() as connection:
            assert connection.exec_driver_sql('SELECT id FROM poems').scalars().all() == ['keep']
    finally: db.dispose()

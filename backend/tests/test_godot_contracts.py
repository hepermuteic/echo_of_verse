import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.client_content import project_client_poem
from app.content import POEM_ID, ROOT, source_dir
from app.demo_content import export_pack, fixtures, load_source, validate_pack, verify_checksums
from app.demo_models import ContentPack, GodotRuntime, JourneySnapshot, Review
from app.main import app
from app.resources import AssetRecord, ResourceManifest
from app.storage import database

SOURCE = ROOT / 'content/shuidiaogetou-3'


@pytest.fixture
def current():
    return load_source(SOURCE)


def ready_asset(kind='scene', fmt='tscn'):
    return dict(asset_id='synthetic.godot', asset_version='2', asset_type=kind, format=fmt,
                delivery='godot_resource', resource_path='res://audit/example.' + fmt,
                status='ready', target_platform='windows', size_bytes=12, sha256='0' * 64,
                source='synthetic test only', license='synthetic test only')


def approved(current):
    pack, manifest = copy.deepcopy(current)
    review = Review(status='reviewed', reviewer='synthetic-test-only', reviewedAt='2026-10-17')
    pack.poem.review = review
    for item in pack.sources:
        item.review = review
    for item in pack.texts:
        item.en = 'Synthetic translation'
        item.reviewZh = item.reviewEn = review
    for item in pack.presentations:
        item.confirmed = True
    for item in pack.parameters:
        item.confirmed = True
    pack.runtime = GodotRuntime(engineVersion='4.5.1', renderer='gl_compatibility', bindingsConfirmed=True)
    for item in manifest.assets:
        item.status, item.license = 'ready', 'synthetic test only'
        item.resource_path = f'res://audit/{item.asset_id}.{item.format}'
        item.size_bytes, item.sha256 = 12, '0' * 64
    return pack, ResourceManifest.model_validate_json(manifest.model_dump_json())


@pytest.mark.parametrize('kind,fmt', [('scene', 'tscn'), ('vfx', 'tscn'), ('model', 'glb'),
    ('material', 'tres'), ('texture', 'png'), ('audio', 'wav'), ('audio', 'ogg'), ('audio', 'mp3')])
def test_godot_resource_formats_and_roundtrip(kind, fmt):
    asset = AssetRecord.model_validate(ready_asset(kind, fmt))
    assert AssetRecord.model_validate_json(asset.model_dump_json()) == asset
    assert asset.resource_path.startswith('res://')
    assert 'unity_version' not in asset.model_dump()


@pytest.mark.parametrize('path', ['assets/file.tscn', 'user://file.tscn', 'http://example.com/file.tscn',
    'C:/file.tscn', 'res://../file.tscn', 'res://a/../file.tscn', 'res://./file.tscn',
    'res:///file.tscn', 'res://a//file.tscn', 'res://a\\file.tscn', 'res://a%2f../file.tscn',
    'res://file.tscn?x=1', 'res://file.tscn#fragment', 'res://C:/file.tscn', 'res://a\nfile.tscn',
    'res://a\x00file.tscn', 'res://file.tscn ', ' res://file.tscn', 'res://file.tscn\n', 42])
def test_noncanonical_resource_paths_are_rejected(path):
    with pytest.raises(ValueError):
        AssetRecord.model_validate({**ready_asset(), 'resource_path': path})


@pytest.mark.parametrize('edit', [dict(asset_type='prefab'), dict(format='unity_prefab'), dict(format='png'),
    dict(resource_path='res://file.glb'), dict(address='old-address'), dict(unity_version='6'),
    dict(render_pipeline='urp'), dict(catalog_url='https://example.com/catalog'),
    dict(source_coordinate_system='unity_left_handed_y_up'), dict(meters_per_unit=1),
    dict(object_location={'provider': 'oss', 'bucket': 'audit', 'object_key': 'file'}),
    dict(resource_path=None), dict(size_bytes=None), dict(sha256=None), dict(license='pending')])
def test_invalid_godot_metadata_rejected(edit):
    with pytest.raises(ValueError):
        AssetRecord.model_validate({**ready_asset(), **edit})


def test_declared_resource_does_not_fabricate_a_path(current):
    pack, manifest = current
    assert source_dir() == SOURCE
    assert pack.runtime.engineVersion is None and pack.runtime.renderer is None
    assert pack.runtime.bindingsConfirmed is False
    assert all(a.status == 'declared' and a.resource_path is None and a.asset_version == '2' for a in manifest.assets)
    report = validate_pack(pack, manifest)
    assert report['ok'] and len(report['issues']) == 67
    assert report['godotResourceContract'] == 'declared'
    assert report['clientImport'] == report['playerAcceptance'] == 'unverified'
    assert not validate_pack(pack, manifest, release=True)['ok']


@pytest.mark.parametrize('field,value', [('engine', 'unity'), ('engineMajor', 3), ('engineVersion', '4.x'),
    ('engineVersion', '3.5'), ('renderer', 'urp'), ('targetPlatform', 'webgl'),
    ('coordinateSystem', 'unity_left_handed_y_up'), ('metersPerUnit', True), ('metersPerUnit', 100),
    ('quaternionOrder', 'wxyz'), ('bindingsConfirmed', 'true')])
def test_runtime_rejects_unsupported_or_ambiguous_values(field, value):
    with pytest.raises(ValueError):
        GodotRuntime.model_validate({field: value})


@pytest.mark.parametrize('field,code', [('engineVersion', 'GODOT_VERSION_PENDING'),
    ('renderer', 'GODOT_RENDERER_PENDING'), ('bindingsConfirmed', 'GODOT_BINDINGS_PENDING')])
def test_runtime_confirmation_blocks_release(current, field, code):
    pack, manifest = approved(current)
    setattr(pack.runtime, field, False if field == 'bindingsConfirmed' else None)
    assert validate_pack(pack, manifest)['ok']
    errors = validate_pack(pack, manifest, release=True)['issues']
    assert {item['code'] for item in errors} == {code}


@pytest.mark.parametrize('case', ['missing-runtime', 'legacy-runtime', 'missing-view', 'manifest-engine',
    'manifest-legacy', 'manifest-new', 'unknown-content', 'unknown-manifest'])
def test_versions_require_matching_profiles(current, case):
    p, m = [item.model_dump(mode='json') for item in current]
    if case == 'missing-runtime': p.pop('runtime')
    if case == 'legacy-runtime': p['schemaVersion'] = '1.1'
    if case == 'missing-view': p.pop('clientPresentation')
    if case == 'manifest-engine': m.pop('engine')
    if case == 'manifest-legacy': m['schema_version'], m['engine'] = '1.0', None
    if case == 'manifest-new': m = load_source(ROOT / 'content/shuidiaogetou-2')[1].model_dump(mode='json'); m.update(schema_version='1.1', engine='godot')
    if case == 'unknown-content': p['schemaVersion'] = '2.0'
    if case == 'unknown-manifest': m['schema_version'] = '1.2'
    with pytest.raises(ValueError):
        ContentPack.model_validate(p)
        ResourceManifest.model_validate(m)


def test_legacy_contracts_serialize_without_new_fields(current, tmp_path):
    for version in ('shuidiaogetou-1', 'shuidiaogetou-2'):
        p, m = load_source(ROOT / 'content' / version)
        assert validate_pack(p, m)['ok']
        assert 'runtime' not in p.model_dump() and 'engine' not in m.model_dump()
        assert all('resource_path' not in a.model_dump() for a in m.assets)
        assert export_pack(p, m, tmp_path)['ok']
        verify_checksums(tmp_path / version)
        assert (tmp_path / version / ('UNITY_MAPPING.md' if p.schemaVersion == '1.0' else 'LEGACY_UNITY_RESOURCE_MAPPING.md')).is_file()
    p, m = current
    old = load_source(ROOT / 'content/shuidiaogetou-2')
    assert 'RESOURCE_PROFILE' in {i['code'] for i in validate_pack(p, old[1])['issues']}
    assert 'RESOURCE_PROFILE' in {i['code'] for i in validate_pack(old[0], m)['issues']}


@pytest.mark.parametrize('case,code', [('direct-platform', 'ASSET_PLATFORM'), ('dependency-platform', 'ASSET_PLATFORM'),
    ('asset-type', 'ASSET_TYPE'), ('version', 'ASSET_MISSING'), ('displayed-text', 'REQUIRED_TEXT'),
    ('required-object', 'REQUIRED_OBJECT')])
def test_semantic_and_security_guards_apply_to_godot(current, case, code):
    p, m = copy.deepcopy(current)
    if case == 'direct-platform': m.assets[1].target_platform = 'linux'
    if case == 'dependency-platform':
        dep = AssetRecord.model_validate({**ready_asset(), 'asset_id': 'extra', 'target_platform': 'linux'})
        m.assets.append(dep)
        from app.resources import AssetReference
        m.assets[1].dependencies.append(AssetReference(asset_id='extra', asset_version='2'))
    if case == 'asset-type': p.objects[0].asset.assetId = 'sdt.ambient'
    if case == 'version': p.objects[0].asset.assetVersion = '1'
    if case == 'displayed-text': next(t for t in p.texts if t.textId == p.events[0].nodeTextId).required = False
    if case == 'required-object': p.objects[0].required = False
    assert code in {i['code'] for i in validate_pack(p, m)['issues']}


def test_native_dependency_cycle_and_ready_dependencies(current):
    _, manifest = current
    raw = manifest.model_dump(mode='json')
    raw['assets'][0]['dependencies'] = [{'asset_id': raw['assets'][1]['asset_id'], 'asset_version': '2'}]
    raw['assets'][1]['dependencies'] = [{'asset_id': raw['assets'][0]['asset_id'], 'asset_version': '2'}]
    with pytest.raises(ValueError): ResourceManifest.model_validate(raw)
    ready = ready_asset()
    ready['dependencies'] = [{'asset_id': manifest.assets[0].asset_id, 'asset_version': '2'}]
    with pytest.raises(ValueError): ResourceManifest(schema_version='1.1', engine='godot', catalog_version='audit', assets=[AssetRecord.model_validate(ready), manifest.assets[0]])


def test_http_offline_projection_and_complete_handoff(current, tmp_path, monkeypatch):
    pack, manifest = current
    monkeypatch.setenv('EOV_CONFIG_FILE', str(ROOT / 'config/services.example.toml'))
    monkeypatch.setenv('EOV_CONTENT_SOURCE', str(SOURCE))
    monkeypatch.setenv('EOV_DB_PATH', str(tmp_path / 'isolated.sqlite3'))
    expected = project_client_poem(load_source(ROOT / 'content/shuidiaogetou-2')[0]).model_dump(mode='json')
    assert project_client_poem(pack).model_dump(mode='json') == expected
    with TestClient(app) as client:
        assert client.get('/openapi.json').json()['info']['version'] == '0.5.0'
        listing = client.get('/api/v1/poems').json()['items'][0]
        assert {key: listing[key] for key in expected} == expected
        assert listing['contentVersion'] == 'shuidiaogetou-3'
        assert client.get('/api/v1/poems/lookup?title=水调歌头').json()['matches'][0]['poem'] == expected
        with database() as db:
            assert db.execute('SELECT id FROM poems').fetchone()[0] == POEM_ID
    assert export_pack(pack, manifest, tmp_path)['ok']
    output = tmp_path / pack.contentVersion
    assert len(list(output.iterdir())) == 17
    assert (output / 'GODOT_MAPPING.md').is_file()
    assert not (output / 'LEGACY_UNITY_RESOURCE_MAPPING.md').exists()
    assert json.loads((output / 'client-poems.json').read_text(encoding='utf-8')) == [expected]
    verify_checksums(output)
    assert load_source(output) == current
    with pytest.raises(FileExistsError): export_pack(pack, manifest, tmp_path)
    (output / 'GODOT_MAPPING.md').unlink()
    checks = json.loads((output / 'checksums.json').read_text())
    del checks['GODOT_MAPPING.md']
    (output / 'checksums.json').write_text(json.dumps(checks))
    with pytest.raises(ValueError): verify_checksums(output)


def test_native_formal_package_and_snapshot_version_isolation(current, tmp_path):
    pack, manifest = approved(current)
    assert export_pack(pack, manifest, tmp_path, release=True)['ok']
    verify_checksums(tmp_path / pack.contentVersion)
    from app.demo_content import evaluate_reflection
    case = fixtures(pack)[0]
    assert evaluate_reflection(pack, JourneySnapshot.model_validate(case['input'])) == case['expected']
    old = JourneySnapshot.model_validate(fixtures(load_source(ROOT / 'content/shuidiaogetou-2')[0])[0]['input'])
    with pytest.raises(ValueError): evaluate_reflection(pack, old)


def test_native_parallel_export_and_atomic_failure(current, tmp_path, monkeypatch):
    pack, manifest = current
    def export(_):
        try: return export_pack(pack, manifest, tmp_path / 'parallel')['ok']
        except FileExistsError: return False
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(export, range(2))) == [False, True]
    verify_checksums(tmp_path / 'parallel' / pack.contentVersion)
    def fail(*args): raise OSError('synthetic rename failure')
    monkeypatch.setattr('app.demo_content.os.rename', fail)
    with pytest.raises(OSError): export_pack(pack, manifest, tmp_path / 'failure')
    assert list((tmp_path / 'failure').iterdir()) == []

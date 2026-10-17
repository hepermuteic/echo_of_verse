"""Offline validation, deterministic reflection and atomic handoff export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from pydantic import ValidationError
from app.content import POEM_ID
from app.demo_models import ContentPack, JourneySnapshot
from app.resources import ResourceManifest, EntityPlacement, resource_compatible
from app.client_content import client_documents, project_client_poem

MAIN = {'act1.cup.confirmed': ('act1', True), 'act2.high.visited': ('act2', False),
        'act2.return.confirmed': ('act2', True), 'act3.shadow.responded': ('act3', True),
        'act3.moon.confirmed': ('act3', True)}

GODOT_MAPPING = '''# Godot 4.x resource contract — ContentPack 1.2 / ResourceManifest 1.1

This is a backend contract, not an imported or playable Godot project.
JSON remains the editable content source. No actual resource path is invented.

| JSON | Godot client responsibility |
|---|---|
| assetId + assetVersion | Resolve exact asset_id + asset_version in ResourceManifest |
| resource_path | Load a delivered res:// resource; missing paths must not be guessed |
| scene / model / vfx | Instantiate delivered scenes/models; verify actual node classes in Godot |
| objects / regions / spawns / environments | Register stable IDs in the actual scene; verify each binding |
| acts | Follow order, environmentId, spawnId and exitEventId; commit before nextAct |
| presentations | Execute sequentially; confirm only after every required completion callback |
| events | Check committed prerequisites; never infer events from displayed lines |
| texts / sources | Preserve language fallback, provenance and human review |
| reflectionRules | Apply priority descending, ruleId ascending; use default when unmatched |

runtime declares right-handed Y-up coordinates, meters and normalized [x,y,z,w] quaternions.
Existing transforms are placeholders, NOT converted scene placements. bindingsConfirmed=false blocks release.
engineVersion and renderer are unconfirmed until supplied by the actual Godot project.
The renderer enum uses forward_plus / mobile / gl_compatibility; Unity settings are not accepted.

res:// content is bundled/read-only at runtime. Client saves/settings belong in user://.
SaveSlot is UI progress only; it is not a complete save, checkpoint or completion record.
Keep unknown old saves; JourneySnapshot only accepts the same contentVersion.
At each act exit, persist committed real events. Reset drops current-act uncommitted records.
Pause, focus loss, loading and settlement must not accumulate dwell or advance the story.
Use reflection-fixtures.json to compare normal/early-return/no-optional results.

Validation checks declarations and references, not resource bytes, scene nodes or engine execution.
ready requires delivered path, byte size, SHA-256 and known rights; it is not proof of engine import.
Godot import, platform export and actual-device offline play remain unverified independently.
'''


def load_source(directory):
    directory = Path(directory)
    pack = ContentPack.model_validate_json((directory / 'content-pack.json').read_text(encoding='utf-8-sig'))
    manifest = ResourceManifest.model_validate_json((directory / 'resource-manifest.json').read_text(encoding='utf-8-sig'))
    return pack, manifest


def validate_pack(pack, manifest, release=False):
    issues = []
    def issue(code, obj, field, message, severity='error'):
        issues.append({'code': code, 'objectId': obj, 'field': field, 'message': message, 'severity': severity})
    def index(items, key):
        result = {}
        for i, item in enumerate(items):
            identity = getattr(item, key)
            if identity in result:
                issue('DUPLICATE_ID', identity, f'{key}[{i}]', 'Duplicate stable identity')
            result[identity] = item
        return result
    def ref(identity, table, obj, field):
        if identity not in table:
            issue('MISSING_REFERENCE', obj, field, f'Unknown identity: {identity}')
            return None
        return table[identity]
    def reviewed(review, obj, field):
        if review.status != 'reviewed':
            issue('UNREVIEWED', obj, field, 'Human review is pending', 'error' if release else 'warning')

    godot = pack.schemaVersion == '1.2'
    if godot != (manifest.schema_version == '1.1'):
        issue('RESOURCE_PROFILE', pack.contentVersion, 'resourceCatalogVersion', 'Content and resource engine profiles differ')
    if godot:
        for field, code in [('engineVersion', 'GODOT_VERSION_PENDING'), ('renderer', 'GODOT_RENDERER_PENDING'),
                            ('bindingsConfirmed', 'GODOT_BINDINGS_PENDING')]:
            if not getattr(pack.runtime, field):
                issue(code, pack.contentVersion, 'runtime.' + field, 'Godot target/binding confirmation is pending',
                      'error' if release else 'warning')

    displayed_texts = set()
    def visible_text(identity, obj, field):
        text = ref(identity, texts, obj, field)
        if text is not None:
            displayed_texts.add(identity)
            if not text.required:
                issue('REQUIRED_TEXT', obj, field, f'Displayed text must be required content: {identity}')
        return text

    acts = index(pack.acts, 'actId'); events = index(pack.events, 'eventId')
    texts = index(pack.texts, 'textId'); sources = index(pack.sources, 'sourceId')
    segments = index(pack.poem.segments, 'segmentId'); objects = index(pack.objects, 'objectId')
    regions = index(pack.regions, 'regionId'); spawns = index(pack.spawns, 'spawnId')
    environments = index(pack.environments, 'environmentId'); presentations = index(pack.presentations, 'presentationId')
    parameters = index(pack.parameters, 'parameterId')
    index(pack.insights, 'insightId'); index(pack.reflectionRules, 'ruleId')
    if pack.poem.poemId != POEM_ID:
        issue('WRONG_DEMO', pack.poem.poemId, 'poem.poemId', 'Only Shuidiaogetou is supported')
    if pack.resourceCatalogVersion != manifest.catalog_version:
        issue('CATALOG_VERSION', pack.contentVersion, 'resourceCatalogVersion', 'Catalog versions differ')
    if len({s.order for s in pack.poem.segments}) != len(pack.poem.segments):
        issue('SEGMENT_ORDER', POEM_ID, 'poem.segments', 'Segment order must be unique')
    if set(acts) != {'act1', 'act2', 'act3'} or sorted(a.order for a in pack.acts) != [1, 2, 3]:
        issue('ACT_ORDER', POEM_ID, 'acts', 'Exactly act1/act2/act3 in that order are required')
    for position, act in enumerate(sorted(pack.acts, key=lambda a: a.order)):
        if act.actId != f'act{position + 1}':
            issue('ACT_ORDER', act.actId, 'order', 'Act ID and order differ')
        expected = f'act{position + 2}' if position < 2 else None
        if act.nextActId != expected:
            issue('ACT_TRANSITION', act.actId, 'nextActId', 'Transition must follow act order')
        ref(act.environmentId, environments, act.actId, 'environmentId')
        spawn = ref(act.spawnId, spawns, act.actId, 'spawnId')
        if spawn and spawn.actId != act.actId:
            issue('BINDING_ACT', act.actId, 'spawnId', 'Spawn belongs to another act')
        exit_event = ref(act.exitEventId, events, act.actId, 'exitEventId')
        expected_exit = ['act1.cup.confirmed', 'act2.return.confirmed', 'act3.moon.confirmed'][position]
        if act.exitEventId != expected_exit or (exit_event and (not exit_event.required or exit_event.actId != act.actId)):
            issue('ACT_EXIT', act.actId, 'exitEventId', 'Incorrect mandatory exit')
    for identity, (act_id, required) in MAIN.items():
        event = ref(identity, events, POEM_ID, 'events')
        if event and (event.actId != act_id or event.required != required):
            issue('MAIN_EVENT', identity, 'actId/required', 'Main event contract mismatch')

    records = {(a.asset_id, a.asset_version): a for a in manifest.assets}
    required_assets = set()
    # Usage, not just a mutable object flag, determines mandatory resource delivery.
    required_objects = set()
    def require_object(identity, obj, field):
        binding = objects.get(identity)
        if binding is not None:
            required_objects.add(identity)
            if not binding.required:
                issue('REQUIRED_OBJECT', obj, field, f'Mandatory usage requires a required object: {identity}')
    for event in pack.events:
        if event.required and event.trigger.kind == 'interact':
            require_object(event.trigger.objectId, event.eventId, 'trigger.objectId')
    for presentation in pack.presentations:
        for step in presentation.steps:
            if step.required and step.objectId:
                require_object(step.objectId, presentation.presentationId, f'steps.{step.stepId}.objectId')
    def asset(reference, obj, field, types=None, required=True):
        key = (reference.assetId, reference.assetVersion)
        record = records.get(key)
        if record is None:
            issue('ASSET_MISSING', obj, field, 'Resource identity/version is not registered')
            return
        if required:
            required_assets.add(key)
        if types and record.asset_type not in types:
            issue('ASSET_TYPE', obj, field, 'Resource type is incompatible with this usage')
        if record.status == 'retired':
            issue('ASSET_RETIRED', obj, field, 'New content cannot reference retired resources')
        if not resource_compatible(record, godot=godot):
            issue('ASSET_PLATFORM', obj, field, 'Resource is incompatible with the content engine/platform profile')
    for binding in pack.objects:
        ref(binding.actId, acts, binding.objectId, 'actId')
        asset(binding.asset, binding.objectId, 'asset', {'scene', 'model', 'vfx'} if godot else {'prefab', 'model', 'vfx'},
              binding.required or binding.objectId in required_objects)
        try:
            EntityPlacement(id=binding.objectId, asset_id=binding.asset.assetId, asset_version=binding.asset.assetVersion,
                            position=binding.position, rotation=binding.rotation, scale=binding.scale)
        except ValueError:
            issue('TRANSFORM', binding.objectId, 'rotation/scale', 'Invalid placement transform')
    for binding in [*pack.regions, *pack.spawns]:
        ref(binding.actId, acts, getattr(binding, 'regionId', getattr(binding, 'spawnId', '')), 'actId')
    for environment in pack.environments:
        for reference in environment.assets:
            asset(reference, environment.environmentId, 'assets')
    for presentation in pack.presentations:
        index(presentation.steps, 'stepId')
        if not any(step.required for step in presentation.steps):
            issue('EMPTY_COMPLETION', presentation.presentationId, 'steps', 'At least one required step is needed')
        if not presentation.confirmed:
            issue('PRESENTATION_PENDING', presentation.presentationId, 'confirmed', 'Sequence has not been approved', 'error' if release else 'warning')
        for step in presentation.steps:
            if step.objectId:
                ref(step.objectId, objects, presentation.presentationId, 'steps.objectId')
            if step.textId:
                visible_text(step.textId, presentation.presentationId, f'steps.{step.stepId}.textId')
            if step.asset:
                asset(step.asset, presentation.presentationId, 'steps.asset', {'audio'} if step.kind == 'audio' else None, step.required)

    graph = {identity: event.prerequisites for identity, event in events.items()}
    for event in pack.events:
        ref(event.actId, acts, event.eventId, 'actId')
        if len(set(event.prerequisites)) != len(event.prerequisites):
            issue('DUPLICATE_DEPENDENCY', event.eventId, 'prerequisites', 'Duplicate prerequisite')
        for identity in event.prerequisites:
            predecessor = ref(identity, events, event.eventId, 'prerequisites')
            if predecessor and event.actId in acts and predecessor.actId in acts:
                if acts[predecessor.actId].order > acts[event.actId].order:
                    issue('CROSS_ACT_DEPENDENCY', event.eventId, 'prerequisites', 'Cannot depend on a later act')
                if predecessor.actId != event.actId and identity != acts[predecessor.actId].exitEventId:
                    issue('CROSS_ACT_DEPENDENCY', event.eventId, 'prerequisites', 'Cross-act dependencies must reference an exit')
        for identity in event.segmentIds:
            ref(identity, segments, event.eventId, 'segmentIds')
        visible_text(event.nodeTextId, event.eventId, 'nodeTextId')
        visible_text(event.explanationTextId, event.eventId, 'explanationTextId')
        presentation = ref(event.presentationId, presentations, event.eventId, 'presentationId')
        if presentation:
            for step in presentation.steps:
                if step.objectId in objects and objects[step.objectId].actId != event.actId:
                    issue('BINDING_ACT', event.eventId, 'presentationId', 'Step object belongs to another act')
        trigger = event.trigger
        binding = ref(trigger.objectId, objects, event.eventId, 'trigger.objectId') if trigger.kind == 'interact' else ref(trigger.regionId, regions, event.eventId, 'trigger.regionId')
        if binding and binding.actId != event.actId:
            issue('BINDING_ACT', event.eventId, 'trigger', 'Trigger belongs to another act')
        if trigger.kind == 'horizontal_movement':
            parameter = ref(trigger.parameterId, parameters, event.eventId, 'trigger.parameterId')
            if parameter and parameter.unit != 'meters':
                issue('PARAMETER_UNIT', event.eventId, 'trigger.parameterId', 'Movement threshold must be meters')
    remaining = {identity: set(deps) & graph.keys() for identity, deps in graph.items()}
    followers = {identity: [] for identity in graph}
    for identity, deps in remaining.items():
        for dep in deps:
            followers[dep].append(identity)
    ready = [identity for identity, deps in remaining.items() if not deps]
    traversed = set()
    while ready:
        identity = ready.pop(); traversed.add(identity)
        for following in followers[identity]:
            remaining[following].discard(identity)
            if not remaining[following]:
                ready.append(following)
    for identity in sorted(set(graph) - traversed):
        issue('EVENT_CYCLE', identity, 'prerequisites', 'Cyclic or blocked event dependencies')
    def ancestors(identity):
        seen, pending = set(), list(graph.get(identity, []))
        while pending:
            dep = pending.pop()
            if dep not in seen:
                seen.add(dep); pending.extend(graph.get(dep, []))
        return seen
    if 'act2.high.visited' in ancestors('act2.return.confirmed'):
        issue('EARLY_RETURN_BLOCKED', 'act2.return.confirmed', 'prerequisites', 'Early return must not require high visit')
    if 'act3.shadow.responded' not in ancestors('act3.moon.confirmed'):
        issue('MOON_DEPENDENCY', 'act3.moon.confirmed', 'prerequisites', 'Moon requires shadow response')
    for event in pack.events:
        if event.required:
            if any(dep in events and not events[dep].required for dep in ancestors(event.eventId)):
                issue('OPTIONAL_BLOCKS_REQUIRED', event.eventId, 'prerequisites', 'Mandatory progress cannot depend on optional exploration')
            if event.actId in acts:
                exit_id = acts[event.actId].exitEventId
                if event.eventId != exit_id and event.eventId not in ancestors(exit_id):
                    issue('REQUIRED_UNREACHABLE_EXIT', event.eventId, 'actId', 'Act exit must depend on every mandatory event in its act')
    for identity, (act_id, _) in MAIN.items():
        previous = {'act2': 'act1.cup.confirmed', 'act3': 'act2.return.confirmed'}.get(act_id)
        if identity in events and previous and previous not in ancestors(identity):
            issue('ACT_ENTRY_DEPENDENCY', identity, 'prerequisites', 'Missing preceding act exit')
    for insight in pack.insights:
        visible_text(insight.textId, insight.insightId, 'textId')
    default_text = visible_text(pack.defaultReflectionTextId, POEM_ID, 'defaultReflectionTextId')
    for rule in pack.reflectionRules:
        visible_text(rule.textId, rule.ruleId, 'textId')
    view = pack.clientPresentation
    if view is not None:
        for i, imagery in enumerate(view.imagery):
            for field in ('lineTextId', 'clipTextId', 'noteTextId', 'sourceTextId'):
                visible_text(getattr(imagery, field), POEM_ID, f'clientPresentation.imagery[{i}].{field}')
        if view.noteTextId:
            visible_text(view.noteTextId, POEM_ID, 'clientPresentation.noteTextId')
    for text in pack.texts:
        for identity in text.experienceEventIds:
            ref(identity, events, text.textId, 'experienceEventIds')
        for identity in text.sourceIds:
            ref(identity, sources, text.textId, 'sourceIds')
        if text.required or text.textId in displayed_texts:
            reviewed(text.reviewZh, text.textId, 'reviewZh')
        if text.requiresEnglish and not text.en:
            issue('ENGLISH_MISSING', text.textId, 'en', 'Required English translation missing', 'error' if release else 'warning')
        if text.en and (text.required or text.textId in displayed_texts or text.requiresEnglish):
            reviewed(text.reviewEn, text.textId, 'reviewEn')
    reviewed(pack.poem.review, POEM_ID, 'poem.review')
    for identity in pack.poem.sourceIds:
        ref(identity, sources, POEM_ID, 'sourceIds')
    for source in pack.sources:
        reviewed(source.review, source.sourceId, 'review')
    for parameter in pack.parameters:
        if not parameter.confirmed:
            issue('PARAMETER_PENDING', parameter.parameterId, 'confirmed', 'Playtest approval pending', 'error' if release else 'warning')
    for insight in pack.insights:
        for identity in insight.segmentIds:
            ref(identity, segments, insight.insightId, 'segmentIds')
    if default_text and default_text.experienceEventIds:
        issue('DEFAULT_CLAIM', default_text.textId, 'experienceEventIds', 'Default message must not claim optional experience')
    for event in pack.events:
        guaranteed = ancestors(event.eventId) | {event.eventId}
        for text_id in (event.nodeTextId, event.explanationTextId):
            if text_id in texts and not set(texts[text_id].experienceEventIds) <= guaranteed:
                issue('UNSUPPORTED_EXPERIENCE', event.eventId, 'nodeTextId/explanationTextId', 'Node text claims an experience not guaranteed by this event')
    for rule in pack.reflectionRules:
        guaranteed = set(rule.when.allEvents)
        if len(rule.when.anyEvents) == 1:
            guaranteed.update(rule.when.anyEvents)
        guaranteed |= {dep for identity in list(guaranteed) for dep in ancestors(identity)}
        if rule.textId in texts and not set(texts[rule.textId].experienceEventIds) <= guaranteed:
            issue('UNSUPPORTED_EXPERIENCE', rule.ruleId, 'when', 'Rule does not guarantee claimed experiences')
        for identity in [*rule.when.allEvents, *rule.when.anyEvents, *rule.when.absentEvents]:
            ref(identity, events, rule.ruleId, 'when')
        if set(rule.when.allEvents) & set(rule.when.absentEvents):
            issue('RULE_CONTRADICTION', rule.ruleId, 'when', 'Required and absent events overlap')
        for dwell in rule.when.dwellMin:
            ref(dwell.regionId, regions, rule.ruleId, 'when.dwellMin.regionId')
            parameter = ref(dwell.parameterId, parameters, rule.ruleId, 'when.dwellMin.parameterId')
            if parameter and parameter.unit != 'seconds':
                issue('PARAMETER_UNIT', rule.ruleId, 'when.dwellMin', 'Dwell threshold must be seconds')
    queue = list(required_assets)
    while queue:
        key = queue.pop()
        for dep in records[key].dependencies:
            dep_key = (dep.asset_id, dep.asset_version)
            if dep_key not in required_assets:
                required_assets.add(dep_key); queue.append(dep_key)
    for key in sorted(required_assets):
        record = records[key]
        if not resource_compatible(record, godot=godot):
            issue('ASSET_PLATFORM', key[0], 'dependencies', 'Required dependencies must match the content engine/platform profile')
        if records[key].status != 'ready':
            issue('ASSET_PENDING', key[0], 'status', 'Required resource is not delivered', 'error' if release else 'warning')
    covered = sum(bool(text.en) for text in pack.texts)
    if pack.clientPresentation is not None:
        try:
            project_client_poem(pack)
        except (ValueError, KeyError) as exc:
            issue('CLIENT_PRESENTATION_INVALID', POEM_ID, 'clientPresentation', str(exc))
    return {'ok': not any(i['severity'] == 'error' for i in issues), 'contentVersion': pack.contentVersion,
            'target': 'release' if release else 'draft', 'issues': issues,
            'englishCoverage': {'covered': covered, 'total': len(pack.texts), 'missing': [t.textId for t in pack.texts if not t.en]},
            'clientImport': 'unverified', 'godotResourceContract': 'declared' if godot else 'pending', 'playerAcceptance': 'unverified'}


def evaluate_reflection(pack, snapshot):
    if snapshot.contentVersion != pack.contentVersion:
        raise ValueError('Snapshot content version mismatch')
    definitions = {e.eventId: e for e in pack.events}
    ordered_acts = sorted(pack.acts, key=lambda act: act.order)
    act_index = 0
    events, previous = set(), -1
    for item in snapshot.committedEvents:
        if item.eventId not in definitions or item.eventId in events or item.sequence <= previous:
            raise ValueError('Unknown/duplicate event or invalid confirmation order')
        if not set(definitions[item.eventId].prerequisites) <= events:
            raise ValueError('Event prerequisites were not committed earlier')
        if act_index >= len(ordered_acts) or definitions[item.eventId].actId != ordered_acts[act_index].actId:
            raise ValueError('Event is outside the active act or was confirmed after its exit')
        previous = item.sequence; events.add(item.eventId)
        if item.eventId == ordered_acts[act_index].exitEventId:
            act_index += 1
    if snapshot.completed and not {e.eventId for e in pack.events if e.required} <= events:
        raise ValueError('Completed snapshot lacks required events')
    regions = {r.regionId for r in pack.regions}
    dwell = {}
    for item in snapshot.regionDwell:
        if item.regionId not in regions or item.regionId in dwell:
            raise ValueError('Unknown/duplicate dwell region')
        dwell[item.regionId] = item.effectiveSeconds
    parameters = {p.parameterId: p for p in pack.parameters}
    texts = {t.textId: t for t in pack.texts}
    def matches(rule):
        condition = rule.when
        return (set(condition.allEvents) <= events and (not condition.anyEvents or bool(set(condition.anyEvents) & events))
                and not set(condition.absentEvents) & events
                and all(dwell.get(c.regionId, 0) >= parameters[c.parameterId].value for c in condition.dwellMin))
    selected = next((r for r in sorted(pack.reflectionRules, key=lambda r: (-r.priority, r.ruleId)) if matches(r)), None)
    def render(identity):
        text = texts[identity]
        return {'textId': identity, 'zh': text.zh, 'en': text.en or text.zh, 'englishFallback': text.en is None}
    return {'contentVersion': pack.contentVersion, 'journeyId': snapshot.journeyId,
            'nodes': [{'eventId': item.eventId, 'sequence': item.sequence, 'segmentIds': definitions[item.eventId].segmentIds,
                       'node': render(definitions[item.eventId].nodeTextId), 'explanation': render(definitions[item.eventId].explanationTextId)}
                      for item in snapshot.committedEvents],
            'ruleId': selected.ruleId if selected else None,
            'message': render(selected.textId if selected else pack.defaultReflectionTextId)}


def fixtures(pack):
    routes = [('normal', ['act1.cup.confirmed', 'act2.high.visited', 'act2.return.confirmed', 'act3.shadow.responded', 'act3.moon.confirmed']),
              ('early-return', ['act1.cup.confirmed', 'act2.return.confirmed', 'act3.shadow.responded', 'act3.moon.confirmed']),
              ('no-optional', ['act1.cup.confirmed', 'act2.return.confirmed', 'act3.shadow.responded', 'act3.moon.confirmed'])]
    result = []
    for name, route in routes:
        snapshot = JourneySnapshot(contentVersion=pack.contentVersion, journeyId='fixture.' + name, completed=True,
                                   committedEvents=[{'eventId': identity, 'sequence': i} for i, identity in enumerate(route)])
        result.append({'name': name, 'synthetic': True, 'input': snapshot.model_dump(mode='json'), 'expected': evaluate_reflection(pack, snapshot)})
    return result


def verify_checksums(directory):
    directory = Path(directory)
    checks = json.loads((directory / 'checksums.json').read_text(encoding='utf-8'))
    if not isinstance(checks, dict) or not checks or 'checksums.json' in checks:
        raise ValueError('Invalid checksum manifest')
    # A self-consistent subset is still an incomplete handoff.
    required = {'content-pack.json', 'content-pack.schema.json', 'resource-manifest.json',
                'resource-manifest.schema.json', 'journey-snapshot.schema.json', 'validation-report.json',
                'reflection-fixtures.json', 'RELEASE_NOTES.md', 'ACCEPTANCE.md', 'UNITY_MAPPING.md'}
    content = json.loads((directory / 'content-pack.json').read_text(encoding='utf-8-sig'))
    if not isinstance(content, dict) or content.get('schemaVersion') not in ('1.0', '1.1', '1.2'):
        raise ValueError('Unsupported handoff schema version')
    if content['schemaVersion'] in ('1.1', '1.2'):
        required.remove('UNITY_MAPPING.md')
        mapping = 'GODOT_MAPPING.md' if content['schemaVersion'] == '1.2' else 'LEGACY_UNITY_RESOURCE_MAPPING.md'
        required.update({mapping, 'CLIENT_MAPPING.md', 'client-poems.json',
                         'client-poem.schema.json', 'client-save-slot.schema.json', 'client-settings.schema.json',
                         'client-default-settings.json'})
    if set(checks) != required:
        raise ValueError('Incomplete handoff file set')
    actual = {p.name for p in directory.iterdir() if p.is_file() and p.name != 'checksums.json'}
    if actual != set(checks):
        raise ValueError('Checksum manifest does not cover every file')
    for name, digest in checks.items():
        if Path(name).name != name or hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Checksum mismatch')


def export_pack(pack, manifest, output, release=False):
    report = validate_pack(pack, manifest, release)
    if not report['ok']:
        return report
    output = Path(output)
    # IDs are identities, never filesystem path components.
    if pack.contentVersion in ('.', '..') or any(c in pack.contentVersion for c in '/\\:'):
        raise ValueError('Content version must be a portable directory name')
    output.mkdir(parents=True, exist_ok=True)
    destination = output / pack.contentVersion
    if destination.exists():
        raise FileExistsError('Content version already exists; refusing overwrite')
    temporary = Path(tempfile.mkdtemp(prefix='.handoff-', dir=output))
    try:
        exported = pack.model_copy(update={'publication': 'released' if release else 'draft'})
        documents = {'content-pack.json': exported.model_dump(mode='json'), 'content-pack.schema.json': ContentPack.model_json_schema(),
                     'resource-manifest.json': manifest.model_dump(mode='json'), 'resource-manifest.schema.json': ResourceManifest.model_json_schema(),
                     'journey-snapshot.schema.json': JourneySnapshot.model_json_schema(), 'validation-report.json': report,
                     'reflection-fixtures.json': fixtures(pack)}
        if pack.clientPresentation is not None:
            documents.update(client_documents(pack))
        for name, value in documents.items():
            (temporary / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        mapping = '''# Unity mapping — ContentPack 1.0

JSON is the only editable content source. Generated ScriptableObjects must not be edited manually.

| JSON | Unity responsibility |
|---|---|
| poem / segments | PoemDefinition; preface separate; segmentId is semantic identity, not UI row |
| acts | ActDefinition; ordered environmentId, spawnId and exitEventId; commit before nextAct |
| objects | objectId registry; assetId+assetVersion -> builtin address; placement in meters, xyzw quaternion |
| regions / spawns / environments | stable scene registries; validate actual bindings in Editor |
| presentations | run steps sequentially; all required completion callbacks before event confirmation |
| events | EventDefinition; prerequisites require confirmed events; act commit makes records visible to reflection |
| parameters | provisional values cannot enter formal release until confirmed |
| texts / insights / sources | stable text keys, language fallback, separate review and provenance |
| reflectionRules | deterministic conditions; priority descending, ruleId ordinal ascending; default fallback |
| JourneySnapshot | committed events in increasing sequence; effective dwell excludes pause, focus loss, loading and settlement |

ResourceManifest retains snake_case. Map assetId/assetVersion explicitly to asset_id/asset_version.
Reject unsupported schemaVersion. Unity owns SaveEnvelope versions and retains unknown old saves.
Resume committed checkpoints without replaying completion. Reset discards current-act uncommitted records.
Only confirmed, committed events enter reflection. No network request is needed during Player runtime.
Python reflection-fixtures are the reference outputs. Unity import, callback ordering, collisions, audio and Player execution are unverified.
'''
        resource_mapping = 'UNITY_MAPPING.md'
        if pack.clientPresentation is not None:
            resource_mapping = 'LEGACY_UNITY_RESOURCE_MAPPING.md'
            mapping = '# Legacy resource contract — NOT a Godot import contract\n\nGodot resource formats and actual bindings remain pending.\n\n' + mapping
            client_mapping = '''# Client field mapping 1.0

Client Poem fields follow frontend commit e24415f2f5784df287fa20cb56b786e3e3c13e2f.
client-poems.json is an array of Poem objects. HTTP items and matches[].poem use the same projection.
Public id shuidiaogetou maps only to internal su_shi.shuidiaogetou; the database is not renamed.
stanzas uses clientPresentation.stanzaSegmentIds in order; acts {n,t} binds actId and its title.
imagery text references resolve from texts; art is a client display key, not a Godot resource path.
Absent optional fields are omitted, not null. Review/status metadata is supplied separately by HTTP or validation-report.json.

SaveSlot (poemId,lineIndex,act,savedAt) describes UI progress only. act is 0..2, not act1/act2/act3.
It is NOT a complete game save or JourneySnapshot. Never synthesize committed events or completion from lineIndex.
Keep old saves intact; any migration to real checkpoints requires a client compatibility table.
Settings and saves are local to the client; there are no server persistence endpoints.
Client settings indices: size=small/medium/large, sub=Chinese/English/bilingual, quality=standard/high/ultra.
Read client-default-settings.json; runtime settings application and storage failure handling belong to the client.

Full ContentPack 1.1 still owns events, prerequisites, presentations and reflection rules.
Only committed real events enter JourneySnapshot and reflection-fixtures.json. Imagery clip is authored display copy, not evidence of actual play.
Godot import, resource migration and Windows offline acceptance remain unverified; legacy Unity resources are not converted.
'''
            if pack.runtime is not None:
                resource_mapping = 'GODOT_MAPPING.md'
                mapping = GODOT_MAPPING
                client_mapping = client_mapping.replace('Full ContentPack 1.1', 'Full ContentPack 1.2').replace(
                    'Godot import, resource migration and Windows offline acceptance remain unverified; legacy Unity resources are not converted.',
                    'Godot resource contract is declared. Engine version, renderer, paths and bindings remain pending; actual import and offline acceptance are unverified.')
            (temporary / 'CLIENT_MAPPING.md').write_text(client_mapping, encoding='utf-8')
        (temporary / resource_mapping).write_text(mapping, encoding='utf-8')
        notes = f'# {pack.contentVersion}\n\nStatus: {exported.publication}. ContentPack schema {pack.schemaVersion}; JourneySnapshot and ResourceManifest remain 1.0.\n\nOnly Shuidiaogetou; no server tasks/sessions/reports. Save compatibility: same content version only until the client supplies an explicit migration table.\n\nGodot resources are not adapted. Backend validation does not imply client acceptance.\n'
        acceptance = '# Acceptance\n\n- Backend structural validation: passed\n- Literary/English review: see validation-report\n- Resource delivery: see manifest\n- Godot resource contract: pending (legacy Unity metadata)\n- Client import: unverified\n- Windows normal/early-return/checkpoint/offline acceptance: unverified\n'
        if pack.runtime is not None:
            notes = notes.replace('JourneySnapshot and ResourceManifest remain 1.0', 'ResourceManifest schema 1.1; JourneySnapshot remains 1.0').replace(
                'Godot resources are not adapted.', 'Godot 4.x Windows resource contract declared; actual resources and engine acceptance are unverified.')
            acceptance = acceptance.replace('pending (legacy Unity metadata)', 'declared; exact engine version, renderer and binding confirmation: see runtime')
        (temporary / 'RELEASE_NOTES.md').write_text(notes, encoding='utf-8')
        (temporary / 'ACCEPTANCE.md').write_text(acceptance, encoding='utf-8')
        load_source(temporary)
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(temporary.iterdir())}
        (temporary / 'checksums.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
        verify_checksums(temporary)
        # Reserve the version separately, then atomically rename the complete directory.
        lock = output / ('.publish-' + hashlib.sha256(pack.contentVersion.encode()).hexdigest() + '.lock')
        reservation = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(reservation)
        try:
            if destination.exists():
                raise FileExistsError('Content version already exists; refusing overwrite')
            os.rename(temporary, destination)
        finally:
            lock.unlink()
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    report['output'] = str(destination.resolve())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline Shuidiaogetou content tooling')
    parser.add_argument('command', choices=['validate', 'export', 'release'])
    parser.add_argument('--source', required=True)
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    if args.command != 'validate' and not args.output:
        parser.error('--output is required for export/release')
    try:
        pack, manifest = load_source(args.source)
        report = validate_pack(pack, manifest, args.command == 'release') if args.command == 'validate' else export_pack(pack, manifest, args.output, args.command == 'release')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    except ValidationError as exc:
        print(json.dumps({'ok': False, 'issues': [{'code': 'STRUCTURE', 'objectId': None, 'field': list(e['loc']), 'message': e['msg'], 'severity': 'error'} for e in exc.errors()]}, ensure_ascii=False))
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'ok': False, 'code': 'FILE_OR_COMMAND', 'message': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

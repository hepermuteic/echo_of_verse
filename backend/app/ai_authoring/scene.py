"""Poem-to-Realm: real LLM scene blueprints compiled to unreviewed Godot content drafts."""
from pathlib import Path
from typing import Literal

from pydantic import Field

from app.ai_authoring.models import (AnalysisReport, DIMENSIONS, Id, Strict, Text, Usage, ValidationReport, SEGMENTS)
from app.ai_authoring.provider import AuthoringError
from app.ai_authoring.retrieval import digest
from app.ai_authoring.service import (batches, citations_valid, messages, originals, verify_analysis)
from app.demo_content import validate_pack
from app.demo_models import ContentPack, Review, SourceEntry, TextEntry


class SceneObject(Strict):
    objectId: Id
    position: list[float] = Field(min_length=3, max_length=3)
    role: Text


class SceneSound(Strict):
    assetId: Id
    direction: Text


class SceneEvent(Strict):
    eventId: Id
    narration: str = Field(min_length=1, max_length=1000)
    audiovisualCue: Text


class SceneInteraction(Strict):
    eventId: Id
    action: Text


class SceneAct(Strict):
    actId: Id
    title: str = Field(min_length=1, max_length=128)
    segmentIds: list[Id] = Field(min_length=1, max_length=8)
    time: Text
    weather: Text
    location: Text
    emotion: Text
    visualPrompt: Text
    sounds: list[SceneSound] = Field(min_length=1, max_length=4)
    objects: list[SceneObject] = Field(min_length=1, max_length=10)
    events: list[SceneEvent] = Field(min_length=1, max_length=5)
    interactions: list[SceneInteraction] = Field(min_length=1, max_length=5)


class SceneReport(Strict):
    schemaVersion: Literal['1.0'] = '1.0'
    publication: Literal['draft'] = 'draft'
    humanReview: Literal['unreviewed'] = 'unreviewed'
    creativeStatus: Literal['game_creation_not_historical_record'] = 'game_creation_not_historical_record'
    engineImportStatus: Literal['unverified'] = 'unverified'
    poemId: Literal['su_shi.shuidiaogetou'] = 'su_shi.shuidiaogetou'
    contentVersion: Id
    contentDigest: str
    corpusDigest: str
    analysisDigest: str
    validationDigest: str
    promptVersion: Literal['sdt-scene-1'] = 'sdt-scene-1'
    model: str
    factualConstraints: list[dict]
    excludedClaims: list[str]
    acts: list[SceneAct] = Field(min_length=3, max_length=3)
    usage: list[Usage]


class ActResult(Strict):
    scene: SceneAct


class SceneAuditDecision(Strict):
    conforms: bool
    issues: list[str] = Field(max_length=40)


class SceneAuditReport(SceneAuditDecision):
    schemaVersion: Literal['1.0'] = '1.0'
    humanReview: Literal['unreviewed'] = 'unreviewed'
    sceneDigest: str
    validationDigest: str
    model: str
    promptVersion: Literal['sdt-scene-audit-1'] = 'sdt-scene-audit-1'
    usage: list[Usage]


ACT_SEGMENTS = {'act1': list(SEGMENTS[:2]), 'act2': list(SEGMENTS[2:3]), 'act3': list(SEGMENTS[3:])}


def verify_validation(report, pack, retrieval):
    if (report.contentVersion != pack.contentVersion or report.contentDigest != digest(pack.model_dump(mode='json'))
            or report.corpusDigest != retrieval.corpus_digest):
        raise AuthoringError('VALIDATION_SOURCE_MISMATCH')
    anchors = {key: [text] for key, text in originals(pack).items()}
    anchors.update({t.textId: [t.zh, *([t.en] if t.en else [])] for t in pack.texts})
    for entry in report.entries:
        claim = entry.claim
        if claim.targetId not in anchors or (claim.sourceQuote and not any(claim.sourceQuote in t for t in anchors[claim.targetId])):
            raise AuthoringError('INVALID_CLAIM_ANCHOR')
        expected = retrieval.search(claim.text + ('\n' + claim.sourceQuote if claim.sourceQuote else ''))
        # Relevant legacy score rounding is not provenance; compare identity, text and metadata.
        strip = lambda rows: [{k: v for k, v in e.items() if k != 'score'} for e in rows]
        if strip(entry.evidence) != strip(expected):
            raise AuthoringError('VALIDATION_EVIDENCE_MISMATCH')
        citations_valid(entry.verdict.citations, expected)


def verify_scene_act(scene, pack, manifest):
    if scene.actId not in ACT_SEGMENTS or scene.segmentIds != ACT_SEGMENTS[scene.actId]:
        raise ValueError('SCENE_SEGMENT_COVERAGE')
    if '未明示' not in scene.weather:
        raise ValueError('SCENE_WEATHER_MUST_MARK_UNSPECIFIED')
    wanted_objects = {o.objectId for o in pack.objects if o.actId == scene.actId}
    wanted_events = {e.eventId for e in pack.events if e.actId == scene.actId}
    for values, wanted, field in (([o.objectId for o in scene.objects], wanted_objects, 'OBJECTS'),
                                  ([e.eventId for e in scene.events], wanted_events, 'EVENTS'),
                                  ([i.eventId for i in scene.interactions], wanted_events, 'INTERACTIONS')):
        if len(values) != len(set(values)) or set(values) != wanted:
            raise ValueError('SCENE_' + field + '_COVERAGE')
    sounds = {a.asset_id for a in manifest.assets if a.asset_type == 'audio'}
    if any(s.assetId not in sounds for s in scene.sounds):
        raise ValueError('SCENE_AUDIO_REFERENCE')
    import math
    if any(not math.isfinite(v) or abs(v) > 1000 for o in scene.objects for v in o.position):
        raise ValueError('SCENE_POSITION_INVALID')


def generate_scene(pack, manifest, retrieval, analysis, validation, provider):
    if pack.schemaVersion != '1.2' or pack.runtime is None or manifest.schema_version != '1.1' or manifest.engine != 'godot':
        raise AuthoringError('SCENE_REQUIRES_GODOT_CONTENT_PROFILE')
    verify_analysis(analysis, pack, retrieval)
    verify_validation(validation, pack, retrieval)
    # A scene may creatively interpret the poem, but never adopt a contradicted historical fact.
    supported = [e for e in validation.entries if e.verdict.status == 'supported']
    constraints = [{'claimId': e.claim.claimId, 'text': e.claim.text,
                    'citations': [c.model_dump() for c in e.verdict.citations]} for e in supported]
    excluded = [e.claim.text for e in validation.entries if e.verdict.status in ('contradicted', 'conflicting', 'insufficient')]
    units = {u.unitId: {'unitId': u.unitId, 'paraphrase': u.paraphrase.value,
             'emotionChange': u.emotionChange.value,
             **{d: [{'value': v.value, 'basis': v.basis} for v in getattr(u, d)] for d in DIMENSIONS}} for u in analysis.units}
    acts = []
    start = len(provider.usage)
    for act in sorted(pack.acts, key=lambda a: a.order):
        segments = ACT_SEGMENTS[act.actId]
        objects = [o.model_dump(mode='json') for o in pack.objects if o.actId == act.actId]
        events = [e.model_dump(mode='json') for e in pack.events if e.actId == act.actId]
        relevant = [{'claimId': c['claimId'], 'text': c['text'],
                     'citationIds': [q['chunkId'] for q in c['citations']]} for c, e in zip(constraints, supported)
                    if e.claim.targetId in segments or e.claim.targetId == 'preface']
        data = {'act': act.model_dump(), 'requiredSegmentIds': segments,
                'poemSegments': [{'segmentId': s, 'text': originals(pack)[s]} for s in segments],
                'analysis': [units[s] for s in segments],
                'factConstraints': relevant, 'objects': objects, 'events': events,
                'audioAssets': [{'assetId': a.asset_id, 'status': a.status} for a in manifest.assets if a.asset_type == 'audio']}
        prompt = messages('生成可由游戏端消费的诗境Scene Schema，不是文学解析报告。输出scene对象，含time/weather/location/emotion、visualPrompt、sounds、objects、events、interactions。所有内容是游戏创作草稿，不是历史实录。原词未明示天气时weather必须注明“原词未明示；创作建议…”。保留指定actId、segmentIds、全部objectId、eventId，不发明资源ID或文件路径。为每个对象提出米制position[x,y,z]，为每个现有事件生成narration和audiovisualCue，并为每个事件设计interaction.action；事件触发器、前置和必需/可选性质不改。想象中的月宫不能说成苏轼实际登月。只采用factConstraints中的文化事实，其余新增细节明确为创作建议。不要声称资源已交付、位置已绑定、玩家已通关或Godot已验收。',
                          data, ActResult.model_json_schema())
        # Scene generation cannot truncate validated source context silently.
        list(batches([data], lambda _: prompt, 1))
        def check(value):
            result = ActResult.model_validate(value).scene
            if result.actId != act.actId:
                raise ValueError('SCENE_ACT_ID')
            verify_scene_act(result, pack, manifest)
            return result
        acts.append(provider.structured(prompt, check))
    return SceneReport(contentVersion=pack.contentVersion, contentDigest=digest(pack.model_dump(mode='json')),
                       corpusDigest=retrieval.corpus_digest, analysisDigest=digest(analysis.model_dump(mode='json')),
                       validationDigest=digest(validation.model_dump(mode='json')), model=provider.config.model,
                       factualConstraints=constraints, excludedClaims=excluded, acts=acts, usage=provider.usage[start:])


def audit_scene(scene, pack, validation, provider):
    data = {'acts': [a.model_dump() for a in scene.acts],
            'supportedFacts': [{'claimId': c['claimId'], 'text': c['text']} for c in scene.factualConstraints],
            'poem': originals(pack),
            'constraints': '这是宋代苏轼单作品的游戏创作，月宫是文学想象。天气未明示；资源仍declared；坐标为待绑定建议；实际玩家事件和Godot验收未发生。'}
    prompt = messages('校验新生成的场景，而非原有文案。检查时代、器物、文化和文学想象有无错误：不得宣称真实登月、杜撰历史事实、使用明显现代器物冒充宋代、声称资源交付或Godot验收。明确为游戏创作的云阶、环境音和角色演出允许作为创意，不应误判为历史断言。仅当未发现上述问题时conforms=true且issues=[]；有问题列出actId和具体原因，conforms=false。',
                      data, SceneAuditDecision.model_json_schema())
    start = len(provider.usage)
    def check(raw):
        result = SceneAuditDecision.model_validate(raw)
        if result.conforms == bool(result.issues):
            raise ValueError('SCENE_AUDIT_CONTRADICTION')
        return result
    result = provider.structured(prompt, check)
    return SceneAuditReport(**result.model_dump(), sceneDigest=digest(scene.model_dump(mode='json')),
                            validationDigest=digest(validation.model_dump(mode='json')), model=provider.config.model,
                            usage=provider.usage[start:])


def compile_scene(scene, pack, manifest, audit):
    if pack.schemaVersion != '1.2' or pack.runtime is None:
        raise AuthoringError('SCENE_REQUIRES_GODOT_CONTENT_PROFILE')
    if (not audit.conforms or audit.issues or audit.sceneDigest != digest(scene.model_dump(mode='json'))
            or audit.validationDigest != scene.validationDigest):
        raise AuthoringError('SCENE_CULTURAL_AUDIT_FAILED')
    if scene.contentDigest != digest(pack.model_dump(mode='json')):
        raise AuthoringError('SCENE_SOURCE_MISMATCH')
    if [a.actId for a in scene.acts] != ['act1', 'act2', 'act3']:
        raise AuthoringError('SCENE_ACT_COVERAGE')
    candidate = pack.model_copy(deep=True)
    candidate.contentVersion = 'shuidiaogetou-ai-' + digest(scene.model_dump(mode='json'))[:12]
    candidate.publication = 'draft'
    candidate.runtime.bindingsConfirmed = False
    source_id = 'ai.scene.generated'
    if any(s.sourceId == source_id for s in candidate.sources):
        raise AuthoringError('AI_SOURCE_ID_COLLISION')
    candidate.sources.append(SourceEntry(sourceId=source_id, kind='creation', title='LLM 诗境生成草稿',
                            editionOrCredit=f'DeepSeek {scene.model}; {scene.promptVersion}; human review pending',
                            locator='scene-blueprint.json; not historical evidence'))
    text_table = {t.textId: t for t in candidate.texts}
    object_table = {o.objectId: o for o in candidate.objects}
    event_table = {e.eventId: e for e in candidate.events}
    for act in scene.acts:
        verify_scene_act(act, candidate, manifest)
        for obj in act.objects:
            object_table[obj.objectId].position = tuple(obj.position)
        for event in act.events:
            text = text_table[event_table[event.eventId].nodeTextId]
            if text.contentType != 'game_creation':
                raise AuthoringError('REFUSING_NONCREATIVE_TEXT_REWRITE')
            text.zh = event.narration
            text.en = None
            text.sourceIds = [source_id]
            text.reviewZh = Review()
            text.reviewEn = Review()
        # Retain the model's art/sound/environment instructions in the machine-readable pack.
        for suffix, value in [('visual', act.visualPrompt), ('audio', '\n'.join(s.direction for s in act.sounds)),
                              ('setting', f'游戏创作草稿：{act.title}；时间：{act.time}；天气：{act.weather}；地点：{act.location}；情绪：{act.emotion}')]:
            candidate.texts.append(TextEntry(textId=f'ai.scene.{act.actId}.{suffix}', zh=value,
                                   contentType='game_creation', sourceIds=[source_id], required=True))
    for presentation in candidate.presentations:
        presentation.confirmed = False
    # Reparse changed payloads and reuse the established reference/resource validator.
    candidate = ContentPack.model_validate_json(candidate.model_dump_json())
    report = validate_pack(candidate, manifest)
    if not report['ok']:
        raise AuthoringError('GENERATED_CONTENT_INVALID')
    return candidate, report

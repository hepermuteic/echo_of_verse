"""Offline LLM poetic feedback, anchored only to a supplied validated JourneySnapshot."""
from typing import Literal

from pydantic import Field

from app.ai_authoring.models import Id, Strict, Text, Usage
from app.ai_authoring.provider import AuthoringError
from app.ai_authoring.retrieval import digest
from app.ai_authoring.service import messages
from app.demo_content import evaluate_reflection


class FeedbackNode(Strict):
    eventId: Id
    segmentIds: list[Id] = Field(min_length=1, max_length=8)
    poeticExplanation: Text
    emotionalInterpretation: Text


class FeedbackBody(Strict):
    nodes: list[FeedbackNode] = Field(max_length=5)


class FeedbackReport(FeedbackBody):
    schemaVersion: Literal['1.0'] = '1.0'
    publication: Literal['draft'] = 'draft'
    humanReview: Literal['unreviewed'] = 'unreviewed'
    inputStatus: Literal['reference_fixture', 'caller_snapshot_unverified']
    deviceAcceptance: Literal['unverified'] = 'unverified'
    contentVersion: Id
    contentDigest: str
    journeyId: Id
    snapshotDigest: str
    completed: bool
    emotionalStatus: Literal['literary_inference_not_measured_player_emotion'] = 'literary_inference_not_measured_player_emotion'
    model: str
    promptVersion: Literal['sdt-feedback-1'] = 'sdt-feedback-1'
    usage: list[Usage]


def generate_feedback(pack, snapshot, provider, *, synthetic=False):
    # Reuse exact existing event, prerequisite, sequence, completion and dwell validation.
    reference = evaluate_reflection(pack, snapshot)
    ids = [n['eventId'] for n in reference['nodes']]
    segment_map = {n['eventId']: n['segmentIds'] for n in reference['nodes']}
    start = len(provider.usage)
    def check(raw):
        result = FeedbackBody.model_validate(raw)
        if [n.eventId for n in result.nodes] != ids:
            raise ValueError('FEEDBACK_EVENT_COVERAGE')
        for node in result.nodes:
            if node.segmentIds != segment_map[node.eventId]:
                raise ValueError('FEEDBACK_SEGMENT_MAPPING')
            if 'act2.high.visited' not in ids and '登高' in node.poeticExplanation:
                raise ValueError('FEEDBACK_UNOBSERVED_HIGH_EVENT')
        return result
    if not ids:
        result = FeedbackBody(nodes=[])
    else:
        data = {'confirmedNodes': reference['nodes'], 'completed': snapshot.completed,
                'effectiveDwell': [d.model_dump() for d in snapshot.regionDwell],
                'poemSegments': {s.segmentId: s.text for s in pack.poem.segments},
                'evidenceBoundary': 'snapshot only; no claim of device/player authenticity'}
        prompt = messages('依据已提交的confirmedNodes逐条生成离线诗意反馈，nodes顺序及eventId、segmentIds必须完全相同。poeticExplanation把该节点与诗句意象对应；emotionalInterpretation只能是文学情绪解释，不是玩家心理测量。不添加已给节点以外的经历，不把诗句里想象的动作说成玩家实际做过。未给act2.high.visited时不要提及玩家登高。未完成时不说通关；没有驻足时不编造时长。给玩家阅读的自然中文，不出现草稿、校验、字段、Godot等工程措辞；审核状态由外层元数据声明。',
                          data, FeedbackBody.model_json_schema())
        result = provider.structured(prompt, check)
    return FeedbackReport(**result.model_dump(), inputStatus='reference_fixture' if synthetic else 'caller_snapshot_unverified',
                          contentVersion=pack.contentVersion, contentDigest=digest(pack.model_dump(mode='json')),
                          journeyId=snapshot.journeyId, snapshotDigest=digest(snapshot.model_dump(mode='json')),
                          completed=snapshot.completed, model=provider.config.model, usage=provider.usage[start:])

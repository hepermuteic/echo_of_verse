"""Versioned offline authoring contract; independent of the client's save schema."""
from typing import Annotated, Literal
from pydantic import ConfigDict, Field, FiniteFloat, model_serializer, model_validator
from app.contracts import Contract, InputIdentifier as ID
from app.client_contracts import ArtKey, Dynasty, Form, Genre


class Review(Contract):
    status: Literal['demo_unreviewed', 'reviewed'] = 'demo_unreviewed'
    reviewer: ID | None = None
    reviewedAt: ID | None = None

    @model_validator(mode='after')
    def evidence(self):
        if self.status == 'reviewed' and (not self.reviewer or not self.reviewedAt):
            raise ValueError('Reviewed content requires reviewer and date')
        return self


class AssetRef(Contract):
    assetId: ID
    assetVersion: ID


class SourceEntry(Contract):
    sourceId: ID
    kind: Literal['original', 'reference', 'creation']
    title: str = Field(min_length=1, max_length=2048)
    editionOrCredit: str = Field(min_length=1, max_length=2048)
    locator: str = Field(min_length=1, max_length=2048)
    review: Review = Field(default_factory=Review)


class Segment(Contract):
    segmentId: ID
    order: int = Field(ge=0, strict=True)
    text: str = Field(min_length=1, max_length=2048)


class PoemDefinition(Contract):
    poemId: ID
    title: ID
    author: ID
    preface: str = Field(min_length=1, max_length=4096)
    segments: list[Segment] = Field(min_length=1)
    sourceIds: list[ID] = Field(min_length=1)
    review: Review = Field(default_factory=Review)


class TextEntry(Contract):
    textId: ID
    zh: str = Field(min_length=1, max_length=8192)
    en: str | None = Field(default=None, min_length=1, max_length=8192)
    contentType: Literal['original', 'cultural_explanation', 'game_creation', 'english_explanation']
    sourceIds: list[ID] = Field(min_length=1)
    required: bool = Field(default=True, strict=True)
    requiresEnglish: bool = Field(default=False, strict=True)
    experienceEventIds: list[ID] = Field(default_factory=list)
    reviewZh: Review = Field(default_factory=Review)
    reviewEn: Review = Field(default_factory=Review)


class ObjectBinding(Contract):
    objectId: ID
    actId: ID
    asset: AssetRef
    position: tuple[FiniteFloat, FiniteFloat, FiniteFloat]
    rotation: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat] = (0, 0, 0, 1)
    scale: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (1, 1, 1)
    required: bool = Field(default=True, strict=True)


class RegionBinding(Contract):
    regionId: ID
    actId: ID


class SpawnBinding(Contract):
    spawnId: ID
    actId: ID
    position: tuple[FiniteFloat, FiniteFloat, FiniteFloat]


class EnvironmentPreset(Contract):
    environmentId: ID
    assets: list[AssetRef] = Field(min_length=1)


class Parameter(Contract):
    parameterId: ID
    value: FiniteFloat = Field(gt=0, strict=True)
    unit: Literal['meters', 'seconds']
    confirmed: bool = Field(default=False, strict=True)


class Step(Contract):
    stepId: ID
    kind: Literal['animation', 'dialogue', 'audio', 'effect']
    objectId: ID | None = None
    textId: ID | None = None
    asset: AssetRef | None = None
    required: bool = Field(default=True, strict=True)

    @model_validator(mode='after')
    def payload(self):
        if self.kind == 'dialogue':
            if not self.textId or self.asset:
                raise ValueError('Dialogue needs textId and no asset')
        elif not self.objectId:
            raise ValueError('Animation, effect and audio need objectId')
        if self.kind == 'audio' and self.asset is None:
            raise ValueError('Audio needs an explicit versioned asset')
        if self.kind != 'dialogue' and self.textId is not None:
            raise ValueError('Only dialogue steps may carry textId')
        if self.kind != 'audio' and self.asset is not None:
            raise ValueError('Only audio steps carry independent asset references')
        return self


class Presentation(Contract):
    presentationId: ID
    execution: Literal['sequential'] = 'sequential'
    steps: list[Step] = Field(min_length=1)
    confirmed: bool = Field(default=False, strict=True)


class InteractionTrigger(Contract):
    kind: Literal['interact']
    objectId: ID


class RegionTrigger(Contract):
    kind: Literal['enter_region']
    regionId: ID


class MovementTrigger(Contract):
    kind: Literal['horizontal_movement']
    regionId: ID
    parameterId: ID


Trigger = Annotated[InteractionTrigger | RegionTrigger | MovementTrigger, Field(discriminator='kind')]


class EventDefinition(Contract):
    eventId: ID
    actId: ID
    required: bool = Field(strict=True)
    prerequisites: list[ID] = Field(default_factory=list)
    trigger: Trigger
    presentationId: ID
    completion: Literal['all_required_steps'] = 'all_required_steps'
    segmentIds: list[ID] = Field(min_length=1)
    nodeTextId: ID
    explanationTextId: ID


class ActDefinition(Contract):
    actId: ID
    order: int = Field(ge=1, strict=True)
    title: ID
    environmentId: ID
    spawnId: ID
    exitEventId: ID
    nextActId: ID | None = None


class InsightEntry(Contract):
    insightId: ID
    segmentIds: list[ID] = Field(min_length=1)
    textId: ID


class DwellCondition(Contract):
    regionId: ID
    parameterId: ID


class RuleCondition(Contract):
    allEvents: list[ID] = Field(default_factory=list)
    anyEvents: list[ID] = Field(default_factory=list)
    absentEvents: list[ID] = Field(default_factory=list)
    dwellMin: list[DwellCondition] = Field(default_factory=list)


class ReflectionRule(Contract):
    ruleId: ID
    priority: int = Field(strict=True)
    when: RuleCondition
    textId: ID


class ClientActBinding(Contract):
    actId: ID
    n: ID


class ClientImageryBinding(Contract):
    name: ID
    lineTextId: ID
    clipTextId: ID
    noteTextId: ID
    sourceTextId: ID
    art: ArtKey


class ClientPresentation(Contract):
    sourceCommit: ID
    id: Literal['shuidiaogetou']
    title: ID
    form: Form
    dynasty: Dynasty
    genre: Genre
    first: ID
    stanzaSegmentIds: list[list[ID]] = Field(min_length=2, max_length=2)
    acts: list[ClientActBinding] = Field(min_length=3, max_length=3)
    imagery: list[ClientImageryBinding] = Field(min_length=1)
    noteTextId: ID | None = None
    art: ArtKey


class GodotRuntime(Contract):
    engine: Literal['godot'] = 'godot'
    engineMajor: Literal[4] = 4
    targetPlatform: Literal['windows'] = 'windows'
    engineVersion: str | None = Field(default=None, max_length=128, pattern=r'^4\.\d+(?:\.\d+)?(?:[.-][A-Za-z0-9]+)*$')
    renderer: Literal['forward_plus', 'mobile', 'gl_compatibility'] | None = None
    coordinateSystem: Literal['godot_right_handed_y_up'] = 'godot_right_handed_y_up'
    metersPerUnit: float = Field(default=1, strict=True, ge=1, le=1, allow_inf_nan=False)
    quaternionOrder: Literal['xyzw'] = 'xyzw'
    bindingsConfirmed: bool = Field(default=False, strict=True)


class ContentPack(Contract):
    model_config = ConfigDict(json_schema_extra={'allOf': [{
        'if': {'required': ['schemaVersion'], 'properties': {'schemaVersion': {'enum': ['1.1', '1.2']}}},
        'then': {'required': ['clientPresentation'], 'properties': {'clientPresentation': {'type': 'object'}}},
        'else': {'properties': {'clientPresentation': {'type': 'null'}}},
    }, {
        'if': {'required': ['schemaVersion'], 'properties': {'schemaVersion': {'const': '1.2'}}},
        'then': {'required': ['runtime'], 'properties': {'runtime': {'type': 'object'}}},
        'else': {'properties': {'runtime': {'type': 'null'}}},
    }]})
    schemaVersion: Literal['1.0', '1.1', '1.2'] = '1.0'
    contentVersion: ID
    resourceCatalogVersion: ID
    publication: Literal['draft', 'released'] = 'draft'
    poem: PoemDefinition
    acts: list[ActDefinition] = Field(min_length=3, max_length=3)
    events: list[EventDefinition] = Field(min_length=5)
    texts: list[TextEntry] = Field(min_length=1)
    insights: list[InsightEntry] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(min_length=1)
    objects: list[ObjectBinding] = Field(min_length=1)
    regions: list[RegionBinding] = Field(min_length=1)
    spawns: list[SpawnBinding] = Field(min_length=3)
    environments: list[EnvironmentPreset] = Field(min_length=1)
    presentations: list[Presentation] = Field(min_length=1)
    parameters: list[Parameter] = Field(default_factory=list)
    reflectionRules: list[ReflectionRule] = Field(default_factory=list)
    defaultReflectionTextId: ID
    clientPresentation: ClientPresentation | None = None
    runtime: GodotRuntime | None = None

    @model_serializer(mode='wrap')
    def content_fields(self, handler):
        data = handler(self)
        if self.schemaVersion != '1.2':
            data.pop('runtime', None)
        return data

    @model_validator(mode='after')
    def presentation_version(self):
        if (self.schemaVersion in ('1.1', '1.2')) != (self.clientPresentation is not None):
            raise ValueError('Schema 1.1/1.2 require clientPresentation; legacy 1.0 must not include it')
        if (self.schemaVersion == '1.2') != (self.runtime is not None):
            raise ValueError('Schema 1.2 requires runtime; legacy versions must not include it')
        return self


class CommittedEvent(Contract):
    eventId: ID
    sequence: int = Field(ge=0, strict=True)


class RegionDwell(Contract):
    regionId: ID
    effectiveSeconds: FiniteFloat = Field(ge=0, strict=True)


class JourneySnapshot(Contract):
    schemaVersion: Literal['1.0'] = '1.0'
    contentVersion: ID
    journeyId: ID
    completed: bool = Field(strict=True)
    committedEvents: list[CommittedEvent]
    regionDwell: list[RegionDwell] = Field(default_factory=list)

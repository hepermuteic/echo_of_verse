"""AI authoring contracts, independent of the game and human review contracts."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Id = Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')]
Text = Annotated[str, StringConstraints(min_length=1, max_length=4096)]
Digest = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
Kind = Literal['original', 'historical', 'interpretation', 'game_creation']
SEGMENTS = tuple(f'sdt.segment.{i:02}' for i in range(1, 9))
UNITS = ('preface', *SEGMENTS)
DIMENSIONS = ('time', 'location', 'people', 'imagery', 'actions', 'sounds', 'events', 'emotions')


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True, str_strip_whitespace=True)


class Paragraph(Strict):
    chunkId: Id
    locator: Text
    kind: Literal['original', 'historical', 'interpretation']
    representation: Literal['verbatim', 'paraphrase']
    text: Text


class KnowledgeSource(Strict):
    sourceId: Id
    title: Text
    authorOrPublisher: Text
    url: str = Field(pattern=r'^https://[^\s]+$', max_length=2048)
    collectedAt: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    editionStatus: Literal['web_located_print_unconfirmed', 'publication_located']
    summary: Text
    humanReview: Literal['unreviewed'] = 'unreviewed'
    paragraphs: list[Paragraph] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def valid_date(self):
        date.fromisoformat(self.collectedAt)
        return self


class KnowledgeBase(Strict):
    schemaVersion: Literal['1.0'] = '1.0'
    poemId: Literal['su_shi.shuidiaogetou'] = 'su_shi.shuidiaogetou'
    sources: list[KnowledgeSource] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_ids(self):
        sources = [s.sourceId for s in self.sources]
        chunks = [p.chunkId for s in self.sources for p in s.paragraphs]
        if len(set(sources)) != len(sources) or len(set(chunks)) != len(chunks):
            raise ValueError('Duplicate source or chunk identity')
        return self


class Citation(Strict):
    chunkId: Id
    quote: str = Field(min_length=1, max_length=600)


class Grounded(Strict):
    value: str = Field(min_length=1, max_length=1000)
    basis: Literal['explicit', 'inferred', 'imagined', 'unknown']
    originalQuotes: list[str] = Field(max_length=8)
    citations: list[Citation] = Field(max_length=6)

    @model_validator(mode='after')
    def anchored(self):
        if self.basis == 'unknown':
            if self.value != '未知' or self.originalQuotes or self.citations:
                raise ValueError('Unknown values must not assert facts')
        elif not self.originalQuotes and not self.citations:
            raise ValueError('Nonempty analysis requires an anchor')
        if any(not q or len(q) > 2048 for q in self.originalQuotes):
            raise ValueError('Invalid original quotation')
        return self


class UnitAnalysis(Strict):
    unitId: Id
    paraphrase: Grounded
    emotionChange: Grounded
    time: list[Grounded] = Field(max_length=12)
    location: list[Grounded] = Field(max_length=12)
    people: list[Grounded] = Field(max_length=12)
    imagery: list[Grounded] = Field(max_length=12)
    actions: list[Grounded] = Field(max_length=12)
    sounds: list[Grounded] = Field(max_length=12)
    events: list[Grounded] = Field(max_length=12)
    emotions: list[Grounded] = Field(max_length=12)


class Usage(Strict):
    attempt: int = Field(ge=1)
    model: str
    promptTokens: int | None = Field(default=None, ge=0)
    completionTokens: int | None = Field(default=None, ge=0)
    totalTokens: int | None = Field(default=None, ge=0)


class AnalysisReport(Strict):
    schemaVersion: Literal['1.0'] = '1.0'
    publication: Literal['draft'] = 'draft'
    humanReview: Literal['unreviewed'] = 'unreviewed'
    poemId: Literal['su_shi.shuidiaogetou'] = 'su_shi.shuidiaogetou'
    contentVersion: Id
    contentDigest: Digest
    corpusDigest: Digest
    promptVersion: Literal['sdt-ai-1', 'sdt-ai-2'] = 'sdt-ai-2'
    model: str
    retrievalMethod: Literal['jieba-bm25'] = 'jieba-bm25'
    units: list[UnitAnalysis] = Field(min_length=9, max_length=9)
    evidence: dict[str, list[dict]]
    usage: list[Usage]

    @model_validator(mode='after')
    def coverage(self):
        if tuple(u.unitId for u in self.units) != UNITS:
            raise ValueError('Preface and all eight segments required in stable order')
        if set(self.evidence) != set(UNITS):
            raise ValueError('Evidence required for every unit')
        return self


class Claim(Strict):
    claimId: Id
    targetId: Id
    text: Text
    kind: Kind
    sourceQuote: str | None = Field(default=None, min_length=1, max_length=4096)


class Verdict(Strict):
    claimId: Id
    status: Literal['supported', 'contradicted', 'insufficient', 'conflicting']
    explanation: Text
    citations: list[Citation] = Field(max_length=6)

    @model_validator(mode='after')
    def has_evidence(self):
        if self.status != 'insufficient' and not self.citations:
            raise ValueError('Conclusion requires evidence')
        if self.status == 'conflicting' and len({c.chunkId for c in self.citations}) < 2:
            raise ValueError('Conflict requires at least two evidence chunks')
        return self


class ValidationEntry(Strict):
    claim: Claim
    verdict: Verdict
    evidence: list[dict]


class ValidationReport(Strict):
    schemaVersion: Literal['1.0'] = '1.0'
    publication: Literal['draft'] = 'draft'
    humanReview: Literal['unreviewed'] = 'unreviewed'
    poemId: Literal['su_shi.shuidiaogetou'] = 'su_shi.shuidiaogetou'
    contentVersion: Id
    contentDigest: Digest
    corpusDigest: Digest
    promptVersion: Literal['sdt-ai-1', 'sdt-ai-2'] = 'sdt-ai-2'
    model: str
    retrievalMethod: Literal['jieba-bm25'] = 'jieba-bm25'
    entries: list[ValidationEntry]
    skippedCreations: list[Claim]
    usage: list[Usage]

    @model_validator(mode='after')
    def identities(self):
        ids = [e.claim.claimId for e in self.entries] + [c.claimId for c in self.skippedCreations]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate claim identity')
        if any(e.claim.claimId != e.verdict.claimId for e in self.entries):
            raise ValueError('Mismatched verdict identity')
        if any(c.kind != 'game_creation' for c in self.skippedCreations):
            raise ValueError('Only game creations may skip fact validation')
        return self

import unicodedata
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

InputIdentifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]

def normalize_name(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).strip()
    if value.startswith('《') and value.endswith('》'):
        value = value[1:-1].strip()
    return ' '.join(value.split()).casefold()

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Poem(Contract):
    id: InputIdentifier
    title: InputIdentifier
    author: InputIdentifier
    lines: list[str] = Field(min_length=1, max_length=256)
    content_review_status: Literal['demo_unreviewed', 'reviewed'] = 'demo_unreviewed'

    @field_validator('lines')
    @classmethod
    def lines_valid(cls, values):
        if any(not value.strip() or len(value) > 2048 for value in values):
            raise ValueError('Lines must be nonempty and at most 2048 characters')
        return [value.strip() for value in values]

class LookupRequest(Contract):
    title: InputIdentifier
    author: InputIdentifier | None = None

    @field_validator('title', 'author')
    @classmethod
    def meaningful(cls, value):
        if value is not None and not normalize_name(value):
            raise ValueError('Empty normalized name')
        return value

class PaginationRequest(Contract):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.client_contracts import ClientPoem

class ResponseContract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class HealthResponse(ResponseContract):
    status: Literal['ok']
    mode: Literal['offline_content']
    deployment: str

class ContentState(ResponseContract):
    contentVersion: str | None
    contentStatus: Literal['missing', 'draft', 'released', 'invalid']

class PoemListItem(ClientPoem, ContentState):
    content_review_status: Literal['demo_unreviewed', 'reviewed']

class PoemListResponse(ResponseContract):
    items: list[PoemListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

class LookupMatch(ContentState):
    poem: ClientPoem
    content_review_status: Literal['demo_unreviewed', 'reviewed']

class LookupResponse(ContentState):
    poem_exists: bool
    status: Literal['not_found', 'poem_only', 'content_available']
    message: str
    matches: list[LookupMatch]

class ValidationField(ResponseContract):
    location: list[str | int]
    message: str
    type: str

class GeneralError(ResponseContract):
    code: Literal['LOCAL_DATA_INVALID', 'INTERNAL_ERROR', 'DATABASE_UNAVAILABLE', 'CONTENT_UNAVAILABLE', 'HTTP_ERROR']
    message: str

class ValidationErrorDetail(ResponseContract):
    code: Literal['VALIDATION_ERROR']
    message: str
    fields: list[ValidationField]

class ErrorResponse(ResponseContract):
    error: Annotated[GeneralError | ValidationErrorDetail, Field(discriminator='code')]
    request_id: str

def response_docs():
    docs = {status: {'model': ErrorResponse, 'description': description} for status, description in {
        422: 'VALIDATION_ERROR', 500: 'LOCAL_DATA_INVALID / INTERNAL_ERROR',
        503: 'DATABASE_UNAVAILABLE / CONTENT_UNAVAILABLE', 'default': 'HTTP_ERROR'}.items()}
    docs[405] = {'model': ErrorResponse, 'description': 'HTTP_ERROR: method not allowed',
                 'headers': {'Allow': {'description': 'Supported HTTP methods', 'schema': {'type': 'string'}}}}
    return docs

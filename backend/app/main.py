import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from fastapi import FastAPI, Query, Request
from starlette.exceptions import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.catalog import CatalogError, find_poems, read_poem
from app.content import POEM_ID, client_content
from app.contracts import LookupRequest, PaginationRequest
from app.responses import ErrorResponse, HealthResponse, LookupResponse, PoemListResponse, response_docs
from app.settings import DEPLOYMENT_NAME, cors_origins
from app.storage import database, initialize

log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield

app = FastAPI(title='诗画入境 · 客户端内容契约', version='0.5.0', lifespan=lifespan)
origins = cors_origins()
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=['GET'], allow_headers=['Content-Type'], expose_headers=['X-Request-ID'])

@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error_response(request, status, code, message, *, headers=None, **extra):
    request_id = getattr(request.state, "request_id", None) or str(uuid4())
    content = ErrorResponse.model_validate({"error": {"code": code, "message": message, **extra},
                                           "request_id": request_id})
    return JSONResponse(status_code=status, content=content.model_dump(mode="json"),
                        headers={**(headers or {}), "X-Request-ID": request_id})


@app.exception_handler(CatalogError)
async def catalog_error(request, exc):
    return error_response(request, exc.status, exc.code, exc.message)


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail), headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    fields = [{"location": list(e["loc"]), "message": e["msg"], "type": e["type"]} for e in exc.errors()]
    return error_response(request, 422, "VALIDATION_ERROR", "请求字段不符合接口约定", fields=fields)


@app.exception_handler(sqlite3.Error)
async def database_error(request, exc):
    log.exception("Database unavailable; request_id=%s", request.state.request_id)
    return error_response(request, 503, "DATABASE_UNAVAILABLE", "本地数据库暂不可用，请稍后重试")


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error(request, exc):
    log.exception("Database unavailable; request_id=%s", request.state.request_id)
    return error_response(request, 503, "DATABASE_UNAVAILABLE", "数据库暂不可用，请稍后重试")


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    log.exception("Unexpected failure; request_id=%s", request.state.request_id)
    return error_response(request, 500, "INTERNAL_ERROR", "服务内部异常，请根据 request_id 联系维护人员")


@app.get('/health', response_model=HealthResponse, responses=response_docs())
def health():
    with database() as db:
        db.execute('SELECT 1 FROM poems LIMIT 1')
    return {'status': 'ok', 'mode': 'offline_content', 'deployment': DEPLOYMENT_NAME}

@app.get('/api/v1/poems', response_model=PoemListResponse, responses=response_docs())
def poems(payload: Annotated[PaginationRequest, Query()]):
    with database() as db:
        row = db.execute('SELECT * FROM poems WHERE id=?', (POEM_ID,)).fetchone()
        if row is not None and payload.offset == 0:
            read_poem(row)  # Keep detecting corrupt SQL records; do not rewrite them.
    items = []
    if row is not None and payload.offset == 0:
        poem, state = client_content()
        items = [{**poem, **state}]
    return {'items': items, 'total': int(row is not None), 'limit': payload.limit, 'offset': payload.offset}

@app.get('/api/v1/poems/lookup', response_model=LookupResponse, responses=response_docs())
def lookup(payload: Annotated[LookupRequest, Query()]):
    with database() as db:
        matches = find_poems(db, payload.title, payload.author)
    if not matches:
        return {'poem_exists': False, 'contentVersion': None, 'contentStatus': 'missing',
                'status': 'not_found', 'message': '当前 Demo 未收录该作品', 'matches': []}
    poem, state = client_content()
    return {'poem_exists': True, 'contentVersion': state['contentVersion'], 'contentStatus': state['contentStatus'],
            'status': 'content_available', 'message': '客户端字段已提供；Godot 资源对接和离线通关须单独验收',
            'matches': [{'poem': poem, **state}]}

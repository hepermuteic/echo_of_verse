"""Bounded DeepSeek requests with durable pre-send accounting and redacted failures."""
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.ai_authoring.retrieval import encoded
from app.ai_authoring.models import Usage
from app.configuration import secret

MAX_INPUT = 24000
MAX_OUTPUT = 8192


class AuthoringError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class OutputValidationError(ValueError):
    """Internal, sanitized locations for precise model repair; never includes values."""
    def __init__(self, code, fields):
        super().__init__(code)
        self.diagnostic = {'code': code, 'fields': fields}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.ai-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(encoded(data) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Budget:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + '.lock')
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, PermissionError):
            raise AuthoringError('BUDGET_BUSY') from None
        os.close(fd)
        try:
            yield
        finally:
            lock.unlink()

    def read(self):
        if not self.path.exists():
            return {'limit': 20, 'attempts': []}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            attempts = data['attempts']
            if (set(data) != {'limit', 'attempts'} or type(data['limit']) is not int or data['limit'] != 20
                    or not isinstance(attempts, list) or len(attempts) > 20
                    or any(e['attempt'] != i for i, e in enumerate(attempts, 1))):
                raise ValueError()
            return data
        except (ValueError, KeyError, TypeError):
            raise AuthoringError('INVALID_BUDGET_LEDGER') from None

    def reserve(self, model):
        with self.locked():
            data = self.read()
            if len(data['attempts']) >= 20:
                raise AuthoringError('REQUEST_BUDGET_EXHAUSTED')
            attempt = len(data['attempts']) + 1
            data['attempts'].append({'attempt': attempt, 'model': model, 'time': datetime.now(timezone.utc).isoformat(),
                                     'status': 'reserved'})
            atomic_json(self.path, data)
        return attempt

    def finish(self, attempt, status, **details):
        with self.locked():
            data = self.read()
            data['attempts'][attempt - 1].update(status=status, **details)
            atomic_json(self.path, data)


class DeepSeek:
    def __init__(self, config, budget, *, transport=None, sleeper=time.sleep):
        self.config = config
        self.budget = budget
        self.usage = []
        self.diagnostics = []
        self.sleeper = sleeper
        self.transport = transport
        if not config.enabled:
            raise AuthoringError('MODEL_DISABLED')
        if config.provider != 'deepseek' or not config.model or not config.api_base_url:
            raise AuthoringError('INVALID_MODEL_CONFIGURATION')
        self.key = secret(config.api_key_env).get_secret_value()
        if not self.key.strip():
            raise AuthoringError('MODEL_CREDENTIAL_MISSING')

    def request(self, messages):
        if len(encoded(messages)) > MAX_INPUT:
            raise AuthoringError('INPUT_TOO_LARGE')
        payload = {'model': self.config.model, 'messages': messages, 'stream': False,
                   'thinking': {'type': 'disabled'}, 'response_format': {'type': 'json_object'},
                   'max_tokens': MAX_OUTPUT}
        retries = min(self.config.max_retries, 2)
        for retry in range(retries + 1):
            attempt = self.budget.reserve(self.config.model)
            try:
                with httpx.Client(timeout=self.config.timeout_seconds, transport=self.transport,
                                  follow_redirects=False, trust_env=False) as client:
                    response = client.post(self.config.api_base_url.rstrip('/') + '/chat/completions',
                                           headers={'Authorization': 'Bearer ' + self.key}, json=payload)
            except httpx.TransportError:
                self.budget.finish(attempt, 'failed', code='MODEL_NETWORK_ERROR')
                if retry < retries:
                    self.sleeper(2 ** retry)
                    continue
                raise AuthoringError('MODEL_NETWORK_ERROR') from None
            status = response.status_code
            if status != 200:
                code = {400: 'MODEL_BAD_REQUEST', 401: 'MODEL_AUTH_FAILED', 402: 'MODEL_BALANCE_INSUFFICIENT',
                        403: 'MODEL_FORBIDDEN', 429: 'MODEL_RATE_LIMITED'}.get(status, 'MODEL_HTTP_ERROR')
                self.budget.finish(attempt, 'failed', code=code, httpStatus=status)
                if (status == 429 or status in (500, 502, 503, 504)) and retry < retries:
                    self.sleeper(2 ** retry)
                    continue
                raise AuthoringError(code)
            try:
                data = response.json()
                actual_model = data['model']
                if not isinstance(actual_model, str) or not actual_model:
                    raise ValueError()
                raw_usage = data.get('usage') or {}
                usage = Usage(attempt=attempt, model=actual_model, promptTokens=raw_usage.get('prompt_tokens'),
                              completionTokens=raw_usage.get('completion_tokens'), totalTokens=raw_usage.get('total_tokens'))
                self.usage.append(usage)
                self.budget.finish(attempt, 'received', usage=usage.model_dump())
                choice = data['choices'][0]
                content = choice['message']['content']
                if choice['finish_reason'] != 'stop' or not isinstance(content, str) or not content.strip():
                    raise ValueError()
                return content
            except (ValueError, KeyError, IndexError, TypeError, ValidationError):
                self.budget.finish(attempt, 'invalid_response', code='MODEL_INVALID_RESPONSE')
                raise AuthoringError('MODEL_INVALID_RESPONSE') from None

    def structured(self, messages, validate):
        # One bounded repair, without echoing untrusted provider output or validation inputs.
        for repair in range(2):
            try:
                result = json.loads(self.request(messages))
                return validate(result)
            except OutputValidationError as exc:
                diagnostic = exc.diagnostic
            except ValidationError as exc:
                diagnostic = {'code': 'SCHEMA_VALIDATION',
                              'fields': [{'location': list(e['loc']), 'type': e['type']} for e in exc.errors()]}
            except (ValueError, TypeError, KeyError) as exc:
                # Only internal identifier-shaped error codes, never arbitrary exception text.
                value = str(exc)
                diagnostic = {'code': value if re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', value) else 'INVALID_JSON_OR_STRUCTURE'}
            except AuthoringError as exc:
                if exc.code != 'MODEL_INVALID_RESPONSE':
                    raise
                diagnostic = {'code': exc.code}
            self.diagnostics.append(diagnostic)
            if not repair:
                messages = [*messages, {'role': 'user', 'content': '上次输出未通过校验：' + encoded(diagnostic) +
                            '。请重新生成完整 json，严格遵守原 schema。原文和证据引用必须逐字复制，包括简繁体、标点，不要自行改写。'}]
        raise AuthoringError('MODEL_STRUCTURED_OUTPUT_INVALID')

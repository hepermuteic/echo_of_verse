"""Immutable versioned authoring bundles, separate from the 17-file game handoff."""
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.ai_authoring.models import Id
from app.ai_authoring.provider import AuthoringError
from app.ai_authoring.retrieval import encoded
from pydantic import TypeAdapter


@contextmanager
def bundle(output, run_id):
    TypeAdapter(Id).validate_python(run_id)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / run_id
    if destination.exists():
        raise AuthoringError('RUN_ALREADY_EXISTS')
    lock = output / ('.' + run_id + '.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):
        raise AuthoringError('RUN_BUSY') from None
    os.close(fd)
    temporary = Path(tempfile.mkdtemp(prefix='.ai-bundle-', dir=output))
    try:
        yield temporary
        hashes = {p.relative_to(temporary).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in temporary.rglob('*') if p.is_file()}
        (temporary / 'checksums.json').write_text(encoded(hashes) + '\n', encoding='utf-8')
        verify_bundle(temporary)
        if destination.exists():
            raise AuthoringError('RUN_ALREADY_EXISTS')
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        lock.unlink()


def verify_bundle(directory):
    directory = Path(directory)
    hashes = json.loads((directory / 'checksums.json').read_text(encoding='utf-8'))
    if set(hashes) != {p.relative_to(directory).as_posix() for p in directory.rglob('*')
                       if p.is_file() and p != directory / 'checksums.json'}:
        raise AuthoringError('BUNDLE_FILE_SET')
    if 'run.json' not in hashes:
        raise AuthoringError('BUNDLE_MISSING_STATUS')
    for name, checksum in hashes.items():
        relative = Path(name)
        if (relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name
                or (directory / relative).is_symlink()
                or hashlib.sha256((directory / relative).read_bytes()).hexdigest() != checksum):
            raise AuthoringError('BUNDLE_CHECKSUM')


def write_json(directory, name, value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def readable(analysis, validation, status):
    lines = ['# 水调歌头 AI 内容制作草稿', '', '人工审核：未审核。证据支持不等于正式发布或客户端验收。', '',
             f'执行状态：{status}', '']
    if analysis:
        dimensions = {'time': '时间', 'location': '地点', 'people': '人物', 'imagery': '意象',
                      'actions': '动作', 'sounds': '声音', 'events': '诗义事件', 'emotions': '情绪'}
        for unit in analysis.units:
            lines.extend([f'## {unit.unitId}', '', unit.paraphrase.value, '', '情绪变化：' + unit.emotionChange.value, ''])
            for field, label in dimensions.items():
                entries = getattr(unit, field)
                lines.append(f'- {label}：' + ('；'.join(f'{v.value}（{v.basis}）' for v in entries) or '未提取到有依据的内容'))
            lines.append('')
            lookup = {e['chunkId']: e for e in analysis.evidence[unit.unitId]}
            cited = {(c.chunkId, c.quote) for v in [unit.paraphrase, unit.emotionChange,
                     *(v for field in dimensions for v in getattr(unit, field))] for c in v.citations}
            for chunk_id, quote in sorted(cited):
                e = lookup[chunk_id]
                lines.append(f'- 依据：[{e["title"]}]({e["url"]}) · {e["locator"]} · {e["representation"]}：{quote}')
            lines.append('')
    if validation:
        labels = {'supported': '证据支持', 'contradicted': '证据反驳', 'insufficient': '证据不足', 'conflicting': '来源冲突'}
        for item in validation.entries:
            lines.extend([f'## {item.claim.claimId}', '', item.claim.text, '',
                          f'{labels[item.verdict.status]}：{item.verdict.explanation}', ''])
            lookup = {e['chunkId']: e for e in item.evidence}
            for citation in item.verdict.citations:
                e = lookup[citation.chunkId]
                lines.extend([f'- [{e["title"]}]({e["url"]}) · {e["locator"]} · {e["representation"]}：{citation.quote}'])
            lines.append('')
        lines.append(f'另有 {len(validation.skippedCreations)} 项游戏创作单独列示，不作为史实。')
        for claim in validation.skippedCreations:
            lines.extend(['', f'- 游戏创作 {claim.targetId}：{claim.text}'])
    return '\n'.join(lines) + '\n'

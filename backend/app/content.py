from pathlib import Path
from app.contracts import Poem

POEM_ID = 'su_shi.shuidiaogetou'
CONTENT_VERSION = 'shuidiaogetou-3'
ROOT = Path(__file__).resolve().parents[1]

def source_dir() -> Path:
    import os
    selected = Path(os.environ.get('EOV_CONTENT_SOURCE', 'content/' + CONTENT_VERSION))
    return selected if selected.is_absolute() else ROOT / selected

def poem_projection() -> Poem:
    from app.demo_models import ContentPack
    pack = ContentPack.model_validate_json((source_dir() / 'content-pack.json').read_text(encoding='utf-8'))
    if pack.poem.poemId != POEM_ID:
        raise ValueError('Only the current demo may initialize the database')
    return Poem(id=pack.poem.poemId, title=pack.poem.title, author=pack.poem.author,
                lines=[line.text for line in sorted(pack.poem.segments, key=lambda line: line.order)],
                content_review_status=pack.poem.review.status)

def content_state():
    from app.demo_content import load_source, validate_pack, verify_checksums
    directory = source_dir()
    if not (directory / 'content-pack.json').is_file():
        return {'contentVersion': None, 'contentStatus': 'missing'}
    try:
        pack, manifest = load_source(directory)
        report = validate_pack(pack, manifest, release=pack.publication == 'released')
        if not report['ok']:
            raise ValueError('Invalid content')
        if pack.publication == 'released':
            verify_checksums(directory)
        return {'contentVersion': pack.contentVersion, 'contentStatus': pack.publication}
    except (ValueError, OSError, KeyError):
        return {'contentVersion': None, 'contentStatus': 'invalid'}


def client_content():
    """Read a single consistent source snapshot for both the payload and status."""
    from app.catalog import CatalogError
    from app.client_content import project_client_poem
    from app.demo_content import load_source, validate_pack, verify_checksums
    directory = source_dir()
    try:
        pack, manifest = load_source(directory)
        report = validate_pack(pack, manifest, release=pack.publication == 'released')
        if not report['ok']:
            raise ValueError('Content validation failed')
        poem = project_client_poem(pack)
        if pack.publication == 'released':
            verify_checksums(directory)
        state = {'contentVersion': pack.contentVersion, 'contentStatus': pack.publication,
                 'content_review_status': pack.poem.review.status}
        return poem.model_dump(mode='json', exclude_none=True), state
    except (ValueError, OSError, KeyError) as exc:
        raise CatalogError('CONTENT_UNAVAILABLE', '客户端内容缺失、无效或不支持完整字段投影', 503) from exc

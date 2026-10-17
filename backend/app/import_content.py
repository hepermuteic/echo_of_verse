"""Only the current demo poem projection may be imported; no Scene inputs."""
import argparse
import json
from pathlib import Path
from app.content import POEM_ID
from app.contracts import Poem, normalize_name
from app.storage import database, initialize
from app.cache import clear_catalog

def import_record(payload, replace=False):
    if not isinstance(payload, dict) or set(payload) != {'poem'}:
        raise ValueError('Import requires only poem; use demo_content for offline packs')
    poem = Poem.model_validate(payload['poem'])
    if poem.id != POEM_ID:
        raise ValueError('Only the current demo identity may be imported')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        exists = db.execute('SELECT id FROM poems WHERE id=?', (poem.id,)).fetchone()
        if exists and not replace:
            raise ValueError('Existing poem; use --replace')
        db.execute('INSERT INTO poems(id,title_key,author_key,poem_json) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET title_key=excluded.title_key,author_key=excluded.author_key,poem_json=excluded.poem_json',
                   (poem.id, normalize_name(poem.title), normalize_name(poem.author), poem.model_dump_json()))
    clear_catalog()
    return {'poem_id': poem.id}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.file).read_text(encoding='utf-8-sig'))
        initialize(seed_demo=False)
        print(json.dumps(import_record(payload, args.replace), ensure_ascii=False))
        return 0
    except (OSError, ValueError):
        print('Import failed; input must be a valid current-demo poem')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())

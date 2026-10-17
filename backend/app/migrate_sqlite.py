"""Read-only-source import of the sole current poem into PostgreSQL."""
import argparse
import json
import sqlite3
from pathlib import Path
from sqlalchemy import select
from app.content import POEM_ID
from app.contracts import Poem, normalize_name
from app.storage import engine, initialize, poems
from app.cache import clear_catalog

def import_database(source):
    target = engine()
    if target.dialect.name != 'postgresql':
        raise ValueError('Target must be PostgreSQL')
    path = Path(source).resolve()
    if not path.is_file():
        raise FileNotFoundError('Source SQLite does not exist')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT poem_json FROM poems WHERE id=?', (POEM_ID,)).fetchone()
    if row is None:
        return {'poems': 0}
    poem = Poem.model_validate_json(row[0])
    if poem.id != POEM_ID:
        raise ValueError('Source poem identity mismatch')
    initialize(seed_demo=False)
    with target.begin() as connection:
        old = connection.execute(select(poems).where(poems.c.id == POEM_ID)).mappings().first()
        if old:
            if Poem.model_validate_json(old['poem_json']) != poem:
                raise ValueError('Conflicting current poem; source unchanged')
            return {'poems': 0}
        connection.execute(poems.insert().values(id=poem.id, title_key=normalize_name(poem.title),
                           author_key=normalize_name(poem.author), poem_json=poem.model_dump_json()))
    clear_catalog()
    return {'poems': 1}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    print(json.dumps(import_database(args.source)))

if __name__ == '__main__':
    main()

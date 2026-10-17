from app.content import POEM_ID
from app.contracts import Poem, normalize_name

class CatalogError(Exception):
    def __init__(self, code, message, status):
        self.code, self.message, self.status = code, message, status

def read_poem(row):
    try:
        poem = Poem.model_validate_json(row['poem_json'])
        if poem.id != row['id']:
            raise ValueError('Poem ID mismatch')
        return poem
    except ValueError as exc:
        raise CatalogError('LOCAL_DATA_INVALID', '诗篇资料损坏', 500) from exc

def find_poems(db, title, author=None):
    row = db.execute('SELECT * FROM poems WHERE id=?', (POEM_ID,)).fetchone()
    if row is None:
        return []
    poem = read_poem(row)
    # The work title and full display title resolve to the same, sole work.
    if normalize_name(title) not in {normalize_name(poem.title), normalize_name('水调歌头')}:
        return []
    if author is not None and normalize_name(author) != normalize_name(poem.author):
        return []
    return [poem]

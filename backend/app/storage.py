import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (Column, ForeignKey, Integer, MetaData, String, Table, Text, URL, create_engine,
                        event, inspect)
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url

from app.settings import DB_CONNECT_TIMEOUT_SECONDS, DB_POOL_TIMEOUT_SECONDS, DB_TIMEOUT_SECONDS, db_path
from app.configuration import configured_database_url, load_config

metadata = MetaData()
poems = Table("poems", metadata, Column("id", String, primary_key=True),
              Column("title_key", String, nullable=False), Column("author_key", String, nullable=False),
              Column("poem_json", Text, nullable=False))
from sqlalchemy import Index
Index("idx_poems_name", poems.c.title_key, poems.c.author_key)

_engines: dict[str, Engine] = {}


def database_url() -> str:
    config = load_config()
    configured = configured_database_url(config)
    if configured:
        return configured
    path = db_path(config).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)


def engine() -> Engine:
    url = database_url()
    if url not in _engines:
        options = {"pool_pre_ping": True}
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite":
            options.update(connect_args={"timeout": DB_TIMEOUT_SECONDS})
            if parsed.database not in (None, '', ':memory:'):
                options['pool_timeout'] = DB_POOL_TIMEOUT_SECONDS
        elif parsed.drivername == 'postgresql+psycopg':
            # Bound stalled reads/locks too; preserve unrelated URL session options.
            session_options = parsed.query.get('options', '')
            options.update(pool_timeout=DB_POOL_TIMEOUT_SECONDS,
                           connect_args={'connect_timeout': DB_CONNECT_TIMEOUT_SECONDS,
                                         'options': session_options + ' -c statement_timeout=5000 -c lock_timeout=1000'})
        db_engine = create_engine(url, **options)
        if db_engine.dialect.name == "sqlite":
            @event.listens_for(db_engine, "connect")
            def sqlite_pragmas(connection, _record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        _engines[url] = db_engine
    return _engines[url]


class Row:
    def __init__(self, row):
        self._row = row
        self._mapping = row._mapping

    def __getitem__(self, key):
        return self._row[key] if isinstance(key, int) else self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class Result:
    def __init__(self, result):
        self._result = result

    def fetchone(self):
        row = self._result.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self._result.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Database:
    def __init__(self, connection):
        self.connection = connection
        self.dialect = connection.dialect.name

    def execute(self, statement, params=()):
        sql = statement.strip()
        if self.dialect == "postgresql":
            if sql.upper() == "BEGIN IMMEDIATE":
                return Result(self.connection.exec_driver_sql("SELECT 1"))
            sql = sql.replace("?", "%s")
        elif sql.upper() == "BEGIN IMMEDIATE":
            return Result(self.connection.exec_driver_sql("BEGIN IMMEDIATE"))
        if self.dialect == "postgresql" and sql.upper().startswith("INSERT OR IGNORE INTO"):
            sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO", 1) + " ON CONFLICT DO NOTHING"
        return Result(self.connection.exec_driver_sql(sql, tuple(params) if params else ()))


@contextmanager
def database():
    try:
        connection = engine().connect()
    except OSError as exc:
        raise sqlite3.OperationalError('Database configuration or storage unavailable') from exc
    db = Database(connection)
    try:
        yield db
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(*, seed_demo: bool = True):
    metadata.create_all(engine())
    if not seed_demo:
        return
    from app.content import poem_projection
    from app.content import POEM_ID
    from app.contracts import normalize_name
    with database() as db:
        if db.execute('SELECT id FROM poems WHERE id=?', (POEM_ID,)).fetchone() is not None:
            return
        try:
            poem = poem_projection()
        except (ValueError, OSError):
            # Content can be repaired independently; never fabricate a SQL record or stop health checks.
            logging.getLogger(__name__).warning('Content unavailable; skipped additive catalog initialization')
            return
        db.execute("INSERT INTO poems(id,title_key,author_key,poem_json) VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING",
                   (poem.id, normalize_name(poem.title), normalize_name(poem.author), poem.model_dump_json()))

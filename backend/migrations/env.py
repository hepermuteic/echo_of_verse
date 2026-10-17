from alembic import context
from sqlalchemy import create_engine, pool
from app.storage import metadata
from app.configuration import configured_database_url

config = context.config
url = configured_database_url() or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

def run_migrations_offline():
    context.configure(url=url, target_metadata=metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Initial PostgreSQL schema for the demo backend."""
from alembic import op
from app.storage import metadata

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    metadata.create_all(bind=op.get_bind())

def downgrade():
    metadata.drop_all(bind=op.get_bind())

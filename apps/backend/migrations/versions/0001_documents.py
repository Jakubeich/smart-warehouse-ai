"""Versioned scenario and result documents."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("documents", sa.Column("kind", sa.String(32), primary_key=True),
                    sa.Column("id", sa.String(100), primary_key=True),
                    sa.Column("payload", sa.JSON(), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("documents")

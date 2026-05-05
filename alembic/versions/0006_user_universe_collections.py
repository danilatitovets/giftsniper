"""user universe collections

Revision ID: 0006_user_universe_collections
Revises: 0005_user_bankroll_settings
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_user_universe_collections"
down_revision = "0005_user_bankroll_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_universe_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_universe_collections_user_id", "user_universe_collections", ["user_id"], unique=False)
    op.create_index("ix_user_universe_collections_collection", "user_universe_collections", ["collection"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_universe_collections_collection", table_name="user_universe_collections")
    op.drop_index("ix_user_universe_collections_user_id", table_name="user_universe_collections")
    op.drop_table("user_universe_collections")

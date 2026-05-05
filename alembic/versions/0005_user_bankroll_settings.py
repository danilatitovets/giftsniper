"""user bankroll settings

Revision ID: 0005_user_bankroll_settings
Revises: 0004_manual_market_user_scope
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_user_bankroll_settings"
down_revision = "0004_manual_market_user_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bankroll_ton", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("goal_ton", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("max_deal_percent", sa.Integer(), nullable=True, server_default="25"))
    op.add_column("users", sa.Column("max_collection_percent", sa.Integer(), nullable=True, server_default="40"))
    op.add_column("users", sa.Column("reserve_percent", sa.Integer(), nullable=True, server_default="20"))


def downgrade() -> None:
    op.drop_column("users", "reserve_percent")
    op.drop_column("users", "max_collection_percent")
    op.drop_column("users", "max_deal_percent")
    op.drop_column("users", "goal_ton")
    op.drop_column("users", "bankroll_ton")

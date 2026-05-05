"""User referrals MVP + bonus_checks_available on users.

Revision ID: 0036_user_referrals_bonus
Revises: 0035_watchlist_notifications
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_user_referrals_bonus"
down_revision = "0035_watchlist_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("bonus_checks_available", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.create_table(
        "user_referrals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("referrer_user_id", sa.Integer(), nullable=False),
        sa.Column("invited_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("bonus_awarded_checks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("milestone_awarded_checks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source_payload", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id", name="user_referrals_pkey"),
        sa.UniqueConstraint("invited_user_id", name="user_referrals_invited_user_id_key"),
        sa.CheckConstraint("referrer_user_id <> invited_user_id", name="user_referrals_no_self"),
        sa.ForeignKeyConstraint(
            ["referrer_user_id"], ["users.id"], ondelete="CASCADE", name="user_referrals_referrer_user_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["invited_user_id"], ["users.id"], ondelete="CASCADE", name="user_referrals_invited_user_id_fkey"
        ),
    )
    op.create_index("ix_user_referrals_referrer_user_id", "user_referrals", ["referrer_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_referrals_referrer_user_id", table_name="user_referrals")
    op.drop_table("user_referrals")
    op.drop_column("users", "bonus_checks_available")

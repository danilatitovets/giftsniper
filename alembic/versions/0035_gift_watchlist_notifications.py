"""Watchlist market notifications (signals) state on gifts.

Revision ID: 0035_watchlist_notifications (<=32 chars for alembic_version.version_num)
Revises: 0034_users_telegram_id_bigint
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_watchlist_notifications"
down_revision = "0034_users_telegram_id_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gifts",
        sa.Column("signals_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("gifts", sa.Column("last_signal_checked_at", sa.DateTime(), nullable=True))
    op.add_column("gifts", sa.Column("last_signal_sent_at", sa.DateTime(), nullable=True))
    op.add_column("gifts", sa.Column("last_signal_normal_ton", sa.Double(), nullable=True))
    op.add_column("gifts", sa.Column("last_signal_floor_ton", sa.Double(), nullable=True))
    op.add_column("gifts", sa.Column("last_signal_market_hash", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("gifts", "last_signal_market_hash")
    op.drop_column("gifts", "last_signal_floor_ton")
    op.drop_column("gifts", "last_signal_normal_ton")
    op.drop_column("gifts", "last_signal_sent_at")
    op.drop_column("gifts", "last_signal_checked_at")
    op.drop_column("gifts", "signals_enabled")

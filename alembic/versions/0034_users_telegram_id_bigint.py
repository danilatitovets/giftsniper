"""Promote users.telegram_id to BIGINT.

Revision ID: 0034_users_telegram_id_bigint
Revises: 0033_nft_global_index
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_users_telegram_id_bigint"
down_revision = "0033_nft_global_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )

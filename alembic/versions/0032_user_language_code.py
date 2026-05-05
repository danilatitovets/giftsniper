"""Add users.language_code for bot UI locale.

Revision ID: 0032_user_language_code
Revises: 0031_ton_subscription_payments
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_user_language_code"
down_revision = "0031_ton_subscription_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("language_code", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "language_code")

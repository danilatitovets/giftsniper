"""manual payment reviewed fields

Revision ID: 0019_manual_payment_review
Revises: 0018_manual_crypto_payments
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_manual_payment_review"
down_revision = "0018_manual_crypto_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manual_payment_requests", sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("manual_payment_requests", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_manual_payment_requests_reviewed_by",
        "manual_payment_requests",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_manual_payment_requests_reviewed_by", "manual_payment_requests", type_="foreignkey")
    op.drop_column("manual_payment_requests", "reviewed_at")
    op.drop_column("manual_payment_requests", "reviewed_by_user_id")

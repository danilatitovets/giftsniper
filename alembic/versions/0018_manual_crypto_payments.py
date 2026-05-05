"""manual crypto payment requests

Revision ID: 0018_manual_crypto_payments
Revises: 0017_payment_webhook_events
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_manual_crypto_payments"
down_revision = "0017_payment_webhook_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_payment_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_plan", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="TON"),
        sa.Column("wallet_address", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("tx_hash", sa.String(length=255), nullable=True),
        sa.Column("proof_text", sa.String(length=4000), nullable=True),
        sa.Column("admin_note", sa.String(length=4000), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_manual_payment_requests_user_id", "manual_payment_requests", ["user_id"], unique=False)
    op.create_index("ix_manual_payment_requests_status", "manual_payment_requests", ["status"], unique=False)
    op.create_index("ix_manual_payment_requests_requested_plan", "manual_payment_requests", ["requested_plan"], unique=False)
    op.create_index("ix_manual_payment_requests_tx_hash", "manual_payment_requests", ["tx_hash"], unique=False)
    op.create_index("ix_manual_payment_requests_created_at", "manual_payment_requests", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_manual_payment_requests_created_at", table_name="manual_payment_requests")
    op.drop_index("ix_manual_payment_requests_tx_hash", table_name="manual_payment_requests")
    op.drop_index("ix_manual_payment_requests_requested_plan", table_name="manual_payment_requests")
    op.drop_index("ix_manual_payment_requests_status", table_name="manual_payment_requests")
    op.drop_index("ix_manual_payment_requests_user_id", table_name="manual_payment_requests")
    op.drop_table("manual_payment_requests")

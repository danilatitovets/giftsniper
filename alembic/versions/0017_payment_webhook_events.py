"""payment webhook events

Revision ID: 0017_payment_webhook_events
Revises: 0016_billing_entitlements
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_payment_webhook_events"
down_revision = "0016_billing_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("plan", sa.String(length=16), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("sanitized_payload_json", sa.String(length=4000), nullable=True),
        sa.Column("sanitized_headers_json", sa.String(length=4000), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_payment_provider_event"),
    )
    op.create_index("ix_payment_webhook_events_provider", "payment_webhook_events", ["provider"], unique=False)
    op.create_index("ix_payment_webhook_events_provider_event_id", "payment_webhook_events", ["provider_event_id"], unique=False)
    op.create_index("ix_payment_webhook_events_status", "payment_webhook_events", ["status"], unique=False)
    op.create_index("ix_payment_webhook_events_user_id", "payment_webhook_events", ["user_id"], unique=False)
    op.create_index("ix_payment_webhook_events_created_at", "payment_webhook_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payment_webhook_events_created_at", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_events_user_id", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_events_status", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_events_provider_event_id", table_name="payment_webhook_events")
    op.drop_index("ix_payment_webhook_events_provider", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")

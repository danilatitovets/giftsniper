"""billing entitlements layer

Revision ID: 0016_billing_entitlements
Revises: 0015_audit_log
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_billing_entitlements"
down_revision = "0015_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("grace_until", sa.DateTime(), nullable=True),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_user_entitlements_user_id"),
    )
    op.create_index("ix_user_entitlements_user_id", "user_entitlements", ["user_id"], unique=False)
    op.create_index("ix_user_entitlements_status", "user_entitlements", ["status"], unique=False)
    op.create_index("ix_user_entitlements_plan", "user_entitlements", ["plan"], unique=False)
    op.create_index("ix_user_entitlements_expires_at", "user_entitlements", ["expires_at"], unique=False)

    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("plan", sa.String(length=16), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", sa.String(length=4000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_billing_events_user_id", "billing_events", ["user_id"], unique=False)
    op.create_index("ix_billing_events_event_type", "billing_events", ["event_type"], unique=False)
    op.create_index("ix_billing_events_provider_event_id", "billing_events", ["provider_event_id"], unique=False)

    op.create_table(
        "entitlement_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=4000), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_entitlement_overrides_user_id", "entitlement_overrides", ["user_id"], unique=False)
    op.create_index("ix_entitlement_overrides_is_active", "entitlement_overrides", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_entitlement_overrides_is_active", table_name="entitlement_overrides")
    op.drop_index("ix_entitlement_overrides_user_id", table_name="entitlement_overrides")
    op.drop_table("entitlement_overrides")

    op.drop_index("ix_billing_events_provider_event_id", table_name="billing_events")
    op.drop_index("ix_billing_events_event_type", table_name="billing_events")
    op.drop_index("ix_billing_events_user_id", table_name="billing_events")
    op.drop_table("billing_events")

    op.drop_index("ix_user_entitlements_expires_at", table_name="user_entitlements")
    op.drop_index("ix_user_entitlements_plan", table_name="user_entitlements")
    op.drop_index("ix_user_entitlements_status", table_name="user_entitlements")
    op.drop_index("ix_user_entitlements_user_id", table_name="user_entitlements")
    op.drop_table("user_entitlements")

"""beta invites

Revision ID: 0020_beta_invites
Revises: 0019_manual_payment_review
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_beta_invites"
down_revision = "0019_manual_payment_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("plan", sa.String(length=16), nullable=False, server_default="pro"),
        sa.Column("days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_beta_invites_code"),
    )
    op.create_index("ix_beta_invites_code", "beta_invites", ["code"], unique=False)
    op.create_index("ix_beta_invites_is_active", "beta_invites", ["is_active"], unique=False)

    op.create_table(
        "beta_invite_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invite_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["invite_id"], ["beta_invites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_beta_invite_redemptions_invite_id", "beta_invite_redemptions", ["invite_id"], unique=False)
    op.create_index("ix_beta_invite_redemptions_user_id", "beta_invite_redemptions", ["user_id"], unique=False)
    op.create_index("ix_beta_invite_redemptions_redeemed_at", "beta_invite_redemptions", ["redeemed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_beta_invite_redemptions_redeemed_at", table_name="beta_invite_redemptions")
    op.drop_index("ix_beta_invite_redemptions_user_id", table_name="beta_invite_redemptions")
    op.drop_index("ix_beta_invite_redemptions_invite_id", table_name="beta_invite_redemptions")
    op.drop_table("beta_invite_redemptions")
    op.drop_index("ix_beta_invites_is_active", table_name="beta_invites")
    op.drop_index("ix_beta_invites_code", table_name="beta_invites")
    op.drop_table("beta_invites")

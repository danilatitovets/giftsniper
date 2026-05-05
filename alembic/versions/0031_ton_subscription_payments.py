"""TON subscription payments and daily NFT check usage.

Revision ID: 0031_ton_subscription_payments
Revises: 0030_trade_signal_link
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_ton_subscription_payments"
down_revision = "0030_trade_signal_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ton_subscription_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan", sa.String(length=16), nullable=False),
        sa.Column("amount_ton", sa.Double(), nullable=False),
        sa.Column("amount_nano", sa.BigInteger(), nullable=False),
        sa.Column("receiver_address", sa.String(length=128), nullable=False),
        sa.Column("comment", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'::character varying")),
        sa.Column("tx_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="ton_subscription_payments_pkey"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="ton_subscription_payments_user_id_fkey"),
        sa.UniqueConstraint("comment", name="uq_ton_subscription_payments_comment"),
        sa.UniqueConstraint("tx_hash", name="uq_ton_subscription_payments_tx_hash"),
    )
    op.create_index("ix_ton_subscription_payments_user_id", "ton_subscription_payments", ["user_id"], unique=False)
    op.create_index("ix_ton_subscription_payments_status", "ton_subscription_payments", ["status"], unique=False)
    op.create_index("ix_ton_subscription_payments_expires_at", "ton_subscription_payments", ["expires_at"], unique=False)

    op.create_table(
        "ton_payment_consumed_tx",
        sa.Column("tx_hash", sa.String(length=128), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tx_hash", name="ton_payment_consumed_tx_pkey"),
        sa.ForeignKeyConstraint(["payment_id"], ["ton_subscription_payments.id"], ondelete="CASCADE", name="ton_payment_consumed_tx_payment_id_fkey"),
    )

    op.create_table(
        "user_nft_check_day",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("checks_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("user_id", "day", name="user_nft_check_day_pkey"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="user_nft_check_day_user_id_fkey"),
    )


def downgrade() -> None:
    op.drop_table("user_nft_check_day")
    op.drop_table("ton_payment_consumed_tx")
    op.drop_index("ix_ton_subscription_payments_expires_at", table_name="ton_subscription_payments")
    op.drop_index("ix_ton_subscription_payments_status", table_name="ton_subscription_payments")
    op.drop_index("ix_ton_subscription_payments_user_id", table_name="ton_subscription_payments")
    op.drop_table("ton_subscription_payments")

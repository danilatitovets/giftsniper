"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("risk_mode", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False),
    )
    op.create_table(
        "gifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("purchase_price_ton", sa.Float(), nullable=True),
        sa.Column("target_price_ton", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "collection", "number", name="uq_user_gift"),
    )
    op.create_table(
        "gift_attributes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gift_id", sa.Integer(), sa.ForeignKey("gifts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trait_type", sa.String(length=255), nullable=False),
        sa.Column("trait_value", sa.String(length=255), nullable=False),
        sa.Column("rarity_percent", sa.Float(), nullable=True),
    )
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("floor_ton", sa.Float(), nullable=False),
        sa.Column("volume_24h_ton", sa.Float(), nullable=True),
        sa.Column("listed_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "trait_floors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("trait_type", sa.String(length=255), nullable=False),
        sa.Column("trait_value", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("floor_ton", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("price_ton", sa.Float(), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("attributes_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("price_ton", sa.Float(), nullable=False),
        sa.Column("sold_at", sa.DateTime(), nullable=False),
        sa.Column("attributes_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("trait_type", sa.String(length=255), nullable=True),
        sa.Column("trait_value", sa.String(length=255), nullable=True),
        sa.Column("max_price_ton", sa.Float(), nullable=True),
        sa.Column("min_price_ton", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gift_id", sa.Integer(), sa.ForeignKey("gifts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quick_sell_price_ton", sa.Float(), nullable=False),
        sa.Column("fair_price_ton", sa.Float(), nullable=False),
        sa.Column("optimistic_price_ton", sa.Float(), nullable=False),
        sa.Column("max_buy_price_ton", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("recommendation", sa.String(length=32), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("alert_rules")
    op.drop_table("sales")
    op.drop_table("listings")
    op.drop_table("trait_floors")
    op.drop_table("market_snapshots")
    op.drop_table("gift_attributes")
    op.drop_table("gifts")
    op.drop_table("users")

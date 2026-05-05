"""manual market user scope

Revision ID: 0004_manual_market_user_scope
Revises: 0003_analysis_profit_fields
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_manual_market_user_scope"
down_revision = "0003_analysis_profit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_snapshots", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_market_snapshots_user_id", "market_snapshots", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_market_snapshots_user_id", "market_snapshots", ["user_id"], unique=False)

    op.add_column("trait_floors", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trait_floors_user_id", "trait_floors", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_trait_floors_user_id", "trait_floors", ["user_id"], unique=False)

    op.add_column("listings", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_listings_user_id", "listings", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_listings_user_id", "listings", ["user_id"], unique=False)

    op.add_column("sales", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_sales_user_id", "sales", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_sales_user_id", "sales", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sales_user_id", table_name="sales")
    op.drop_constraint("fk_sales_user_id", "sales", type_="foreignkey")
    op.drop_column("sales", "user_id")

    op.drop_index("ix_listings_user_id", table_name="listings")
    op.drop_constraint("fk_listings_user_id", "listings", type_="foreignkey")
    op.drop_column("listings", "user_id")

    op.drop_index("ix_trait_floors_user_id", table_name="trait_floors")
    op.drop_constraint("fk_trait_floors_user_id", "trait_floors", type_="foreignkey")
    op.drop_column("trait_floors", "user_id")

    op.drop_index("ix_market_snapshots_user_id", table_name="market_snapshots")
    op.drop_constraint("fk_market_snapshots_user_id", "market_snapshots", type_="foreignkey")
    op.drop_column("market_snapshots", "user_id")

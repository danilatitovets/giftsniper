"""Global NFT collections / aliases / items index for name-based resolution.

Revision ID: 0033_nft_global_index
Revises: 0032_user_language_code
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_nft_global_index"
down_revision = "0032_user_language_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nft_collections_index",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("collection_address", sa.String(length=128), nullable=False),
        sa.Column("collection_name", sa.Text(), nullable=True),
        sa.Column("collection_name_normalized", sa.Text(), nullable=True),
        sa.Column("owner_address", sa.String(length=128), nullable=True),
        sa.Column("next_item_index", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=sa.text("'tonapi'")),
        sa.Column("index_status", sa.String(length=30), nullable=False, server_default=sa.text("'new'")),
        sa.Column("items_indexed_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_index_offset", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="nft_collections_index_pkey"),
        sa.UniqueConstraint("collection_address", name="uq_nft_collections_index_address"),
    )
    op.create_index("ix_nft_collections_index_name_norm", "nft_collections_index", ["collection_name_normalized"])
    op.create_index("ix_nft_collections_index_status", "nft_collections_index", ["index_status"])
    op.create_index("ix_nft_collections_index_last_seen", "nft_collections_index", ["last_seen_at"])
    op.create_index("ix_nft_collections_index_indexed_at", "nft_collections_index", ["indexed_at"])

    op.create_table(
        "nft_collection_aliases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alias_normalized", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("collection_address", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="nft_collection_aliases_pkey"),
        sa.UniqueConstraint("alias_normalized", "collection_address", name="uq_nft_alias_norm_coll"),
    )
    op.create_index("ix_nft_collection_aliases_alias_norm", "nft_collection_aliases", ["alias_normalized"])
    op.create_index("ix_nft_collection_aliases_coll_addr", "nft_collection_aliases", ["collection_address"])
    op.create_index("ix_nft_collection_aliases_confidence", "nft_collection_aliases", ["confidence"])
    op.create_index("ix_nft_collection_aliases_seen_count", "nft_collection_aliases", ["seen_count"])

    op.create_table(
        "nft_items_index",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nft_address", sa.String(length=128), nullable=False),
        sa.Column("collection_address", sa.String(length=128), nullable=False),
        sa.Column("item_index", sa.BigInteger(), nullable=True),
        sa.Column("item_number", sa.BigInteger(), nullable=True),
        sa.Column("item_name", sa.Text(), nullable=True),
        sa.Column("item_name_normalized", sa.Text(), nullable=True),
        sa.Column("base_name", sa.Text(), nullable=True),
        sa.Column("base_name_normalized", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="nft_items_index_pkey"),
        sa.UniqueConstraint("nft_address", name="uq_nft_items_index_address"),
    )
    op.create_index("ix_nft_items_base_norm_num", "nft_items_index", ["base_name_normalized", "item_number"])
    op.create_index("ix_nft_items_coll_num", "nft_items_index", ["collection_address", "item_number"])
    op.create_index("ix_nft_items_coll_idx", "nft_items_index", ["collection_address", "item_index"])
    op.create_index("ix_nft_items_name_norm", "nft_items_index", ["item_name_normalized"])
    op.create_index("ix_nft_items_last_seen", "nft_items_index", ["last_seen_at"])

    op.create_table(
        "nft_index_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("collection_address", sa.String(length=128), nullable=True),
        sa.Column("offset_value", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("limit_value", sa.Integer(), nullable=False, server_default=sa.text("1000")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="nft_index_jobs_pkey"),
    )
    op.create_index("ix_nft_index_jobs_type", "nft_index_jobs", ["job_type"])
    op.create_index("ix_nft_index_jobs_status", "nft_index_jobs", ["status"])
    op.create_index("ix_nft_index_jobs_coll", "nft_index_jobs", ["collection_address"])


def downgrade() -> None:
    op.drop_table("nft_index_jobs")
    op.drop_table("nft_items_index")
    op.drop_table("nft_collection_aliases")
    op.drop_table("nft_collections_index")

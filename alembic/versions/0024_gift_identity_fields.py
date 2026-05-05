"""gift identity fields

Revision ID: 0024_gift_identity_fields
Revises: 0023_feedback_triage_fields
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_gift_identity_fields"
down_revision = "0023_feedback_triage_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gifts", sa.Column("nft_address", sa.String(length=256), nullable=True))
    op.add_column("gifts", sa.Column("collection_address", sa.String(length=256), nullable=True))
    op.add_column("gifts", sa.Column("source_url", sa.String(length=1024), nullable=True))
    op.add_column("gifts", sa.Column("marketplace", sa.String(length=64), nullable=True))
    op.add_column("gifts", sa.Column("canonical_key", sa.String(length=384), nullable=True))
    op.add_column("gifts", sa.Column("normalized_collection", sa.String(length=255), nullable=True))
    op.add_column("gifts", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column("gifts", sa.Column("attributes_json", sa.Text(), nullable=True))
    op.add_column("gifts", sa.Column("last_resolved_at", sa.DateTime(), nullable=True))
    op.add_column("gifts", sa.Column("identity_confidence", sa.Integer(), nullable=True))
    op.create_index("ix_gifts_user_canonical_key", "gifts", ["user_id", "canonical_key"], unique=False)
    op.create_index("ix_gifts_nft_address_lookup", "gifts", ["nft_address"], unique=False)
    op.create_index("ix_gifts_user_normalized_collection", "gifts", ["user_id", "normalized_collection"], unique=False)
    op.create_index("ix_gifts_collection_number_lookup", "gifts", ["collection", "number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gifts_collection_number_lookup", table_name="gifts")
    op.drop_index("ix_gifts_user_normalized_collection", table_name="gifts")
    op.drop_index("ix_gifts_nft_address_lookup", table_name="gifts")
    op.drop_index("ix_gifts_user_canonical_key", table_name="gifts")
    op.drop_column("gifts", "identity_confidence")
    op.drop_column("gifts", "last_resolved_at")
    op.drop_column("gifts", "attributes_json")
    op.drop_column("gifts", "metadata_json")
    op.drop_column("gifts", "normalized_collection")
    op.drop_column("gifts", "canonical_key")
    op.drop_column("gifts", "marketplace")
    op.drop_column("gifts", "source_url")
    op.drop_column("gifts", "collection_address")
    op.drop_column("gifts", "nft_address")

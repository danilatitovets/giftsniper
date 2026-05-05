from app.db.models import Gift


def test_gift_model_has_identity_columns():
    assert "nft_address" in Gift.__table__.c
    assert "canonical_key" in Gift.__table__.c
    assert "normalized_collection" in Gift.__table__.c
    assert "last_resolved_at" in Gift.__table__.c

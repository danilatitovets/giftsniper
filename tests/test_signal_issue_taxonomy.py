from app.db.models import SignalSnapshot
from app.services.signal_review import classify_signal_issue


def test_taxonomy_no_sales_trait_from_note():
    snap = SignalSnapshot(user_id=1, source_command="check", collection="C", number=1)
    assert classify_signal_issue(snap, feedback_notes=["no trait sales at all"]) == "no_sales_trait_issue"


def test_taxonomy_high_confidence_no_trait_sales():
    snap = SignalSnapshot(
        user_id=1,
        source_command="deal",
        collection="C",
        number=1,
        confidence_score=82,
        has_trait_sales=False,
        recommendation="BUY_FOR_FLIP",
        freshness_label="fresh",
    )
    assert classify_signal_issue(snap, feedback_notes=[]) == "no_sales_trait_issue"

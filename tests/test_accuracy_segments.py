from datetime import datetime

from app.db.models import TradeJournal
from app.services.accuracy_report import build_accuracy_segments_report, build_user_accuracy_report


def test_segments_report():
    rows = [
        TradeJournal(
            id=1,
            user_id=1,
            collection="A",
            number=1,
            status="sold",
            buy_price_ton=100.0,
            sell_price_ton=130.0,
            decision_type="BUY_IF_UNDER",
            predicted_confidence=72,
            hold_time_hours=48.0,
            attributes_json=[{"trait_type": "t", "trait_value": "v"}],
        ),
        TradeJournal(
            id=2,
            user_id=1,
            collection="A",
            number=2,
            status="sold",
            buy_price_ton=100.0,
            sell_price_ton=70.0,
            decision_type="SPECULATIVE_BUY",
            predicted_confidence=45,
            hold_time_hours=12.0,
            attributes_json=[],
        ),
        TradeJournal(
            id=3,
            user_id=1,
            collection="B",
            number=3,
            status="sold",
            buy_price_ton=50.0,
            sell_price_ton=55.0,
            decision_type="BUY_IF_UNDER",
            predicted_confidence=80,
        ),
    ]
    txt = build_accuracy_segments_report(rows)
    assert "сегмент" in txt.lower() or "Accuracy" in txt


def test_user_report_include_segments_flag():
    rows = [
        TradeJournal(
            id=1,
            user_id=1,
            collection="A",
            number=1,
            status="sold",
            buy_price_ton=100.0,
            sell_price_ton=130.0,
        )
    ]
    # only one closed — segments block may be skipped in main report (n>=3)
    t1 = build_user_accuracy_report(rows, include_segments=False)
    assert "Accuracy" in t1 or "accuracy" in t1.lower()

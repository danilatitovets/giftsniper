from app.db.models import TradeJournal
from app.services.accuracy_report import build_user_accuracy_report


def test_accuracy_report_empty():
    assert "нет закрытых" in build_user_accuracy_report([])


def test_accuracy_report_closed_trades():
    rows = [
        TradeJournal(
            user_id=1,
            collection="C",
            number=1,
            buy_price_ton=100.0,
            sell_price_ton=130.0,
            status="sold",
            decision_type="BUY_IF_UNDER",
            predicted_max_buy_ton=110.0,
            predicted_list_price_ton=125.0,
            predicted_confidence=70,
        )
    ]
    txt = build_user_accuracy_report(rows)
    assert "Accuracy" in txt or "accuracy" in txt.lower()
    assert "не гарантирует" in txt or "прошлое" in txt

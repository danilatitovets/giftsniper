from datetime import datetime

from app.db.models import TradeJournal
from app.services.trade_accuracy import compute_sold_trade_accuracy


def test_compute_tags_loss_max_buy():
    row = TradeJournal(
        id=1,
        user_id=1,
        collection="C",
        number=1,
        status="open",
        buy_price_ton=100.0,
        buy_date=datetime(2026, 1, 1),
        predicted_max_buy_ton=110.0,
        predicted_list_price_ton=150.0,
        decision_type="BUY_IF_UNDER",
        predicted_confidence=50,
    )
    row.sell_price_ton = 85.0
    acc = compute_sold_trade_accuracy(row, 85.0, sell_date=datetime(2026, 1, 3))
    assert "loss" in acc["accuracy_tags_json"]
    assert acc["realized_profit_ton"] is not None
    assert acc["hold_time_hours"] is not None

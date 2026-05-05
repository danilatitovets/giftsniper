from datetime import datetime

from app.db.models import TradeJournal
from app.services.trade_import import format_trade_export_csv


def test_trade_export_csv_columns():
    rows = [
        TradeJournal(
            id=1,
            user_id=1,
            collection="C",
            number=2,
            buy_price_ton=100.0,
            sell_price_ton=120.0,
            status="sold",
            decision_type="BUY_IF_UNDER",
            predicted_max_buy_ton=110.0,
            predicted_list_price_ton=115.0,
            predicted_confidence=70,
            created_at=datetime(2026, 1, 1),
        )
    ]
    csv = format_trade_export_csv(rows)
    assert "collection" in csv
    assert "C" in csv
    assert "120" in csv

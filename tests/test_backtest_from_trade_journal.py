import json
from datetime import datetime

from app.db.models import TradeJournal
from app.services.backtesting import journal_rows_to_backtest_pairs, run_backtest


def test_journal_to_backtest_pairs():
    plan = {
        "normal_list_price_ton": 118,
        "max_buy_price_ton": 110,
        "safe_buy_price_ton": 95,
        "quick_sell_price_ton": 90,
        "stop_loss_price_ton": 85,
    }
    prediction_json = json.dumps({"precision_plan_json": json.dumps(plan)})
    rows = [
        TradeJournal(
            id=1,
            user_id=1,
            collection="C",
            number=1,
            status="sold",
            buy_price_ton=100.0,
            sell_price_ton=120.0,
            buy_date=datetime(2026, 1, 1),
            sell_date=datetime(2026, 1, 2),
            decision_type="BUY_IF_UNDER",
            predicted_max_buy_ton=110.0,
            predicted_list_price_ton=118.0,
            predicted_confidence=70,
            prediction_json=prediction_json,
        )
    ]
    pairs = journal_rows_to_backtest_pairs(rows)
    assert len(pairs) == 1
    rep = run_backtest(pairs)
    assert rep.total_cases == 1

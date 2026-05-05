import json

from app.db.models import TradeJournal


def test_trade_journal_model_has_prediction_columns():
    t = TradeJournal(
        user_id=1,
        collection="Ice Cream",
        number=1,
        buy_price_ton=10.0,
        prediction_json=json.dumps({"decision_type": "BUY_IF_UNDER"}),
        decision_type="BUY_IF_UNDER",
        predicted_max_buy_ton=12.0,
        predicted_safe_buy_ton=9.0,
        predicted_list_price_ton=14.0,
        predicted_roi_percent=11.0,
        predicted_confidence=72,
    )
    assert t.predicted_confidence == 72

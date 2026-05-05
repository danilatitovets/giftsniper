from app.bot.handlers.portfolio import _sell_priority


def test_sell_plan_orders_by_action_priority():
    assert _sell_priority("SELL_FAST") < _sell_priority("LIST_HIGHER")
    assert _sell_priority("LIST_HIGHER") < _sell_priority("HOLD")
    assert _sell_priority("HOLD") < _sell_priority("AVOID")

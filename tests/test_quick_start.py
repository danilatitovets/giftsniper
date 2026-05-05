from app.bot.messages import QUICK_START_TEXT


def test_quick_start_steps():
    assert "Шаг 1" in QUICK_START_TEXT
    assert "/check" in QUICK_START_TEXT
    assert "/lite_plan" in QUICK_START_TEXT
    assert "/trade_add" in QUICK_START_TEXT
    assert "/trade_sell" in QUICK_START_TEXT

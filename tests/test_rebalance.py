from app.bot.handlers.portfolio import _build_rebalance_hints


def test_rebalance_suggests_reducing_concentration():
    hints = _build_rebalance_hints(["82% портфеля в Ice Cream — выше лимита 40%"])
    assert any("снизить концентрацию" in h for h in hints)

from app.bot.handlers.market import _parts_pipe, _to_price


def test_manual_floor_parser():
    parts = _parts_pipe("/market_set_floor Ice Cream | 186", "/market_set_floor")
    assert parts == ["Ice Cream", "186"]


def test_manual_trait_floor_parser():
    parts = _parts_pipe("/market_set_trait_floor Ice Cream | Symbol | Moon | 240", "/market_set_trait_floor")
    assert parts == ["Ice Cream", "Symbol", "Moon", "240"]


def test_manual_sale_parser():
    parts = _parts_pipe("/market_set_sale Ice Cream | 217467 | 230", "/market_set_sale")
    assert parts == ["Ice Cream", "217467", "230"]


def test_invalid_manual_price():
    assert _to_price("-1") is None
    assert _to_price("abc") is None

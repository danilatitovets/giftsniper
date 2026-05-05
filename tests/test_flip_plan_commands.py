from app.bot.handlers.flip_handlers import _parse_budget, _parse_compound


def test_parse_budget_flip_plan():
    assert _parse_budget("/flip_plan 300", "/flip_plan") == 300.0
    assert _parse_budget("/flip_plan 12,5", "/flip_plan") == 12.5
    assert _parse_budget("/flip_plan", "/flip_plan") is None


def test_parse_compound():
    a, b = _parse_compound("/compound_plan 300 | 1000")
    assert a == 300.0 and b == 1000.0

from app.bot.handlers.portfolio import _parse_positive_amount, _parse_risk


def test_bank_set_validates_positive_amount():
    assert _parse_positive_amount("/bank_set 500", "/bank_set") == 500.0
    assert _parse_positive_amount("/bank_set -1", "/bank_set") is None
    assert _parse_positive_amount("/bank_set abc", "/bank_set") is None


def test_risk_set_validates_percentages():
    assert _parse_risk("/risk_set 25 | 40 | 20") == (25, 40, 20)
    assert _parse_risk("/risk_set 101 | 40 | 20") is None
    assert _parse_risk("/risk_set x | 40 | 20") is None

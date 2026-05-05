from types import SimpleNamespace

from app.services.payment_readiness import manual_prices_configured


def test_manual_prices_configured_all_positive():
    s = SimpleNamespace(manual_payment_starter_ton=1.0, manual_payment_pro_ton=2.0, manual_payment_trader_ton=3.0)
    assert manual_prices_configured(s) is True


def test_manual_prices_missing_zero():
    s = SimpleNamespace(manual_payment_starter_ton=0.0, manual_payment_pro_ton=2.0, manual_payment_trader_ton=3.0)
    assert manual_prices_configured(s) is False

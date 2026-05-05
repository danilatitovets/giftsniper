from app.schemas.market_brain import PrecisionPricePlan
from app.services.price_explain import compare_price_plans, format_price_change_explanation


def _p(safe, conf):
    return PrecisionPricePlan(
        safe_buy_price_ton=safe,
        max_buy_price_ton=safe + 20,
        aggressive_buy_price_ton=safe + 5,
        quick_flip_list_price_ton=120,
        normal_list_price_ton=130,
        high_list_price_ton=140,
        quick_sell_price_ton=90,
        stop_loss_price_ton=85,
        downside_price_ton=80,
        upside_price_ton=145,
        expected_net_sale_ton=125,
        expected_net_profit_ton=5,
        expected_roi_percent=10,
        marketplace_fee_percent=5,
        estimated_extra_costs_ton=0,
        time_to_sell_estimate="3d",
        confidence_score=conf,
        risk_score=40,
        liquidity_score=60,
    )


def test_compare_price_plans_detects_floor_safe_shift():
    old, new = _p(100, 70), _p(110, 65)
    diffs = compare_price_plans(old, new)
    assert any("safe_buy" in d for d in diffs)
    assert any("confidence" in d for d in diffs)


def test_format_price_change_empty():
    assert "не обнаружено" in format_price_change_explanation([])

from app.schemas.market_brain import PrecisionPricePlan
from app.services.pricing import format_precision_price_plan_extended


def test_extended_price_plan_includes_bounds_and_disclaimer():
    p = PrecisionPricePlan(
        safe_buy_price_ton=100,
        max_buy_price_ton=120,
        aggressive_buy_price_ton=110,
        quick_flip_list_price_ton=130,
        normal_list_price_ton=135,
        high_list_price_ton=145,
        quick_sell_price_ton=95,
        stop_loss_price_ton=90,
        downside_price_ton=85,
        upside_price_ton=150,
        expected_net_sale_ton=128,
        expected_net_profit_ton=8,
        expected_roi_percent=10,
        marketplace_fee_percent=5,
        estimated_extra_costs_ton=0,
        time_to_sell_estimate="3d",
        confidence_score=72,
        risk_score=35,
        liquidity_score=65,
    )
    txt = format_precision_price_plan_extended(p, listing_price_ton=105.0, confidence_explanation="Test confidence block.")
    assert "Precision price plan" in txt
    assert "Почему не выше" in txt
    assert "не обещание прибыли" in txt
    assert "Test confidence" in txt

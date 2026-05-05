from app.config import get_settings
from app.schemas.analysis import FlipAnalysisResult
from app.schemas.market_brain import PrecisionPricePlan
from app.services.decision_engine import make_buy_decision


def _plan(safe=100.0, max_buy=120.0, liq=65.0):
    return PrecisionPricePlan(
        safe_buy_price_ton=safe,
        max_buy_price_ton=max_buy,
        aggressive_buy_price_ton=min(max_buy, safe * 1.05),
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
        confidence_score=75,
        risk_score=40,
        liquidity_score=liq,
    )


def _base(conf=75, risk=40):
    return FlipAnalysisResult(
        buy_zone_min_ton=100,
        buy_zone_max_ton=120,
        quick_sell_price_ton=95,
        fair_price_ton=120,
        list_price_ton=135,
        optimistic_price_ton=140,
        stop_price_ton=90,
        marketplace_fee_percent=5,
        expected_net_sale_ton=128,
        expected_profit_ton=5,
        expected_roi_percent=12,
        liquidity_score=65,
        risk_score=risk,
        confidence_score=conf,
        recommendation="BUY_FOR_FLIP",
        reasons=[],
    )


def test_buy_above_max_is_avoid():
    settings = get_settings()
    d = make_buy_decision(
        buy_price=200,
        plan=_plan(),
        base=_base(),
        trait_opp_score=50,
        combined_rarity_adj=50,
        sales_count=8,
        market_regime=None,
        settings=settings,
        strong_buy_trait_ok=True,
        spread_percent=10,
    )
    assert d.decision == "AVOID"


def test_strong_buy_blocked_without_trait_confirmation():
    settings = get_settings()
    d = make_buy_decision(
        buy_price=99,
        plan=_plan(safe=100, max_buy=120, liq=70),
        base=_base(conf=80, risk=35),
        trait_opp_score=50,
        combined_rarity_adj=55,
        sales_count=10,
        market_regime=None,
        settings=settings,
        strong_buy_trait_ok=False,
        spread_percent=8,
    )
    assert d.decision != "STRONG_BUY"

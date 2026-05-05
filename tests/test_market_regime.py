from app.schemas.analysis import CollectionIntelligence
from app.services.market_regime import evaluate_universe_regime


def _report(regime: str, liq: int, avg: int, fresh: str, real: bool, manual: bool, sales: int):
    return CollectionIntelligence(
        collection="Ice Cream",
        regime=regime,
        relative_strength_score=avg,
        avg_opportunity_score=avg,
        best_opportunity_score=avg + 5,
        liquidity_score=liq,
        freshness_label=fresh,
        real_data_available=real,
        manual_data_available=manual,
        recent_sales_count=sales,
        warnings=[],
        recommendation="WATCH",
    )


def test_fresh_real_sales_neutral_or_risk_on():
    regime = evaluate_universe_regime([_report("neutral", 70, 72, "fresh", True, False, 4)])
    assert regime.regime in {"risk_on", "neutral"}


def test_mostly_manual_no_sales_data_poor():
    regime = evaluate_universe_regime([_report("data_poor", 30, 35, "stale", False, True, 0)])
    assert regime.regime == "data_poor"


def test_low_liquidity_can_be_illiquid():
    regime = evaluate_universe_regime([_report("illiquid", 20, 55, "fresh", True, False, 0)])
    assert regime.regime in {"illiquid", "data_poor"}


def test_stale_data_can_be_risk_off():
    regime = evaluate_universe_regime([_report("risk_off", 60, 58, "old", True, True, 1)])
    assert regime.regime in {"risk_off", "data_poor"}

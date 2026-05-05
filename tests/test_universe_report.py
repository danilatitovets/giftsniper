from app.schemas.analysis import CollectionIntelligence
from app.services.market_regime import (
    evaluate_universe_regime,
    format_market_regime_report,
    get_regime_allocation_multiplier,
)


def test_market_regime_formats_report():
    regime = evaluate_universe_regime(
        [
            CollectionIntelligence(
                collection="Ice Cream",
                regime="neutral",
                relative_strength_score=60,
                avg_opportunity_score=62,
                best_opportunity_score=75,
                liquidity_score=55,
                freshness_label="stale",
                real_data_available=True,
                manual_data_available=True,
                recent_sales_count=2,
                warnings=[],
                recommendation="WATCH",
            )
        ]
    )
    text = format_market_regime_report(regime)
    assert "Режим:" in text
    assert "Score:" in text


def test_capital_plan_universe_applies_regime_multiplier():
    assert get_regime_allocation_multiplier("risk_off") == 0.45

"""Stage 34: sale probability caps and drivers."""

from app.services.capital_multiplier import FlipCandidate, estimate_sale_probability


def test_mock_caps_probability():
    c = FlipCandidate(
        collection="X",
        buy_price_ton=10.0,
        liquidity_score=80,
        confidence_score=85,
        risk_score=40,
        has_recent_sales=True,
        has_trait_sales=True,
        decision_type="STRONG_BUY",
        source_quality="mock",
        freshness_label="fresh",
    )
    p = estimate_sale_probability(c, {"market_regime": "risk_on", "recent_sales_count": 8})
    assert p <= 40.5


def test_no_recent_sales_cap():
    c = FlipCandidate(
        collection="X",
        buy_price_ton=10.0,
        liquidity_score=70,
        confidence_score=80,
        risk_score=45,
        has_recent_sales=False,
        has_trait_sales=True,
        decision_type="BUY_IF_UNDER",
        source_quality="real",
        freshness_label="fresh",
    )
    p = estimate_sale_probability(c, {"recent_sales_count": 0, "market_regime": "neutral"})
    assert p <= 55.5


def test_rare_no_trait_sales_cap():
    c = FlipCandidate(
        collection="X",
        buy_price_ton=10.0,
        liquidity_score=60,
        confidence_score=75,
        risk_score=50,
        has_recent_sales=True,
        has_trait_sales=False,
        decision_type="SPECULATIVE_BUY",
        rarity_score=50.0,
        source_quality="real",
        freshness_label="fresh",
    )
    p = estimate_sale_probability(
        c,
        {
            "recent_sales_count": 5,
            "market_regime": "neutral",
            "max_trait_recent_sales": 0,
            "liquidity_adjusted_rarity": 50,
            "rare_trait_no_sales": True,
        },
    )
    assert p <= 45.5


def test_old_data_cap():
    c = FlipCandidate(
        collection="X",
        buy_price_ton=10.0,
        liquidity_score=70,
        confidence_score=80,
        risk_score=45,
        has_recent_sales=True,
        has_trait_sales=True,
        source_quality="real",
        freshness_label="old",
    )
    p = estimate_sale_probability(c, {"recent_sales_count": 10})
    assert p <= 35.5


def test_illiquid_regime_cap():
    c = FlipCandidate(
        collection="X",
        buy_price_ton=10.0,
        liquidity_score=75,
        confidence_score=80,
        risk_score=45,
        has_recent_sales=True,
        has_trait_sales=True,
        source_quality="real",
        freshness_label="fresh",
    )
    p = estimate_sale_probability(c, {"market_regime": "illiquid", "recent_sales_count": 6})
    assert p <= 40.5


def test_low_liquidity_reduces_probability_vs_high():
    base_ctx = {"recent_sales_count": 6, "market_regime": "neutral", "floor_ton": 10.0, "spread_percent": 15}
    hi = FlipCandidate(
        collection="X",
        buy_price_ton=9.0,
        liquidity_score=85,
        confidence_score=75,
        risk_score=45,
        has_recent_sales=True,
        has_trait_sales=True,
        source_quality="real",
        freshness_label="fresh",
    )
    lo = hi.model_copy(update={"liquidity_score": 25})
    assert estimate_sale_probability(lo, base_ctx) < estimate_sale_probability(hi, base_ctx)

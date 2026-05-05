"""Stage 34: capital multiplier plan rules."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.analysis import FlipAnalysisResult, OpportunityScore
from app.services.capital_multiplier import (
    CapitalMultiplierPlan,
    FlipCandidate,
    build_capital_multiplier_plan,
    format_capital_multiplier_plan,
    rank_candidates_for_budget,
)


def _opp_row(price: float, max_buy: float, profit: float, decision: str = "BUY_IF_UNDER", risk: int = 50):
    listing = SimpleNamespace(collection="Ice Cream", number=1, price_ton=price, source="getgems", url="http://x")
    estimate = FlipAnalysisResult(
        buy_zone_min_ton=max_buy * 0.9,
        buy_zone_max_ton=max_buy,
        quick_sell_price_ton=price * 1.1,
        fair_price_ton=price * 1.05,
        list_price_ton=price * 1.2,
        optimistic_price_ton=price * 1.3,
        stop_price_ton=price * 0.85,
        marketplace_fee_percent=5.0,
        expected_net_sale_ton=price * 1.15,
        expected_profit_ton=profit,
        expected_roi_percent=15.0,
        liquidity_score=70,
        risk_score=risk,
        confidence_score=72,
        recommendation="BUY_FOR_FLIP",
        safe_buy_price_ton=max_buy * 0.95,
        aggressive_buy_price_ton=max_buy,
        normal_list_price_ton=price * 1.2,
        high_list_price_ton=price * 1.3,
        decision_type=decision,
        precision_plan_json=f'{{"max_buy_price_ton": {max_buy}, "safe_buy_price_ton": {max_buy * 0.95}, '
        f'"normal_list_price_ton": {price * 1.2}, "high_list_price_ton": {price * 1.3}, '
        f'"quick_sell_price_ton": {price * 1.1}, "stop_loss_price_ton": {price * 0.85}, '
        f'"expected_net_sale_ton": {price * 1.15}, "expected_net_profit_ton": {profit}, '
        f'"expected_roi_percent": 15, "marketplace_fee_percent": 5, "estimated_extra_costs_ton": 0, '
        f'"liquidity_score": 70, "risk_score": {risk}, "confidence_score": 72, "warnings": []}}',
        market_intelligence_json='{"collection_floor_ton": 80, "median_sale_price_ton": 120}',
        max_trait_recent_sales=2,
    )
    score = OpportunityScore(
        total_score=70,
        roi_score=70,
        profit_score=70,
        liquidity_score=70,
        confidence_score=72,
        freshness_score=70,
        risk_penalty=risk,
        source_quality_score=70,
        final_rank_label="A_TIER",
    )
    stats = {
        "floor_freshness": "fresh",
        "sales_freshness": "fresh",
        "listings_freshness": "fresh",
        "real_sales_count": 5,
        "sales_age_minutes": 60,
        "spread_percent": 12.0,
    }
    quality = SimpleNamespace(warnings=[], is_mock_data=False, sources_used=["getgems"])
    return {
        "listing": listing,
        "estimate": estimate,
        "score": score,
        "freshness_label": "fresh",
        "real_sales_count": 5,
        "stats": stats,
        "quality": quality,
    }


@pytest.mark.asyncio
async def test_budget_reserve_and_max_per_deal():
    user = SimpleNamespace(id=1, risk_mode="normal", reserve_percent=20, max_deal_percent=25)
    settings = SimpleNamespace(
        min_profit_ton=1.0,
        capital_multiplier_min_sale_probability=30,
        capital_multiplier_min_confidence=40,
        capital_multiplier_max_risk=85,
        capital_multiplier_speculative_max_percent=15.0,
        capital_multiplier_top_n=5,
    )
    row = _opp_row(price=50.0, max_buy=90.0, profit=10.0)
    with patch(
        "app.services.capital_multiplier.gather_ranked_with_market_regime",
        new=AsyncMock(return_value=([row], "neutral")),
    ):
        plan, _rows = await build_capital_multiplier_plan(
            user,
            300.0,
            settings,
            universe_collections=["Ice Cream"],
            gifts_for_regime=[],
        )
    assert isinstance(plan, CapitalMultiplierPlan)
    assert plan.reserve_ton == 60.0
    assert plan.available_after_reserve_ton == 240.0
    assert plan.max_per_deal_ton == 75.0


@pytest.mark.asyncio
async def test_candidate_above_max_buy_skipped():
    user = SimpleNamespace(id=1, risk_mode="normal", reserve_percent=20, max_deal_percent=40)
    settings = SimpleNamespace(
        min_profit_ton=1.0,
        capital_multiplier_min_sale_probability=30,
        capital_multiplier_min_confidence=40,
        capital_multiplier_max_risk=85,
        capital_multiplier_speculative_max_percent=15.0,
        capital_multiplier_top_n=5,
    )
    row = _opp_row(price=200.0, max_buy=50.0, profit=20.0)
    with patch(
        "app.services.capital_multiplier.gather_ranked_with_market_regime",
        new=AsyncMock(return_value=([row], "neutral")),
    ):
        plan, _ = await build_capital_multiplier_plan(
            user,
            500.0,
            settings,
            universe_collections=["Ice Cream"],
            gifts_for_regime=[],
        )
    assert not plan.selected_candidates
    assert any("max buy" in s.reason.lower() for s in plan.skipped_candidates)


@pytest.mark.asyncio
async def test_speculative_allocation_limited():
    user = SimpleNamespace(id=1, risk_mode="normal", reserve_percent=20, max_deal_percent=50)
    settings = SimpleNamespace(
        min_profit_ton=1.0,
        capital_multiplier_min_sale_probability=20,
        capital_multiplier_min_confidence=40,
        capital_multiplier_max_risk=85,
        capital_multiplier_speculative_max_percent=15.0,
        capital_multiplier_top_n=5,
    )
    rows = [
        _opp_row(price=40.0, max_buy=80.0, profit=8.0, decision="SPECULATIVE_BUY"),
        _opp_row(price=40.0, max_buy=80.0, profit=8.0, decision="SPECULATIVE_BUY"),
    ]
    rows[1]["listing"] = SimpleNamespace(
        collection="Ice Cream", number=2, price_ton=40.0, source="getgems", url="http://y"
    )
    with patch(
        "app.services.capital_multiplier.gather_ranked_with_market_regime",
        new=AsyncMock(return_value=(rows, "neutral")),
    ):
        plan, _ = await build_capital_multiplier_plan(
            user,
            200.0,
            settings,
            universe_collections=["Ice Cream"],
            gifts_for_regime=[],
        )
    spec = [x for x in plan.selected_candidates if x.is_speculative]
    assert sum(x.buy_price_ton for x in spec) <= plan.max_speculative_deal_ton + 1.0


def test_rank_candidates_sorts_by_efficiency():
    a = FlipCandidate(
        collection="A",
        buy_price_ton=10.0,
        expected_roi_percent=40.0,
        sale_probability_percent=80.0,
        confidence_score=80,
        liquidity_score=80,
        risk_score=35,
        probability_weighted_profit_ton=5.0,
        capital_efficiency_score=0.0,
    )
    b = a.model_copy(update={"collection": "B", "expected_roi_percent": 10.0, "sale_probability_percent": 40.0})
    ranked = rank_candidates_for_budget([b, a], 100.0, None)
    assert ranked[0].collection == "A"


def test_flip_plan_format_includes_buy_list_quick_stop_probability():
    plan = CapitalMultiplierPlan(
        starting_budget_ton=300,
        reserve_ton=60,
        available_after_reserve_ton=240,
        max_per_deal_ton=75,
        max_speculative_deal_ton=30,
        selected_candidates=[
            FlipCandidate(
                collection="Ice Cream",
                number=123,
                buy_price_ton=100,
                max_buy_price_ton=110,
                safe_buy_price_ton=100,
                list_price_ton=130,
                high_list_price_ton=140,
                quick_sell_price_ton=120,
                stop_loss_price_ton=90,
                expected_profit_ton=20,
                expected_roi_percent=20,
                sale_probability_percent=65.0,
                capital_efficiency_score=40.0,
                risk_score=50,
                confidence_score=70,
                reasons=["test"],
            )
        ],
    )
    text = format_capital_multiplier_plan(plan)
    assert "Купить до" in text
    assert "Quick sell" in text
    assert "Stop" in text
    assert "Вероятность" in text

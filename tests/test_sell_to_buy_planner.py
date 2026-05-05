"""Stage 34: sell-to-buy only suggests replacement when improvement is meaningful."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sell_to_buy_planner import build_sell_to_buy_plan


@pytest.mark.asyncio
async def test_sell_to_buy_no_replacement_without_improvement():
    user = SimpleNamespace(id=1, risk_mode="normal")
    settings = SimpleNamespace(default_marketplace_fee_percent=5.0)
    gift = SimpleNamespace(id=1, collection="Ice Cream", number=1, purchase_price_ton=100.0)

    async def fake_analyze(*_a, **_k):
        from app.schemas.analysis import FlipAnalysisResult

        return FlipAnalysisResult(
            buy_zone_min_ton=90,
            buy_zone_max_ton=110,
            quick_sell_price_ton=105,
            fair_price_ton=108,
            list_price_ton=120,
            optimistic_price_ton=130,
            stop_price_ton=85,
            marketplace_fee_percent=5.0,
            expected_net_sale_ton=114,
            expected_profit_ton=5,
            expected_roi_percent=5,
            liquidity_score=60,
            risk_score=45,
            confidence_score=75,
            recommendation="HOLD",
            decision_type="HOLD",
            max_trait_recent_sales=1,
        )

    with (
        patch("app.services.sell_to_buy_planner.AnalyzerService") as A,
        patch("app.services.sell_to_buy_planner.create_market_source", return_value=MagicMock()),
        patch(
            "app.services.sell_to_buy_planner.gather_ranked_with_market_regime",
            new=AsyncMock(return_value=([], None)),
        ),
    ):
        A.return_value.analyze_gift = AsyncMock(side_effect=fake_analyze)
        plan = await build_sell_to_buy_plan(user, settings, gifts=[gift], universe_collections=["Ice Cream"])
    assert not plan.replacement_buys

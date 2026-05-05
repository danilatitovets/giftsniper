from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers.flip_handlers import _snapshots_for_flip_rows


@pytest.mark.asyncio
async def test_snapshots_for_flip_rows_calls_create():
    row = {
        "listing": SimpleNamespace(collection="Ice Cream", number=99, price_ton=10.0, source="getgems", url="u"),
        "estimate": SimpleNamespace(
            decision_type="BUY_IF_UNDER",
            recommendation="BUY_FOR_FLIP",
            safe_buy_price_ton=8.0,
            buy_zone_max_ton=9.0,
            list_price_ton=12.0,
            quick_sell_price_ton=11.0,
            stop_price_ton=7.0,
            expected_profit_ton=1.0,
            expected_roi_percent=10.0,
            confidence_score=70,
            risk_score=40,
            liquidity_score=60,
            reasons=[],
            max_trait_recent_sales=0,
        ),
        "stats": {"floor_freshness": "fresh", "sales_freshness": "fresh", "real_sales_count": 2},
        "quality": SimpleNamespace(warnings=[], sources_used=["getgems"]),
        "score": SimpleNamespace(final_rank_label="A_TIER", total_score=70),
    }
    session = MagicMock()
    with patch(
        "app.bot.handlers.flip_handlers.create_signal_snapshot_from_analysis",
        new=AsyncMock(return_value=SimpleNamespace(id=42, collection="Ice Cream", number=99, decision_type="BUY_IF_UNDER", recommendation="x")),
    ) as create:
        lines = await _snapshots_for_flip_rows(session, user_id=1, rows=[row], source_command="budget_deals", top_n=3)
    assert create.await_count == 1
    assert any("42" in ln for ln in lines)

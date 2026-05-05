from types import SimpleNamespace

from app.bot.handlers.analysis import _passes_scan_filters
from app.config import Settings
from app.services.opportunity_scoring import calculate_opportunity_score


def _settings():
    return Settings(BOT_TOKEN="x", DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db")


def _estimate(profit: float, roi: float, confidence: int, risk: int, recommendation: str):
    return SimpleNamespace(
        expected_profit_ton=profit,
        expected_roi_percent=roi,
        confidence_score=confidence,
        risk_score=risk,
        recommendation=recommendation,
    )


def test_scan_filters_bad_deals():
    s = _settings()
    bad = _estimate(profit=1, roi=3, confidence=30, risk=90, recommendation="BUY_FOR_FLIP")
    assert _passes_scan_filters(bad, s, freshness_label="old", is_mock=True, real_sales_count=0) is False


def test_old_data_without_sales_blocks_high_tier():
    score = calculate_opportunity_score(
        SimpleNamespace(expected_roi_percent=45, expected_profit_ton=60, liquidity_score=70, confidence_score=70, risk_score=30, recommendation="BUY_FOR_FLIP"),
        SimpleNamespace(sources_used=["Manual"], is_mock_data=False),
        {"label": "old", "has_recent_sales": False},
    )
    assert score.final_rank_label in {"B_TIER", "C_TIER", "AVOID"}

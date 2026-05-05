from types import SimpleNamespace

from app.services.opportunity_scoring import calculate_opportunity_score, rank_opportunities, format_score_breakdown


def _result(roi: float, profit: float, liquidity: int = 60, confidence: int = 65, risk: int = 40, rec: str = "BUY_FOR_FLIP"):
    return SimpleNamespace(
        expected_roi_percent=roi,
        expected_profit_ton=profit,
        liquidity_score=liquidity,
        confidence_score=confidence,
        risk_score=risk,
        recommendation=rec,
    )


def _quality(sources, is_mock=False):
    return SimpleNamespace(sources_used=sources, is_mock_data=is_mock)


def test_positive_roi_gives_higher_score():
    hi = calculate_opportunity_score(_result(40, 40), _quality(["Getgems"]), {"label": "fresh", "has_recent_sales": True})
    lo = calculate_opportunity_score(_result(5, 40), _quality(["Getgems"]), {"label": "fresh", "has_recent_sales": True})
    assert hi.total_score > lo.total_score


def test_negative_profit_caps_score():
    s = calculate_opportunity_score(_result(30, -2), _quality(["Getgems"]), {"label": "fresh", "has_recent_sales": True})
    assert s.total_score <= 35


def test_mock_signal_max_c_tier():
    s = calculate_opportunity_score(_result(60, 80), _quality(["mock"], is_mock=True), {"label": "fresh", "has_recent_sales": True})
    assert s.final_rank_label in {"C_TIER", "AVOID"}


def test_manual_stale_max_b_tier():
    s = calculate_opportunity_score(_result(50, 50), _quality(["Manual"]), {"label": "stale", "has_recent_sales": True})
    assert s.final_rank_label in {"B_TIER", "C_TIER", "AVOID"}


def test_high_risk_lowers_total_score():
    low_risk = calculate_opportunity_score(_result(40, 40, risk=20), _quality(["Getgems"]), {"label": "fresh", "has_recent_sales": True})
    high_risk = calculate_opportunity_score(_result(40, 40, risk=90), _quality(["Getgems"]), {"label": "fresh", "has_recent_sales": True})
    assert low_risk.total_score > high_risk.total_score


def test_real_fresh_can_rank_higher_than_manual():
    real = calculate_opportunity_score(_result(30, 30), _quality(["Getgems"]), {"label": "fresh", "has_recent_sales": True})
    manual = calculate_opportunity_score(_result(30, 30), _quality(["Manual"]), {"label": "fresh", "has_recent_sales": True})
    assert real.total_score >= manual.total_score


def test_rank_opportunities_sorts_desc():
    a = {"score": calculate_opportunity_score(_result(10, 10), _quality(["Manual"]), {"label": "fresh", "has_recent_sales": True})}
    b = {"score": calculate_opportunity_score(_result(40, 40), _quality(["Getgems"]), {"label": "fresh", "has_recent_sales": True})}
    ranked = rank_opportunities([a, b])
    assert ranked[0]["score"].total_score >= ranked[1]["score"].total_score


def test_deal_score_breakdown_contains_components():
    score = calculate_opportunity_score(_result(30, 20), _quality(["Manual"]), {"label": "stale", "has_recent_sales": False})
    text = format_score_breakdown(score)
    assert "ROI:" in text
    assert "Profit:" in text
    assert "Risk penalty:" in text

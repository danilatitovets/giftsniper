from app.services.confidence_calibration import (
    calculate_data_coverage_score,
    calculate_prediction_confidence,
    explain_confidence_cap,
    format_confidence_explanation,
)


def test_no_sales_lowers_coverage():
    a = calculate_data_coverage_score(
        real_sales_count=0,
        listing_count=2,
        max_trait_sales=0,
        has_floor=True,
        source_mock=False,
        source_manual=False,
        freshness_label="fresh",
    )
    b = calculate_data_coverage_score(
        real_sales_count=5,
        listing_count=10,
        max_trait_sales=2,
        has_floor=True,
        source_mock=False,
        source_manual=False,
        freshness_label="fresh",
    )
    assert a < b


def test_prediction_confidence_blend():
    v = calculate_prediction_confidence(80, 40, journal_accuracy_hint=60)
    assert 40 <= v <= 100


def test_format_confidence_explanation_no_guarantee():
    s = format_confidence_explanation(
        sources_used=["getgems"],
        sales_count=0,
        trait_sales_max=0,
        spread_percent=20,
        freshness_label="stale",
        capped_reason="test cap",
    )
    assert "не гарантия" in s.lower()


def test_explain_cap():
    assert "55" in explain_confidence_cap("stale", 70, 55)

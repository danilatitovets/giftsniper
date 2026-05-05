import pytest

from app.services.signal_quality import format_signal_quality_report


def test_signal_quality_report_counts_good_bad():
    text = format_signal_quality_report(
        {
            "period_days": 7,
            "signal_good_count": 2,
            "signal_bad_count": 3,
            "latest_bad_reasons": ["bad spread"],
            "latest_good_examples": ["good quick sell"],
        },
        ratio=0.66,
    )
    assert "signal_good: 2" in text
    assert "signal_bad: 3" in text
    assert "review scan thresholds" in text

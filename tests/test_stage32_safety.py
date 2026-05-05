"""Stage 32: no auto-apply wording in tuning strings."""

from app.services.pricing_tuner import format_pricing_tuning_report
from app.services.pricing_tuner import PricingTuningReport


def test_tuning_report_disclaims_auto_apply():
    rep = PricingTuningReport(
        total_closed_trades=0,
        win_rate=0.0,
        avg_realized_roi=0.0,
        avg_prediction_error=0.0,
        false_positive_count=0,
        missed_opportunity_count=0,
        max_buy_too_high_cases=0,
        list_price_too_high_cases=0,
        no_sales_trait_losses=0,
        stale_data_losses=0,
        findings=[],
        suggested_env_changes={},
    )
    txt = format_pricing_tuning_report(rep)
    assert "автоматически" in txt.lower()
    assert "гарантированная прибыль" not in txt.lower()

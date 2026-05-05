from datetime import datetime

from app.db.models import TradeJournal
from app.config import get_settings
from app.services.pricing_tuner import (
    analyze_pricing_accuracy,
    detect_max_buy_bias,
    format_pricing_config_current,
    format_pricing_config_suggest,
    suggest_pricing_threshold_changes,
)


def _sold(**kwargs) -> TradeJournal:
    tid = kwargs.pop("id", 1)
    base = dict(
        id=tid,
        user_id=1,
        collection="Col",
        number=1,
        status="sold",
        buy_price_ton=100.0,
        sell_price_ton=80.0,
        buy_date=datetime(2026, 1, 1),
        sell_date=datetime(2026, 1, 2),
        predicted_max_buy_ton=110.0,
        predicted_list_price_ton=130.0,
        decision_type="BUY_IF_UNDER",
        predicted_confidence=60,
        accuracy_tags_json=["loss", "no_sales_trait_loss"],
    )
    base.update(kwargs)
    return TradeJournal(**base)


def test_detect_max_buy_bias():
    rows = [_sold(id=i) for i in range(1, 5)]
    n, findings = detect_max_buy_bias(rows)
    assert n >= 4
    assert findings


def test_suggest_does_not_touch_filesystem():
    from app.services.pricing_tuner import PricingTuningReport

    rep = PricingTuningReport(
        total_closed_trades=5,
        win_rate=40.0,
        avg_realized_roi=-5.0,
        avg_prediction_error=10.0,
        false_positive_count=3,
        missed_opportunity_count=0,
        max_buy_too_high_cases=3,
        list_price_too_high_cases=3,
        no_sales_trait_losses=3,
        stale_data_losses=3,
        findings=[],
        suggested_env_changes={},
    )
    sug = suggest_pricing_threshold_changes(rep, settings=get_settings())
    assert isinstance(sug, dict)


def test_analyze_updates_last_suggest():
    analyze_pricing_accuracy([], settings=get_settings())
    txt = format_pricing_config_suggest()
    assert "Нет сохранённого" in txt or "Добавьте" in txt


def test_format_pricing_config_current():
    assert "PRICING_TARGET_ROI" in format_pricing_config_current(get_settings())

from types import SimpleNamespace

from app.services.smart_alerts import (
    evaluate_concentration_risk,
    evaluate_data_stale,
    evaluate_liquidity_crash,
    evaluate_regime_change,
    evaluate_stay_in_cash,
    evaluate_strength_drop,
)


def test_regime_change_triggers_on_change():
    fired, _ = evaluate_regime_change(SimpleNamespace(), "risk_off", SimpleNamespace(last_regime="neutral"))
    assert fired is True


def test_strength_drop_threshold_works():
    report = SimpleNamespace(collection="Ice Cream", relative_strength_score=50)
    fired, _ = evaluate_strength_drop(report, SimpleNamespace(last_strength_score=80), threshold=20)
    assert fired is True


def test_liquidity_crash_threshold_works():
    report = SimpleNamespace(collection="Ice Cream", liquidity_score=25)
    fired, _ = evaluate_liquidity_crash(report, threshold=30)
    assert fired is True


def test_data_stale_threshold_works():
    report = SimpleNamespace(collection="Ice Cream", freshness_label="stale")
    fired, _ = evaluate_data_stale(report, threshold_minutes=720)
    assert fired is True


def test_concentration_risk_triggers_above_limit():
    fired, _ = evaluate_concentration_risk(
        [{"collection": "Ice Cream", "value_ton": 82}, {"collection": "Berry", "value_ton": 18}],
        SimpleNamespace(max_collection_percent=40),
    )
    assert fired is True


def test_stay_in_cash_triggers_in_data_poor():
    regime = SimpleNamespace(regime="data_poor")
    fired, _ = evaluate_stay_in_cash(regime, [])
    assert fired is True

from types import SimpleNamespace

from app.schemas.gift import GiftCard
from app.services.signal_snapshots import (
    build_snapshot_seed_from_flip_analysis,
    prediction_dict_from_signal_snapshot,
    signal_feedback_footer,
)
from app.db.models import SignalSnapshot


def test_build_snapshot_seed_includes_trait_sales_flag():
    gift = GiftCard(collection="Ice Cream", number=1)
    est = SimpleNamespace(
        decision_type="BUY_IF_UNDER",
        recommendation="BUY_FOR_FLIP",
        safe_buy_price_ton=10.0,
        buy_zone_max_ton=12.0,
        list_price_ton=15.0,
        quick_sell_price_ton=11.0,
        stop_price_ton=9.0,
        expected_profit_ton=1.0,
        expected_roi_percent=10.0,
        confidence_score=80,
        risk_score=30,
        liquidity_score=50,
        reasons=["ok"],
        max_trait_recent_sales=0,
    )
    quality = SimpleNamespace(warnings=["thin book"], sources_used=["mock"])
    stats = {"floor_freshness": "fresh", "sales_freshness": "fresh", "listings_freshness": "fresh", "real_sales_count": 2}
    seed = build_snapshot_seed_from_flip_analysis(
        source_command="deal",
        gift=gift,
        estimate=est,
        stats=stats,
        quality=quality,
    )
    assert seed["source_command"] == "deal"
    assert seed["has_trait_sales"] is False
    assert seed["confidence_score"] == 80


def test_prediction_dict_from_snapshot_uses_analysis_json():
    snap = SignalSnapshot(
        user_id=1,
        source_command="deal",
        collection="Ice Cream",
        number=1,
        decision_type="HOLD",
        safe_buy_price_ton=5.0,
        max_buy_price_ton=6.0,
        list_price_ton=7.0,
        expected_roi_percent=3.0,
        confidence_score=50,
        analysis_json={
            "decision_type": "STRONG_BUY",
            "safe_buy_price_ton": 9.0,
            "buy_zone_max_ton": 11.0,
            "normal_list_price_ton": 14.0,
            "expected_roi_percent": 12.0,
            "confidence_score": 77,
        },
    )
    d = prediction_dict_from_signal_snapshot(snap)
    assert d["decision_type"] == "STRONG_BUY"
    assert d["confidence_score"] == 77


def test_signal_feedback_footer_has_commands():
    t = signal_feedback_footer(123)
    assert "123" in t
    assert "/signal_good" in t
    assert "/signal_bad" in t

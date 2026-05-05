from datetime import datetime
from pathlib import Path
import tempfile

from app.db.models import TradeJournal
from app.services.calibration_dataset_builder import (
    build_scenarios_from_trade_journal,
    export_calibration_scenarios_json,
    format_dataset_builder_report,
)


def test_build_scenarios_skips_incomplete():
    rows = [
        TradeJournal(
            id=1,
            user_id=1,
            collection="C",
            number=1,
            status="open",
            buy_price_ton=10.0,
        )
    ]
    sc, skipped = build_scenarios_from_trade_journal(rows)
    assert sc == []
    assert skipped


def test_export_writes_files():
    rows = [
        TradeJournal(
            id=2,
            user_id=1,
            collection="C",
            number=1,
            status="sold",
            buy_price_ton=100.0,
            sell_price_ton=110.0,
            predicted_list_price_ton=120.0,
            prediction_json='{"recent_sales":[100,105]}',
        )
    ]
    sc, _ = build_scenarios_from_trade_journal(rows)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        res = export_calibration_scenarios_json(sc, p)
        assert res.written >= 1
        txt = format_dataset_builder_report(res, p, extra_skipped=[(99, "test")])
        assert "Written" in txt or "Written:" in txt

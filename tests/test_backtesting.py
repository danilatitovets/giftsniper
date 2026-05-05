from app.services.backtesting import (
    BacktestPrediction,
    BacktestTrade,
    calculate_pricing_error,
    compare_prediction_to_outcome,
    format_backtest_report,
    run_backtest,
)


def test_compare_prediction_to_outcome():
    t = BacktestTrade(
        collection="C",
        number=1,
        buy_price_ton=100,
        buy_time="t0",
        sell_price_ton=130,
        sell_time="t1",
        outcome="win",
        realized_roi_percent=23.5,
    )
    p = BacktestPrediction(
        decision="BUY_IF_UNDER",
        safe_buy=90,
        max_buy=110,
        list_price=125,
        quick_sell=105,
        stop_loss=85,
        expected_profit=10,
        expected_roi=12,
        confidence=70,
        risk=40,
    )
    assert compare_prediction_to_outcome(p, t) == "win"


def test_calculate_pricing_error():
    assert calculate_pricing_error(100, 100) == 0.0
    assert abs(calculate_pricing_error(110, 100) - 10.0) < 0.01


def test_run_backtest_synthetic():
    trades: list = []
    for i, outcome in enumerate(["win", "loss", "win"]):
        tr = BacktestTrade(
            collection="C",
            number=i,
            buy_price_ton=100,
            buy_time="t",
            sell_price_ton=120 if outcome == "win" else 85,
            outcome=outcome,  # type: ignore[arg-type]
            realized_roi_percent=15.0 if outcome == "win" else -18.0,
        )
        pr = BacktestPrediction(
            decision="BUY_IF_UNDER",
            safe_buy=90,
            max_buy=110,
            list_price=118,
            quick_sell=95,
            stop_loss=80,
            expected_profit=8,
            expected_roi=10,
            confidence=65,
            risk=45,
        )
        trades.append((tr, pr))
    res = run_backtest(trades)
    assert res.total_cases == 3
    txt = format_backtest_report(res)
    assert "Win rate" in txt

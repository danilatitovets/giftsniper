"""Backtest predictions vs outcomes (Stage 31)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.db.models import TradeJournal

Outcome = Literal["win", "loss", "breakeven", "unsold"]


@dataclass
class BacktestTrade:
    collection: str
    number: int | None
    buy_price_ton: float
    buy_time: str
    sell_price_ton: float | None = None
    sell_time: str | None = None
    attributes: list[dict] = field(default_factory=list)
    market_snapshot_before_buy: dict[str, Any] = field(default_factory=dict)
    outcome: Outcome = "unsold"
    realized_profit_ton: float | None = None
    realized_roi_percent: float | None = None


@dataclass
class BacktestPrediction:
    decision: str
    safe_buy: float
    max_buy: float
    list_price: float
    quick_sell: float
    stop_loss: float
    expected_profit: float
    expected_roi: float
    confidence: int
    risk: int


@dataclass
class BacktestResult:
    total_cases: int
    win_rate: float
    avoid_saved_losses: int
    false_positive_buys: int
    missed_good_deals: int
    avg_expected_roi: float
    avg_realized_roi: float
    pricing_error_avg: float
    max_buy_error_avg: float
    list_price_error_avg: float
    recommendations: list[str] = field(default_factory=list)


def compare_prediction_to_outcome(pred: BacktestPrediction, trade: BacktestTrade) -> Outcome:
    if trade.outcome != "unsold":
        return trade.outcome
    if trade.sell_price_ton is None:
        return "unsold"
    net = trade.sell_price_ton * 0.95
    pnl = net - trade.buy_price_ton
    if pnl > trade.buy_price_ton * 0.03:
        return "win"
    if pnl < -trade.buy_price_ton * 0.03:
        return "loss"
    return "breakeven"


def calculate_pricing_error(predicted_list: float, actual_sell: float | None) -> float:
    if not actual_sell or actual_sell <= 0:
        return 0.0
    return abs(predicted_list - actual_sell) / actual_sell * 100.0


def run_backtest(trades: list[tuple[BacktestTrade, BacktestPrediction]]) -> BacktestResult:
    wins = losses = 0
    total = len(trades)
    fe = mbe = lle = 0.0
    n_fe = 0
    exp_rois: list[float] = []
    real_rois: list[float] = []
    false_pos = missed = avoid_saved = 0

    for trade, pred in trades:
        exp_rois.append(pred.expected_roi)
        oc = trade.outcome
        if oc == "win":
            wins += 1
        elif oc == "loss":
            losses += 1
        if trade.realized_roi_percent is not None:
            real_rois.append(trade.realized_roi_percent)
        if trade.sell_price_ton:
            fe += calculate_pricing_error(pred.list_price, trade.sell_price_ton)
            mbe += abs(pred.max_buy - trade.buy_price_ton) / max(trade.buy_price_ton, 1e-6) * 100
            lle += abs(pred.list_price - trade.sell_price_ton) / max(trade.sell_price_ton, 1e-6) * 100
            n_fe += 1
        if pred.decision in {"STRONG_BUY", "BUY_IF_UNDER"} and oc == "loss":
            false_pos += 1
        if pred.decision == "AVOID" and oc == "win":
            missed += 1
        if pred.decision == "AVOID" and oc == "loss":
            avoid_saved += 1

    win_rate = (wins / total * 100.0) if total else 0.0
    recs: list[str] = []
    if false_pos > total * 0.25:
        recs.append("Рассмотреть повышение min ROI или ужесточение STRONG_BUY.")
    if missed > total * 0.2:
        recs.append("Часто пропускаете выигрышные — проверьте max_buy не слишком жёсткий.")
    if losses > wins and total >= 3:
        recs.append("Уменьшить размер speculative buys; усилить фильтр no-sales traits.")

    return BacktestResult(
        total_cases=total,
        win_rate=round(win_rate, 2),
        avoid_saved_losses=avoid_saved,
        false_positive_buys=false_pos,
        missed_good_deals=missed,
        avg_expected_roi=round(sum(exp_rois) / len(exp_rois), 2) if exp_rois else 0.0,
        avg_realized_roi=round(sum(real_rois) / len(real_rois), 2) if real_rois else 0.0,
        pricing_error_avg=round(fe / n_fe, 2) if n_fe else 0.0,
        max_buy_error_avg=round(mbe / n_fe, 2) if n_fe else 0.0,
        list_price_error_avg=round(lle / n_fe, 2) if n_fe else 0.0,
        recommendations=recs,
    )


def format_backtest_report(res: BacktestResult) -> str:
    return (
        f"Backtest (n={res.total_cases})\n"
        f"Win rate: {res.win_rate}%\n"
        f"Avoid saved losses (heuristic): {res.avoid_saved_losses}\n"
        f"False positive buys: {res.false_positive_buys}\n"
        f"Missed good deals: {res.missed_good_deals}\n"
        f"Avg expected ROI: {res.avg_expected_roi}% · Avg realized: {res.avg_realized_roi}%\n"
        f"Avg pricing error %: {res.pricing_error_avg}\n"
        f"Avg max_buy error %: {res.max_buy_error_avg}\n"
        f"Avg list vs sell error %: {res.list_price_error_avg}\n"
        + ("Tips:\n- " + "\n- ".join(res.recommendations) if res.recommendations else "")
    )


def journal_rows_to_backtest_pairs(rows: list[TradeJournal]) -> list[tuple[BacktestTrade, BacktestPrediction]]:
    """Build backtest pairs from closed trade_journal rows (stored predictions)."""
    out: list[tuple[BacktestTrade, BacktestPrediction]] = []
    for r in rows:
        if r.status != "sold" or not r.buy_price_ton or not r.sell_price_ton:
            continue
        buy = float(r.buy_price_ton)
        sp = float(r.sell_price_ton)
        net = sp * 0.95
        pnl = net - buy
        if pnl > buy * 0.03:
            oc: Outcome = "win"
        elif pnl < -buy * 0.03:
            oc = "loss"
        else:
            oc = "breakeven"
        roi_real = r.realized_roi_percent if r.realized_roi_percent is not None else (pnl / buy * 100.0 if buy else 0.0)
        safe = float(r.predicted_safe_buy_ton) if r.predicted_safe_buy_ton else buy * 0.9
        mx = float(r.predicted_max_buy_ton) if r.predicted_max_buy_ton else buy * 1.1
        lst = float(r.predicted_list_price_ton) if r.predicted_list_price_ton else sp
        qs = safe * 0.95
        st = safe * 0.88
        exp_roi = float(r.predicted_roi_percent) if r.predicted_roi_percent is not None else 0.0
        exp_p = lst * 0.95 - buy
        if r.prediction_json:
            try:
                pj = json.loads(r.prediction_json)
                if isinstance(pj, dict) and pj.get("precision_plan_json"):
                    raw_plan = pj["precision_plan_json"]
                    plan = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
                    if isinstance(plan, dict):
                        qs = float(plan.get("quick_sell_price_ton") or qs)
                        st = float(plan.get("stop_loss_price_ton") or st)
                        lst = float(plan.get("normal_list_price_ton") or lst)
                        mx = float(plan.get("max_buy_price_ton") or mx)
                        safe = float(plan.get("safe_buy_price_ton") or safe)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        tr = BacktestTrade(
            collection=r.collection,
            number=r.number,
            buy_price_ton=buy,
            buy_time=str(r.buy_date or r.created_at or ""),
            sell_price_ton=sp,
            sell_time=str(r.sell_date or ""),
            attributes=r.attributes_json if isinstance(r.attributes_json, list) else [],
            outcome=oc,
            realized_profit_ton=pnl,
            realized_roi_percent=float(roi_real) if roi_real is not None else None,
        )
        pr = BacktestPrediction(
            decision=str(r.decision_type or "UNKNOWN"),
            safe_buy=safe,
            max_buy=mx,
            list_price=lst,
            quick_sell=qs,
            stop_loss=st,
            expected_profit=exp_p,
            expected_roi=exp_roi,
            confidence=int(r.predicted_confidence or 50),
            risk=50,
        )
        out.append((tr, pr))
    return out

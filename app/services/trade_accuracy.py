"""Compute realized metrics and accuracy tags when a trade closes (Stage 32)."""

from __future__ import annotations

import json
from datetime import datetime

from app.db.models import TradeJournal


def _fee_net(price: float, fee_pct: float) -> float:
    return price * (1 - fee_pct / 100.0)


def hold_time_hours_row(row: TradeJournal, sell_date: datetime | None) -> float | None:
    if sell_date is None:
        return None
    start = row.buy_date or row.created_at
    if start is None:
        return None
    try:
        delta = sell_date - start
        return max(0.0, delta.total_seconds() / 3600.0)
    except (TypeError, ValueError):
        return None


def compute_sold_trade_accuracy(
    row: TradeJournal,
    sell_price_ton: float,
    *,
    fee_percent: float = 5.0,
    sell_date: datetime | None = None,
) -> dict:
    """Fields to merge onto TradeJournal after sell."""
    buy = float(row.buy_price_ton or 0.0)
    net = _fee_net(float(sell_price_ton), fee_percent)
    pnl = net - buy
    roi = (pnl / buy * 100.0) if buy > 0 else 0.0
    sd = sell_date or datetime.utcnow()
    hold = hold_time_hours_row(row, sd)

    tags: list[str] = []
    if buy > 0:
        if pnl > buy * 0.02:
            tags.append("win")
        elif pnl < -buy * 0.02:
            tags.append("loss")
        else:
            tags.append("breakeven")

    pmax = float(row.predicted_max_buy_ton) if row.predicted_max_buy_ton else None
    plist = float(row.predicted_list_price_ton) if row.predicted_list_price_ton else None
    pconf = int(row.predicted_confidence) if row.predicted_confidence is not None else None

    if "loss" in tags and pmax is not None and buy <= pmax * 1.03:
        tags.append("max_buy_too_high")
    if plist and sell_price_ton > 0 and sell_price_ton < plist * 0.82:
        tags.append("list_price_too_high")
    if "loss" in tags and (row.decision_type or "") == "SPECULATIVE_BUY":
        tags.append("no_sales_trait_loss")
    snap = {}
    if row.prediction_json:
        try:
            snap = json.loads(row.prediction_json)
        except json.JSONDecodeError:
            snap = {}
    reasons_blob = " ".join(str(x).lower() for x in (snap.get("reasons") or []) if isinstance(snap, dict))
    if "loss" in tags and ("stale" in reasons_blob or "устарел" in reasons_blob):
        tags.append("stale_data_loss")
    if "loss" in tags and pconf is not None and pconf < 55:
        tags.append("low_confidence_loss")
    if "win" in tags and plist and abs(plist - sell_price_ton) / max(sell_price_ton, 1e-6) * 100 < 18:
        tags.append("good_prediction")
    if "win" in tags and plist and sell_price_ton < plist * 0.88:
        tags.append("missed_upside")

    pred_err: dict = {
        "max_buy_abs_pct_vs_buy": abs(pmax - buy) / buy * 100 if pmax and buy > 0 else None,
        "list_abs_pct_vs_sell": abs(plist - sell_price_ton) / sell_price_ton * 100 if plist and sell_price_ton > 0 else None,
    }

    return {
        "realized_profit_ton": round(pnl, 4),
        "realized_roi_percent": round(roi, 2),
        "hold_time_hours": round(hold, 2) if hold is not None else None,
        "accuracy_tags_json": tags,
        "prediction_error_json": json.dumps({k: v for k, v in pred_err.items() if v is not None}),
    }

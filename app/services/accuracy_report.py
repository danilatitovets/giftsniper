"""User / admin accuracy stats from trade_journal."""

from __future__ import annotations

import json
from statistics import mean

from app.db.models import TradeJournal


def _fee_net(price: float, fee_pct: float = 5.0) -> float:
    return price * (1 - fee_pct / 100.0)


def build_user_accuracy_report(
    rows: list[TradeJournal], *, fee_percent: float = 5.0, include_segments: bool = True
) -> str:
    closed = [r for r in rows if r.status == "sold" and r.buy_price_ton and r.sell_price_ton]
    if not closed:
        return "Accuracy: нет закрытых сделок. Добавляйте через /trade_add и закрывайте /trade_sell."
    wins = losses = 0
    pnl_total = 0.0
    mb_err: list[float] = []
    list_err: list[float] = []
    by_dec: dict[str, list[bool]] = {}

    for r in closed:
        buy = float(r.buy_price_ton)
        net = _fee_net(float(r.sell_price_ton), fee_percent)
        pnl = net - buy
        pnl_total += pnl
        if pnl > buy * 0.02:
            wins += 1
        elif pnl < -buy * 0.02:
            losses += 1
        if r.predicted_max_buy_ton:
            mb_err.append(abs(float(r.predicted_max_buy_ton) - buy) / buy * 100)
        if r.predicted_list_price_ton:
            list_err.append(abs(float(r.predicted_list_price_ton) - float(r.sell_price_ton)) / float(r.sell_price_ton) * 100)
        key = r.decision_type or "unknown"
        by_dec.setdefault(key, []).append(pnl > 0)

    n = len(closed)
    tips: list[str] = []
    if losses > wins:
        tips.append("Рассмотреть увеличение min ROI и уменьшение доли speculative buys.")
        tips.append("Не брать редкие traits без подтверждающих продаж как основной вход.")
    if mean(mb_err) > 18 if mb_err else False:
        tips.append("Средняя ошибка max_buy высокая — калибруйте входы консервативнее.")
    if mean(list_err) > 25 if list_err else False:
        tips.append("List price часто далёк от факта — смотрите ликвидность и spread.")

    dec_lines = []
    for k, vals in sorted(by_dec.items(), key=lambda x: -len(x[1])):
        wr = sum(1 for v in vals if v) / len(vals) * 100
        dec_lines.append(f"- {k}: win% ~{wr:.0f} (n={len(vals)})")

    seg = ""
    if include_segments and n >= 3:
        seg = "\n\n" + build_accuracy_segments_report(rows, fee_percent=fee_percent)

    return (
        f"📈 Accuracy report (закрытых: {n})\n"
        f"Win / loss (грубо ±2%): {wins} / {losses}\n"
        f"Суммарный realized PnL (после комиссии {fee_percent}%): {pnl_total:+.2f} TON\n"
        f"Средняя ошибка max_buy %: {mean(mb_err) if mb_err else 0:.1f}\n"
        f"Средняя ошибка list vs sell %: {mean(list_err) if list_err else 0:.1f}\n"
        f"По решениям:\n" + "\n".join(dec_lines) + "\n"
        + ("Советы:\n- " + "\n- ".join(tips) if tips else "")
        + seg
        + "\n\nОценки сценарные; прошлое не гарантирует будущее."
    )


def _conf_bucket(c: int | None) -> str:
    if c is None:
        return "unknown"
    if c <= 40:
        return "0-40"
    if c <= 60:
        return "41-60"
    if c <= 75:
        return "61-75"
    return "76-100"


def build_accuracy_segments_report(rows: list[TradeJournal], *, fee_percent: float = 5.0) -> str:
    closed = [r for r in rows if r.status == "sold" and r.buy_price_ton and r.sell_price_ton]
    if not closed:
        return "Сегменты: нет закрытых сделок."

    by_coll: dict[str, list[bool]] = {}
    by_dec: dict[str, list[bool]] = {}
    by_bucket: dict[str, list[bool]] = {}
    by_trait: dict[str, list[bool]] = {}
    by_hold: dict[str, list[bool]] = {}
    by_src: dict[str, list[bool]] = {}

    for r in closed:
        buy = float(r.buy_price_ton)
        net = _fee_net(float(r.sell_price_ton), fee_percent)
        win = (net - buy) > buy * 0.02
        key_c = r.collection or "?"
        by_coll.setdefault(key_c, []).append(win)
        by_dec.setdefault(r.decision_type or "unknown", []).append(win)
        by_bucket.setdefault(_conf_bucket(r.predicted_confidence), []).append(win)
        has_trait = bool(r.attributes_json and isinstance(r.attributes_json, list) and len(r.attributes_json) > 0)
        by_trait.setdefault("with_traits" if has_trait else "no_traits", []).append(win)
        h = r.hold_time_hours
        if h is None:
            hk = "unknown_hold"
        elif h < 24:
            hk = "hold_<24h"
        elif h < 168:
            hk = "hold_1-7d"
        else:
            hk = "hold_7d+"
        by_hold.setdefault(hk, []).append(win)
        src = "unknown"
        if r.prediction_json:
            try:
                pj = json.loads(r.prediction_json)
                if isinstance(pj, dict):
                    if pj.get("precision_plan_json"):
                        src = "has_plan"
                    if any("mock" in str(pj.get(k, "")).lower() for k in pj):
                        src = "mock_hint"
            except json.JSONDecodeError:
                pass
        by_src.setdefault(src, []).append(win)

    def _fmt_groups(title: str, d: dict[str, list[bool]]) -> str:
        lines = [title]
        for k, vals in sorted(d.items(), key=lambda x: -len(x[1])):
            if not vals:
                continue
            wr = sum(1 for v in vals if v) / len(vals) * 100
            lines.append(f"  · {k}: win~{wr:.0f}% (n={len(vals)})")
        return "\n".join(lines)

    thin = [c for c, v in by_coll.items() if len(v) < 3]
    lines = [
        "📊 Accuracy по сегментам",
        _fmt_groups("По коллекции:", by_coll),
        "",
        _fmt_groups("По decision_type:", by_dec),
        "",
        _fmt_groups("По confidence:", by_bucket),
        "",
        _fmt_groups("По traits:", by_trait),
        "",
        _fmt_groups("По hold time:", by_hold),
        "",
        _fmt_groups("По снимку прогноза:", by_src),
    ]
    if thin:
        lines.append("\nМало данных (<3 сделок): " + ", ".join(thin[:15]))
    lines.append("\nЭто описательная статистика, не совет по инвестициям.")
    return "\n".join(lines)


def build_trade_stats_extended(rows: list[TradeJournal], *, fee_percent: float = 5.0) -> str:
    open_n = sum(1 for r in rows if r.status == "open")
    watch_n = sum(1 for r in rows if r.status == "watching")
    sold = [r for r in rows if r.status == "sold" and r.buy_price_ton and r.sell_price_ton]
    sold_n = len(sold)
    lines = [
        "📒 Trade stats",
        f"Открыто: {open_n + watch_n} (open/watch) · Закрыто: {sold_n}",
    ]
    if not sold:
        lines.append("Нет закрытых для PnL/ROI.")
        return "\n".join(lines)
    pnls: list[float] = []
    rois: list[float] = []
    holds: list[float] = []
    pred_ok = 0
    for r in sold:
        buy = float(r.buy_price_ton)
        net = _fee_net(float(r.sell_price_ton), fee_percent)
        pnl = r.realized_profit_ton if r.realized_profit_ton is not None else (net - buy)
        roi = r.realized_roi_percent if r.realized_roi_percent is not None else ((pnl / buy * 100.0) if buy else 0.0)
        pnls.append(float(pnl))
        rois.append(float(roi))
        if r.hold_time_hours is not None:
            holds.append(float(r.hold_time_hours))
        if r.accuracy_tags_json and "good_prediction" in r.accuracy_tags_json:
            pred_ok += 1
    best_i = max(range(len(pnls)), key=lambda i: pnls[i])
    worst_i = min(range(len(pnls)), key=lambda i: pnls[i])
    b, w = sold[best_i], sold[worst_i]
    lines.append(f"Суммарный realized PnL: {sum(pnls):+.2f} TON")
    lines.append(f"Avg ROI %: {mean(rois):.1f}")
    if holds:
        lines.append(f"Avg hold: {mean(holds) / 24:.1f} дн (≈ часов {mean(holds):.0f})")
    lines.append(f"Best: #{b.id} {b.collection} PnL ~ {pnls[best_i]:+.2f}")
    lines.append(f"Worst: #{w.id} {w.collection} PnL ~ {pnls[worst_i]:+.2f}")
    if sold_n:
        lines.append(f"Доля «good_prediction» тега: {pred_ok}/{sold_n}")
    lines.append("\n/pro accuracy_report — детальнее; /pricing_tuning_report — калибровка.")
    return "\n".join(lines)


def build_admin_accuracy_report(rows: list[TradeJournal]) -> str:
    if not rows:
        return "Admin accuracy: нет записей trade_journal."
    users_all = len({r.user_id for r in rows})
    closed_ok = [r for r in rows if r.status == "sold" and r.buy_price_ton and r.sell_price_ton]
    users_closed = len({r.user_id for r in closed_ok})
    return (
        build_user_accuracy_report(rows)
        + f"\n\nAdmin: пользователей с записями в выборке: {users_all}, с закрытыми сделками: {users_closed}."
    )

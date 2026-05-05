"""Heuristic pricing calibration suggestions from trade_journal (Stage 32). Not auto-applied."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from statistics import mean

from app.config import Settings, get_settings
from app.db.models import TradeJournal

LAST_TUNING_REPORT: PricingTuningReport | None = None
LAST_SUGGESTED_ENV: dict[str, str] = {}


def _fee_net(price: float, fee_pct: float = 5.0) -> float:
    return price * (1 - fee_pct / 100.0)


@dataclass
class PricingTuningFinding:
    category: str
    severity: str
    metric_name: str
    current_value: str
    suggested_value: str | None
    evidence: str
    affected_cases_count: int
    explanation: str


@dataclass
class PricingTuningReport:
    total_closed_trades: int
    win_rate: float
    avg_realized_roi: float
    avg_prediction_error: float
    false_positive_count: int
    missed_opportunity_count: int
    max_buy_too_high_cases: int
    list_price_too_high_cases: int
    no_sales_trait_losses: int
    stale_data_losses: int
    findings: list[PricingTuningFinding] = field(default_factory=list)
    suggested_env_changes: dict[str, str] = field(default_factory=dict)


def _closed(rows: list[TradeJournal]) -> list[TradeJournal]:
    return [r for r in rows if r.status == "sold" and r.buy_price_ton and r.sell_price_ton]


def detect_max_buy_bias(closed: list[TradeJournal]) -> tuple[int, list[PricingTuningFinding]]:
    """Losses where buy was within predicted max buy — ceiling may be too optimistic."""
    n = 0
    for r in closed:
        buy = float(r.buy_price_ton)
        net = _fee_net(float(r.sell_price_ton))
        pnl = net - buy
        pmax = float(r.predicted_max_buy_ton) if r.predicted_max_buy_ton else None
        if pmax and buy <= pmax * 1.03 and pnl < -buy * 0.02:
            n += 1
    findings: list[PricingTuningFinding] = []
    if n >= 2 and len(closed) >= 4:
        findings.append(
            PricingTuningFinding(
                category="max_buy",
                severity="medium",
                metric_name="PRICING_TARGET_ROI_NORMAL",
                current_value="(see .env)",
                suggested_value="raise a few points or tighten max_buy via higher effective ROI",
                evidence=f"{n} closed losses with buy ≤ predicted max_buy",
                affected_cases_count=n,
                explanation="Сделки убыточны, хотя вход был внутри «разрешённого» max buy — целевой ROI может быть занижен относительно риска.",
            )
        )
    return n, findings


def detect_list_price_bias(closed: list[TradeJournal]) -> tuple[int, list[PricingTuningFinding]]:
    n = 0
    for r in closed:
        plist = float(r.predicted_list_price_ton) if r.predicted_list_price_ton else None
        sp = float(r.sell_price_ton)
        if plist and sp > 0 and sp < plist * 0.78:
            n += 1
    findings: list[PricingTuningFinding] = []
    if n >= 2 and len(closed) >= 4:
        findings.append(
            PricingTuningFinding(
                category="list_price",
                severity="medium",
                metric_name="list_targets / high_list",
                current_value="heuristic multipliers in pricing.calculate_list_targets",
                suggested_value="slightly lower high_list multiplier or conservative normal list",
                evidence=f"{n} sells materially below predicted list",
                affected_cases_count=n,
                explanation="Фактические продажи заметно ниже прогнозного list — ожидания выхода завышены.",
            )
        )
    return n, findings


def detect_rare_no_sales_failures(closed: list[TradeJournal]) -> tuple[int, list[PricingTuningFinding]]:
    n = sum(1 for r in closed if "no_sales_trait_loss" in (r.accuracy_tags_json or []))
    findings: list[PricingTuningFinding] = []
    if n >= 2:
        findings.append(
            PricingTuningFinding(
                category="trait_liquidity",
                severity="high",
                metric_name="PRICING_RARE_NO_SALES_MAX_TIER",
                current_value="B_TIER",
                suggested_value="C_TIER or stricter SPECULATIVE caps",
                evidence=f"{n} tagged no_sales_trait_loss",
                affected_cases_count=n,
                explanation="Убытки на спекулятивных trait без продаж — ужесточить tier или избегать таких входов.",
            )
        )
    return n, findings


def detect_stale_data_failures(closed: list[TradeJournal]) -> tuple[int, list[PricingTuningFinding]]:
    n = sum(1 for r in closed if "stale_data_loss" in (r.accuracy_tags_json or []))
    findings: list[PricingTuningFinding] = []
    if n >= 2:
        findings.append(
            PricingTuningFinding(
                category="data_freshness",
                severity="medium",
                metric_name="PRICING_STALE_DATA_DISCOUNT",
                current_value="(see .env)",
                suggested_value="0.88–0.90 (stronger discount)",
                evidence=f"{n} stale_data_loss tags",
                affected_cases_count=n,
                explanation="Потери связаны со stale данными — сильнее дисконтировать safe buy при stale.",
            )
        )
    return n, findings


def suggest_pricing_threshold_changes(
    report: PricingTuningReport,
    settings: Settings | None = None,
) -> dict[str, str]:
    s = settings or get_settings()
    sug: dict[str, str] = {}
    if report.max_buy_too_high_cases >= 2:
        cur = s.pricing_target_roi_normal
        sug["PRICING_TARGET_ROI_NORMAL"] = str(round(cur + 2.0, 1))
    if report.list_price_too_high_cases >= 2:
        sug["PRICING_LOW_CONFIDENCE_DISCOUNT"] = str(round(min(0.95, s.pricing_low_confidence_discount + 0.02), 2))
    if report.no_sales_trait_losses >= 2:
        sug["PRICING_RARE_NO_SALES_MAX_TIER"] = "C_TIER"
    if report.stale_data_losses >= 2:
        sug["PRICING_STALE_DATA_DISCOUNT"] = str(round(max(0.85, s.pricing_stale_data_discount - 0.03), 2))
    return sug


def analyze_pricing_accuracy(rows: list[TradeJournal], *, settings: Settings | None = None) -> PricingTuningReport:
    global LAST_TUNING_REPORT, LAST_SUGGESTED_ENV
    closed = _closed(rows)
    if not closed:
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
        LAST_TUNING_REPORT = rep
        LAST_SUGGESTED_ENV = {}
        return rep

    wins = losses = 0
    rois: list[float] = []
    pred_errs: list[float] = []
    false_pos = missed = 0

    for r in closed:
        buy = float(r.buy_price_ton)
        net = _fee_net(float(r.sell_price_ton))
        pnl = net - buy
        roi = (pnl / buy * 100.0) if buy > 0 else 0.0
        rois.append(roi)
        if pnl > buy * 0.02:
            wins += 1
        elif pnl < -buy * 0.02:
            losses += 1
        if r.prediction_error_json:
            try:
                d = json.loads(r.prediction_error_json)
                for v in d.values():
                    if isinstance(v, (int, float)):
                        pred_errs.append(float(v))
            except json.JSONDecodeError:
                pass
        dt = r.decision_type or ""
        if dt in ("STRONG_BUY", "BUY_IF_UNDER") and pnl < -buy * 0.02:
            false_pos += 1
        if dt == "AVOID" and pnl > buy * 0.05:
            missed += 1

    mb_n, mb_find = detect_max_buy_bias(closed)
    ls_n, ls_find = detect_list_price_bias(closed)
    ns_n, ns_find = detect_rare_no_sales_failures(closed)
    st_n, st_find = detect_stale_data_failures(closed)

    findings = mb_find + ls_find + ns_find + st_find
    rep = PricingTuningReport(
        total_closed_trades=len(closed),
        win_rate=round(wins / len(closed) * 100.0, 2),
        avg_realized_roi=round(mean(rois), 2) if rois else 0.0,
        avg_prediction_error=round(mean(pred_errs), 2) if pred_errs else 0.0,
        false_positive_count=false_pos,
        missed_opportunity_count=missed,
        max_buy_too_high_cases=mb_n,
        list_price_too_high_cases=ls_n,
        no_sales_trait_losses=ns_n,
        stale_data_losses=st_n,
        findings=findings,
        suggested_env_changes={},
    )
    rep.suggested_env_changes = suggest_pricing_threshold_changes(rep, settings=settings)
    LAST_TUNING_REPORT = rep
    LAST_SUGGESTED_ENV = dict(rep.suggested_env_changes)
    return rep


def format_pricing_tuning_report(rep: PricingTuningReport) -> str:
    lines = [
        "🛠 Pricing tuning (рекомендации, не авто-применение)",
        f"Закрытых сделок: {rep.total_closed_trades}",
        f"Win rate (грубо): {rep.win_rate}%",
        f"Avg realized ROI %: {rep.avg_realized_roi}",
        f"Avg prediction error (составной) %: {rep.avg_prediction_error}",
        f"False-positive buys (эвристика): {rep.false_positive_count}",
        f"Missed upside (AVOID но прибыльно): {rep.missed_opportunity_count}",
        f"max_buy too high cases: {rep.max_buy_too_high_cases}",
        f"list too high vs sell: {rep.list_price_too_high_cases}",
        f"no-sales trait losses: {rep.no_sales_trait_losses}",
        f"stale data losses: {rep.stale_data_losses}",
    ]
    if rep.findings:
        lines.append("\nFindings:")
        for f in rep.findings[:12]:
            lines.append(f"- [{f.severity}] {f.category}: {f.explanation} (n={f.affected_cases_count})")
    if rep.suggested_env_changes:
        lines.append("\nПредлагаемые строки для .env (вручную):")
        for k, v in rep.suggested_env_changes.items():
            lines.append(f"  {k}={v}")
    else:
        lines.append("\nНет устойчивых предложений по порогам — нужно больше закрытых сделок (50+ лучше).")
    lines.append("\nАвтоматически .env не меняется. Подтверждает только owner/admin.")
    return "\n".join(lines)


def format_pricing_config_current(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    keys = [
        "pricing_target_roi_conservative",
        "pricing_target_roi_normal",
        "pricing_target_roi_aggressive",
        "pricing_no_sales_safe_buy_discount",
        "pricing_low_confidence_discount",
        "pricing_stale_data_discount",
        "pricing_rare_no_sales_max_tier",
        "pricing_strong_buy_min_confidence",
        "pricing_strong_buy_min_liquidity",
        "pricing_strong_buy_require_recent_sales",
    ]
    lines = ["Текущие PRICING_* (из settings):"]
    for k in keys:
        lines.append(f"  {k.upper()}={getattr(s, k)}")
    return "\n".join(lines)


def format_pricing_config_suggest() -> str:
    if not LAST_SUGGESTED_ENV:
        return "Нет сохранённого tuning — сначала /pricing_tuning_report."
    lines = ["Добавьте или измените в .env (вручную):"]
    for k, v in LAST_SUGGESTED_ENV.items():
        lines.append(f"  {k}={v}")
    return "\n".join(lines)

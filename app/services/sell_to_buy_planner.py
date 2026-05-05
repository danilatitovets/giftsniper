"""Suggest sells and replacement buys using capital efficiency (Stage 34)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas.gift import GiftCard
from app.services.analyzer import AnalyzerService
from app.services.capital_multiplier import (
    FlipCandidate,
    calculate_capital_efficiency,
    calculate_probability_weighted_profit,
    estimate_sale_probability,
    flip_candidate_from_opportunity_row,
    gather_ranked_with_market_regime,
)
from app.sources.factory import create_market_source


class SuggestedSell(BaseModel):
    gift_id: int
    collection: str
    number: int
    current_value_ton: float
    quick_sell_price_ton: float
    normal_list_price_ton: float
    high_list_price_ton: float
    stop_price_ton: float
    expected_net_ton: float
    reason: str
    urgency: str  # hold | optional_sell | sell_to_redeploy | quick_sell


class ReplacementBuy(BaseModel):
    candidate: FlipCandidate
    reason: str


class SellToBuyPlan(BaseModel):
    current_portfolio_value_ton: float = 0.0
    expected_liquid_capital_ton: float = 0.0
    suggested_sells: list[SuggestedSell] = Field(default_factory=list)
    replacement_buys: list[ReplacementBuy] = Field(default_factory=list)
    expected_improvement_ton: float = 0.0
    expected_improvement_roi_percent: float = 0.0
    risk_change_label: str = ""
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _holding_efficiency(estimate: Any, *, buy_price: float | None) -> float:
    from app.schemas.analysis import FlipAnalysisResult

    if not isinstance(estimate, FlipAnalysisResult):
        return 0.0
    fc = FlipCandidate(
        collection="",
        buy_price_ton=float(buy_price or estimate.fair_price_ton or 0),
        list_price_ton=float(getattr(estimate, "normal_list_price_ton", None) or estimate.list_price_ton or 0),
        expected_profit_ton=float(estimate.expected_profit_ton or 0),
        expected_roi_percent=float(estimate.expected_roi_percent or 0),
        risk_score=int(estimate.risk_score or 50),
        confidence_score=int(estimate.confidence_score or 50),
        liquidity_score=int(estimate.liquidity_score or 50),
        decision_type=str(getattr(estimate, "decision_type", "") or ""),
        has_recent_sales=True,
        has_trait_sales=bool(getattr(estimate, "max_trait_recent_sales", None)),
        warnings=[],
    )
    ctx = {"decision_type": fc.decision_type, "market_regime": "neutral", "source_quality": "real", "freshness_label": "fresh"}
    sp = estimate_sale_probability(fc, ctx)
    fc = fc.model_copy(update={"sale_probability_percent": sp})
    fc = fc.model_copy(update={"probability_weighted_profit_ton": calculate_probability_weighted_profit(fc)})
    return calculate_capital_efficiency(fc)


def _urgency_from_estimate(estimate: Any) -> str:
    rec = getattr(estimate, "recommendation", "") or ""
    dec = getattr(estimate, "decision_type", None)
    if rec == "SELL_FAST" or dec == "QUICK_SELL":
        return "quick_sell"
    if rec in {"LIST_HIGHER"} or dec in {"LIST_NOW", "LIST_HIGH"}:
        return "sell_to_redeploy"
    if rec == "HOLD" and int(estimate.confidence_score or 0) < 55:
        return "optional_sell"
    return "hold"


async def build_sell_to_buy_plan(
    user: Any,
    settings: Settings,
    *,
    gifts: list[Any],
    universe_collections: list[str],
    target_budget_ton: float | None = None,
) -> SellToBuyPlan:
    st = settings or get_settings()
    source = create_market_source(st, user_id=user.id)
    analyzer = AnalyzerService(source)
    if not gifts:
        return SellToBuyPlan(warnings=["Портфель пуст — нечего сопоставлять с рынком."])

    suggested: list[SuggestedSell] = []
    total_fair = 0.0
    liquid_cap = 0.0
    analyzed: list[tuple[Any, Any]] = []

    portfolio_rows = [{"collection": g.collection, "value_ton": float(g.purchase_price_ton or 0.0)} for g in gifts]

    for g in gifts:
        est = await analyzer.analyze_gift(
            GiftCard(collection=g.collection, number=g.number),
            risk_mode=user.risk_mode,
            buy_price_ton=g.purchase_price_ton,
            owns_asset=True,
        )
        analyzed.append((g, est))
        fair = float(est.fair_price_ton or 0)
        total_fair += fair
        net_quick = float(est.quick_sell_price_ton or 0) * (1 - st.default_marketplace_fee_percent / 100.0)
        urgency = _urgency_from_estimate(est)
        suggested.append(
            SuggestedSell(
                gift_id=g.id,
                collection=g.collection,
                number=g.number,
                current_value_ton=round(fair, 2),
                quick_sell_price_ton=float(est.quick_sell_price_ton or 0),
                normal_list_price_ton=float(getattr(est, "normal_list_price_ton", None) or est.list_price_ton or 0),
                high_list_price_ton=float(getattr(est, "high_list_price_ton", None) or est.optimistic_price_ton or 0),
                stop_price_ton=float(est.stop_price_ton or 0),
                expected_net_ton=round(net_quick, 2),
                reason="; ".join((est.reasons or [])[:2]) if est.reasons else "Оценка по текущим данным",
                urgency=urgency,
            )
        )
        if urgency in {"quick_sell", "sell_to_redeploy", "optional_sell"}:
            liquid_cap += net_quick

    _ = target_budget_ton
    ranked, regime_name = await gather_ranked_with_market_regime(
        user, universe_collections, st, portfolio_rows
    )

    replacements: list[ReplacementBuy] = []
    reasons: list[str] = []
    warnings: list[str] = []

    for g, est in analyzed:
        hold_eff = _holding_efficiency(est, buy_price=g.purchase_price_ton)
        urg = _urgency_from_estimate(est)
        if urg == "hold" and int(est.confidence_score or 0) >= 62:
            continue
        if urg == "hold":
            continue

        best_delta = -1.0
        best_cand: FlipCandidate | None = None
        for row in ranked[:40]:
            fc = flip_candidate_from_opportunity_row(row, market_regime=regime_name, settings=st)
            if fc.collection == g.collection and fc.number == g.number:
                continue
            if fc.capital_efficiency_score > hold_eff + 4.0 and fc.expected_profit_ton and fc.expected_profit_ton > 0:
                delta = fc.capital_efficiency_score - hold_eff
                if delta > best_delta:
                    best_delta = delta
                    best_cand = fc

        if best_cand is None:
            reasons.append(f"{g.collection} #{g.number}: удержание или кэш выглядят не хуже замен (оценка).")
            continue
        if best_delta < 6.0:
            reasons.append(f"{g.collection} #{g.number}: улучшение слабое — разумнее hold/кэш.")
            continue

        replacements.append(
            ReplacementBuy(
                candidate=best_cand,
                reason=(
                    f"Capital efficiency ~{best_cand.capital_efficiency_score:.0f} vs ~{hold_eff:.0f} у текущей позиции "
                    "(оценка, не гарантия сделки)."
                ),
            )
        )

    if len(replacements) > 3:
        replacements = sorted(replacements, key=lambda x: x.candidate.capital_efficiency_score, reverse=True)[:3]

    exp_imp = sum(float(r.candidate.probability_weighted_profit_ton or 0) for r in replacements)
    base_cap = float(target_budget_ton or liquid_cap or 1.0)
    roi_imp = (exp_imp / base_cap * 100.0) if base_cap > 0 else 0.0
    risk_change = "similar"
    if replacements:
        avg_r = sum(r.candidate.risk_score for r in replacements) / len(replacements)
        risk_change = "higher" if avg_r >= 62 else "lower"

    if not replacements:
        warnings.append("Подходящих замен с явным улучшением по модели не найдено — не обязательно продавать.")

    return SellToBuyPlan(
        current_portfolio_value_ton=round(total_fair, 2),
        expected_liquid_capital_ton=round(liquid_cap, 2),
        suggested_sells=suggested,
        replacement_buys=replacements,
        expected_improvement_ton=round(exp_imp, 2),
        expected_improvement_roi_percent=round(roi_imp, 2),
        risk_change_label=risk_change,
        reasons=reasons[:12],
        warnings=warnings,
    )


def format_sell_to_buy_plan(plan: SellToBuyPlan) -> str:
    lines = [
        "🔁 Sell → buy (сценарий)",
        f"Оценка стоимости портфеля (fair): ~{plan.current_portfolio_value_ton:.0f} TON",
        f"Потенциальная ликвидность (quick net): ~{plan.expected_liquid_capital_ton:.0f} TON",
        "",
    ]
    if plan.suggested_sells:
        lines.append("Позиции:")
        for s in plan.suggested_sells:
            lines.append(
                f"- #{s.gift_id} {s.collection} #{s.number} · urgency: {s.urgency}\n"
                f"  list ~{s.normal_list_price_ton:.0f} / high ~{s.high_list_price_ton:.0f} TON, "
                f"quick ~{s.quick_sell_price_ton:.0f} TON, stop {s.stop_price_ton:.0f} TON"
            )
        lines.append("")
    if plan.replacement_buys:
        lines.append("Возможные замены (если решите продать сами):")
        for r in plan.replacement_buys:
            c = r.candidate
            lines.append(
                f"→ {c.collection} #{c.number}: buy до {c.max_buy_price_ton or 0:.0f} TON, "
                f"list {c.list_price_ton or 0:.0f} TON, p(sale) ~{c.sale_probability_percent:.0f}%, "
                f"eff {c.capital_efficiency_score:.0f}/100"
            )
            lines.append(f"  {r.reason}")
        lines.append("")
    lines.append(
        f"Оценка улучшения (вероятностная прибыль): ~{plan.expected_improvement_ton:+.1f} TON "
        f"(~{plan.expected_improvement_roi_percent:+.1f}% к ориентиру капитала)"
    )
    lines.append(f"Изменение риска (грубо): {plan.risk_change_label}")
    if plan.reasons:
        lines.append("\nЗаметки:\n" + "\n".join(f"- {x}" for x in plan.reasons))
    if plan.warnings:
        lines.append("\n" + "\n".join(f"⚠️ {w}" for w in plan.warnings))
    lines.append("\nНе автосделки: решения только вручную; это не финансовый совет.")
    return "\n".join(lines)

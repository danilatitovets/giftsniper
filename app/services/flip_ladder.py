"""Compound-style round targets — scenarios only, no guaranteed outcomes (Stage 34)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import Settings, get_settings


class FlipLadderStep(BaseModel):
    round_number: int
    starting_capital_ton: float
    target_capital_ton: float
    required_profit_ton: float
    required_roi_percent: float
    estimated_deals_needed: int
    recommended_deal_roi_range: str
    max_risk_label: str
    comment: str


class FlipLadderPlan(BaseModel):
    start_budget_ton: float
    goal_budget_ton: float
    steps: list[FlipLadderStep] = Field(default_factory=list)
    total_required_profit_ton: float = 0.0
    estimated_rounds: int = 0
    warning: str = ""
    disclaimer: str = (
        "Это сценарий сложения капитала, а не обещание результата: сроки и доходность могут отличаться, возможны потери."
    )


def _roi_band(risk_mode: str, settings: Settings | None = None) -> tuple[float, float]:
    st = settings or get_settings()
    if risk_mode == "conservative":
        lo, hi = float(st.compound_plan_conservative_roi) * 0.8, float(st.compound_plan_conservative_roi) * 1.2
    elif risk_mode == "aggressive":
        lo, hi = float(st.compound_plan_aggressive_roi) * 0.75, float(st.compound_plan_aggressive_roi) * 1.15
    else:
        lo, hi = float(st.compound_plan_normal_roi) * 0.72, float(st.compound_plan_normal_roi) * 1.2
    return round(lo, 1), round(hi, 1)


def build_flip_ladder(
    start_budget_ton: float,
    goal_budget_ton: float,
    risk_mode: str = "normal",
    settings: Settings | None = None,
) -> FlipLadderPlan:
    st = settings or get_settings()
    if start_budget_ton <= 0 or goal_budget_ton <= start_budget_ton:
        return FlipLadderPlan(
            start_budget_ton=start_budget_ton,
            goal_budget_ton=goal_budget_ton,
            warning="Цель должна быть больше стартового бюджета.",
        )
    mult = goal_budget_ton / start_budget_ton
    warning = ""
    if mult > 4.5:
        warning = (
            "Цель существенно выше старта: может потребоваться много раундов, выше риск просадок и дольше время "
            "(оценка, не прогноз)."
        )
    elif mult > 2.5:
        warning = "Умеренно агрессивная цель относительно старта — закладывайте запас по времени и риску."

    lo_roi, hi_roi = _roi_band(risk_mode, st)
    mid_roi = (lo_roi + hi_roi) / 2.0
    steps: list[FlipLadderStep] = []
    cur = start_budget_ton
    rnd = 0
    max_rounds = 24
    while cur < goal_budget_ton * 0.995 and rnd < max_rounds:
        rnd += 1
        growth = 1.0 + mid_roi / 100.0
        nxt = min(cur * growth, goal_budget_ton * 1.02)
        if nxt <= cur * 1.001:
            nxt = cur * (1.0 + lo_roi / 100.0)
        profit = nxt - cur
        req_roi = (profit / cur * 100.0) if cur > 0 else 0.0
        deals = max(1, int(round(mid_roi / max(8.0, hi_roi * 0.35))))
        risk_l = "high" if risk_mode == "aggressive" else ("low" if risk_mode == "conservative" else "medium")
        steps.append(
            FlipLadderStep(
                round_number=rnd,
                starting_capital_ton=round(cur, 2),
                target_capital_ton=round(nxt, 2),
                required_profit_ton=round(profit, 2),
                required_roi_percent=round(req_roi, 1),
                estimated_deals_needed=deals,
                recommended_deal_roi_range=f"{lo_roi:.0f}–{hi_roi:.0f}% за раунд (оценка)",
                max_risk_label=risk_l,
                comment="Промежуточная цель раунда; фактический ROI по сделкам будет отличаться.",
            )
        )
        cur = nxt

    total_profit = goal_budget_ton - start_budget_ton
    return FlipLadderPlan(
        start_budget_ton=round(start_budget_ton, 2),
        goal_budget_ton=round(goal_budget_ton, 2),
        steps=steps,
        total_required_profit_ton=round(total_profit, 2),
        estimated_rounds=len(steps),
        warning=warning,
    )


def format_flip_ladder(plan: FlipLadderPlan) -> str:
    lines = [
        f"📈 Compound plan (сценарий): {plan.start_budget_ton:.0f} → {plan.goal_budget_ton:.0f} TON",
        f"Раундов (оценка): {plan.estimated_rounds}",
        f"Суммарная прибыль в сценарии: ~{plan.total_required_profit_ton:.0f} TON",
        "",
    ]
    if plan.warning:
        lines.append(f"⚠️ {plan.warning}\n")
    for s in plan.steps[:12]:
        lines.append(
            f"Round {s.round_number}: {s.starting_capital_ton:.0f} → {s.target_capital_ton:.0f} TON "
            f"(+{s.required_profit_ton:.0f}, ~{s.required_roi_percent:.0f}% на капитал раунда)"
        )
        lines.append(
            f"  · ориентир сделок за раунд: ~{s.estimated_deals_needed}, ROI диапазон {s.recommended_deal_roi_range}, "
            f"риск-профиль: {s.max_risk_label}"
        )
    if len(plan.steps) > 12:
        lines.append(f"... ещё {len(plan.steps) - 12} шаг(ов)")
    lines.append("")
    lines.append(plan.disclaimer)
    return "\n".join(lines)

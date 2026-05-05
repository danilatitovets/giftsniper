from __future__ import annotations

from app.schemas.analysis import CapitalPlan, CapitalPlanItem
from app.services.diversification import calculate_collection_exposure
from app.services.market_regime import get_regime_allocation_multiplier


def calculate_bankroll_limits(user) -> dict:
    bankroll = float(user.bankroll_ton or 0.0)
    reserve_percent = int(user.reserve_percent or 20)
    max_deal_percent = int(user.max_deal_percent or 25)
    max_collection_percent = int(user.max_collection_percent or 40)
    reserve_ton = bankroll * reserve_percent / 100.0
    available_ton = max(0.0, bankroll - reserve_ton)
    return {
        "bankroll_ton": round(bankroll, 2),
        "reserve_ton": round(reserve_ton, 2),
        "available_ton": round(available_ton, 2),
        "max_per_deal_ton": round(bankroll * max_deal_percent / 100.0, 2),
        "max_per_collection_ton": round(bankroll * max_collection_percent / 100.0, 2),
    }


def _collection_absolute_exposure(portfolio: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in portfolio:
        out[row["collection"]] = out.get(row["collection"], 0.0) + float(row.get("value_ton", 0.0))
    return out


def calculate_collection_exposure(portfolio: list[dict]) -> dict[str, float]:
    return _collection_absolute_exposure(portfolio)


def _downside(value_ton: float) -> dict[str, float]:
    return {
        "-10%": round(value_ton * 0.9, 2),
        "-25%": round(value_ton * 0.75, 2),
        "-40%": round(value_ton * 0.6, 2),
    }


def allocate_capital(opportunities: list[dict], user_settings, existing_portfolio: list[dict]) -> CapitalPlan:
    limits = calculate_bankroll_limits(user_settings)
    collection_exposure = _collection_absolute_exposure(existing_portfolio)
    available = limits["available_ton"]
    selected: list[CapitalPlanItem] = []
    skipped: list[CapitalPlanItem] = []
    warnings: list[str] = []
    expected_profit = 0.0

    for row in opportunities:
        listing = row["listing"]
        estimate = row["estimate"]
        score = row["score"]
        collection = listing.collection
        price = float(listing.price_ton)
        tier = score.final_rank_label
        decision_type = getattr(estimate, "decision_type", None)
        if decision_type in {"AVOID", "NEED_MORE_DATA"}:
            skipped.append(
                CapitalPlanItem(
                    collection=collection,
                    number=listing.number,
                    price_ton=price,
                    tier=tier,
                    score=score.total_score,
                    allocated_ton=0.0,
                    reason="Decision engine: avoid / need more data",
                )
            )
            continue
        if tier in {"C_TIER", "AVOID"}:
            skipped.append(
                CapitalPlanItem(
                    collection=collection,
                    number=listing.number,
                    price_ton=price,
                    tier=tier,
                    score=score.total_score,
                    allocated_ton=0.0,
                    reason="Tier слишком низкий для основного плана",
                )
            )
            continue

        if row.get("freshness_label") == "old" and row.get("real_sales_count", 0) == 0:
            skipped.append(
                CapitalPlanItem(
                    collection=collection,
                    number=listing.number,
                    price_ton=price,
                    tier=tier,
                    score=score.total_score,
                    allocated_ton=0.0,
                    reason="Old data без recent sales",
                )
            )
            continue

        deal_limit = min(limits["max_per_deal_ton"], available)
        if price > deal_limit:
            skipped.append(
                CapitalPlanItem(
                    collection=collection,
                    number=listing.number,
                    price_ton=price,
                    tier=tier,
                    score=score.total_score,
                    allocated_ton=0.0,
                    reason=f"Цена {price:.2f} TON выше max per deal {deal_limit:.2f}",
                )
            )
            continue

        coll_used = collection_exposure.get(collection, 0.0)
        collection_left = max(0.0, limits["max_per_collection_ton"] - coll_used)
        if collection_left < price:
            skipped.append(
                CapitalPlanItem(
                    collection=collection,
                    number=listing.number,
                    price_ton=price,
                    tier=tier,
                    score=score.total_score,
                    allocated_ton=0.0,
                    reason="Лимит по коллекции исчерпан",
                )
            )
            continue

        reason = "Проходит фильтры доходности и риска"
        if decision_type == "SPECULATIVE_BUY":
            reason += " · спекулятивный размер — держите позицию меньше обычного"
        selected.append(
            CapitalPlanItem(
                collection=collection,
                number=listing.number,
                price_ton=price,
                tier=tier,
                score=score.total_score,
                allocated_ton=price,
                reason=reason,
            )
        )
        available = round(available - price, 2)
        collection_exposure[collection] = coll_used + price
        expected_profit += float(estimate.expected_profit_ton or 0.0)
        if len(selected) >= 3:
            break

    if not selected:
        warnings.append("Подходящих сделок нет, лучше держать кэш.")
    total_allocated = sum(x.allocated_ton for x in selected)
    avg_roi = 0.0
    if selected and total_allocated > 0:
        avg_roi = (expected_profit / total_allocated) * 100.0

    plan_value = total_allocated + max(0.0, expected_profit)
    return CapitalPlan(
        bankroll_ton=limits["bankroll_ton"],
        reserve_ton=limits["reserve_ton"],
        available_ton=limits["available_ton"],
        max_per_deal_ton=limits["max_per_deal_ton"],
        max_per_collection_ton=limits["max_per_collection_ton"],
        selected_opportunities=selected,
        skipped_opportunities=skipped,
        warnings=warnings,
        expected_profit_ton=round(expected_profit, 2),
        expected_roi_percent=round(avg_roi, 2),
        downside_scenario_ton=_downside(plan_value),
    )


def allocate_capital_dynamic(
    opportunities: list[dict], user_settings, existing_portfolio: list[dict], regime: str | None = None
) -> CapitalPlan:
    limits = calculate_bankroll_limits(user_settings)
    available = limits["available_ton"]
    absolute_exposure = _collection_absolute_exposure(existing_portfolio)
    selected: list[CapitalPlanItem] = []
    skipped: list[CapitalPlanItem] = []
    expected_profit = 0.0
    warnings: list[str] = []
    regime_multiplier = get_regime_allocation_multiplier(regime or "neutral")

    tier_mult = {"S_TIER": 1.0, "A_TIER": 0.75, "B_TIER": 0.4, "C_TIER": 0.0, "AVOID": 0.0}
    for row in opportunities:
        listing = row["listing"]
        estimate = row["estimate"]
        score = row["score"]
        tier = score.final_rank_label
        base_limit = limits["max_per_deal_ton"] * tier_mult.get(tier, 0.0) * regime_multiplier
        reason = "Проходит dynamic budgeting правила"
        if row.get("freshness_label") == "old":
            base_limit = 0.0
            reason = "old data: исключено из основного плана"
        elif row.get("freshness_label") == "stale":
            base_limit = min(base_limit, limits["max_per_deal_ton"] * 0.3)
        if row.get("real_sales_count", 0) == 0:
            base_limit = min(base_limit, limits["max_per_deal_ton"] * 0.5)
        if float(getattr(estimate, "confidence_score", 0) or 0) < 60:
            base_limit = min(base_limit, limits["max_per_deal_ton"] * 0.4)
        if float(getattr(estimate, "risk_score", 100) or 100) > 70:
            base_limit = min(base_limit, limits["max_per_deal_ton"] * 0.25)
        decision_type = getattr(estimate, "decision_type", None)
        if decision_type == "STRONG_BUY":
            pass
        elif decision_type == "BUY_IF_UNDER":
            base_limit = min(base_limit, limits["max_per_deal_ton"] * 0.85)
        elif decision_type == "SPECULATIVE_BUY":
            base_limit = min(base_limit, limits["max_per_deal_ton"] * 0.4)
        elif decision_type in {"AVOID", "NEED_MORE_DATA"}:
            base_limit = 0.0

        collection = listing.collection
        collection_left = max(0.0, limits["max_per_collection_ton"] - absolute_exposure.get(collection, 0.0))
        suggested = min(base_limit, available, collection_left)
        if regime in {"illiquid", "data_poor"} and tier not in {"S_TIER", "A_TIER"}:
            suggested = 0.0
            reason = f"Режим {regime}: только A/S-TIER"
        if tier in {"C_TIER", "AVOID"} or suggested <= 0:
            skipped.append(
                CapitalPlanItem(
                    collection=collection,
                    number=listing.number,
                    price_ton=float(listing.price_ton),
                    tier=tier,
                    score=score.total_score,
                    allocated_ton=0.0,
                    reason=reason if suggested <= 0 else "Tier слишком низкий",
                )
            )
            continue

        selected.append(
            CapitalPlanItem(
                collection=collection,
                number=listing.number,
                price_ton=float(listing.price_ton),
                tier=tier,
                score=score.total_score,
                allocated_ton=round(suggested, 2),
                reason=reason,
            )
        )
        available = round(available - suggested, 2)
        absolute_exposure[collection] = absolute_exposure.get(collection, 0.0) + suggested
        expected_profit += float(estimate.expected_profit_ton or 0.0) * (suggested / max(float(listing.price_ton), 1.0))
        if len(selected) >= 5:
            break

    if not selected:
        warnings.append("Лучше держать кэш: подходящих сделок в universe нет.")
    if regime:
        warnings.append(f"Market regime: {regime}, allocation multiplier: {int(regime_multiplier * 100)}%")
    allocated_total = sum(x.allocated_ton for x in selected)
    roi = (expected_profit / allocated_total * 100.0) if allocated_total > 0 else 0.0
    plan_value = allocated_total + max(0.0, expected_profit)
    return CapitalPlan(
        bankroll_ton=limits["bankroll_ton"],
        reserve_ton=limits["reserve_ton"],
        available_ton=limits["available_ton"],
        max_per_deal_ton=limits["max_per_deal_ton"],
        max_per_collection_ton=limits["max_per_collection_ton"],
        selected_opportunities=selected,
        skipped_opportunities=skipped,
        warnings=warnings,
        expected_profit_ton=round(expected_profit, 2),
        expected_roi_percent=round(roi, 2),
        downside_scenario_ton=_downside(plan_value),
    )


def format_capital_plan(plan: CapitalPlan) -> str:
    selected = (
        "\n".join(
            f"{idx}. {item.collection} #{item.number} — {item.allocated_ton:.2f} TON ({item.tier}, score {item.score})"
            for idx, item in enumerate(plan.selected_opportunities, start=1)
        )
        if plan.selected_opportunities
        else "Нет подходящих сделок."
    )
    skipped = (
        "\n".join(f"- {x.collection} #{x.number}: {x.reason}" for x in plan.skipped_opportunities[:5])
        if plan.skipped_opportunities
        else "- нет"
    )
    warnings = "\n".join(f"- {x}" for x in plan.warnings) if plan.warnings else "- нет"
    return (
        "💼 Capital Plan\n\n"
        f"Банк: {plan.bankroll_ton:.2f} TON\n"
        f"Reserve: {plan.reserve_ton:.2f} TON\n"
        f"Доступно для сделок: {plan.available_ton:.2f} TON\n"
        f"Max per deal: {plan.max_per_deal_ton:.2f} TON\n"
        f"Max per collection: {plan.max_per_collection_ton:.2f} TON\n\n"
        f"Рекомендация:\n{selected}\n\n"
        f"Пропущены:\n{skipped}\n\n"
        f"Expected profit: {plan.expected_profit_ton:+.2f} TON\n"
        f"Expected ROI: {plan.expected_roi_percent:+.2f}%\n"
        f"Downside -10/-25/-40: {plan.downside_scenario_ton.get('-10%')} / "
        f"{plan.downside_scenario_ton.get('-25%')} / {plan.downside_scenario_ton.get('-40%')} TON\n\n"
        f"Warnings:\n{warnings}"
    )

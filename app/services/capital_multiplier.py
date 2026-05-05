"""Budget-aware flip planning using existing pricing, decisions, and opportunity scores (Stage 34)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas.analysis import FlipAnalysisResult, OpportunityScore
from app.schemas.market_brain import PrecisionPricePlan
from app.services.diversification import calculate_collection_exposure
from app.services.market_regime import evaluate_collection_regime, evaluate_universe_regime


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _max_buy_ton(estimate: FlipAnalysisResult) -> float:
    raw = estimate.precision_plan_json
    if raw:
        try:
            plan = PrecisionPricePlan.model_validate_json(raw)
            return float(plan.max_buy_price_ton)
        except (json.JSONDecodeError, ValueError):
            pass
    return float(estimate.buy_zone_max_ton or 0.0)


def _source_quality_bucket(listing_source: str, is_mock: bool) -> Literal["mock", "manual", "real"]:
    s = (listing_source or "").lower()
    if is_mock or s == "mock":
        return "mock"
    if s == "manual":
        return "manual"
    return "real"


class FlipCandidate(BaseModel):
    collection: str
    number: int | None = None
    nft_address: str | None = None
    source_url: str | None = None
    buy_price_ton: float
    safe_buy_price_ton: float | None = None
    max_buy_price_ton: float | None = None
    aggressive_buy_price_ton: float | None = None
    list_price_ton: float | None = None
    high_list_price_ton: float | None = None
    quick_sell_price_ton: float | None = None
    stop_loss_price_ton: float | None = None
    expected_profit_ton: float | None = None
    expected_roi_percent: float | None = None
    probability_weighted_profit_ton: float | None = None
    sale_probability_percent: float = 0.0
    time_to_sell_estimate: str = ""
    capital_efficiency_score: float = 0.0
    risk_score: int = 0
    confidence_score: int = 0
    liquidity_score: int = 0
    rarity_score: float | None = None
    trait_opportunity_score: float | None = None
    decision_type: str = ""
    recommendation: str | None = None
    tier: str | None = None
    source_quality: str | None = None
    freshness_label: str | None = None
    has_recent_sales: bool = False
    has_trait_sales: bool = False
    is_speculative: bool = False
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def metrics_for_owned_gift(estimate: FlipAnalysisResult, purchase_ton: float | None) -> tuple[float, float, float]:
    """Sale probability, probability-weighted profit, capital efficiency for a held gift (scenario estimates)."""
    fc = FlipCandidate(
        collection="",
        number=0,
        buy_price_ton=float(purchase_ton or estimate.fair_price_ton or 0),
        list_price_ton=float(getattr(estimate, "normal_list_price_ton", None) or estimate.list_price_ton or 0),
        expected_profit_ton=float(estimate.expected_profit_ton or 0),
        expected_roi_percent=float(estimate.expected_roi_percent or 0),
        risk_score=int(estimate.risk_score or 0),
        confidence_score=int(estimate.confidence_score or 0),
        liquidity_score=int(estimate.liquidity_score or 0),
        decision_type=str(getattr(estimate, "decision_type", "") or ""),
        has_recent_sales=True,
        has_trait_sales=bool(getattr(estimate, "max_trait_recent_sales", None)),
        warnings=[],
    )
    ctx = {"market_regime": "neutral", "source_quality": "real", "freshness_label": "fresh"}
    sp = estimate_sale_probability(fc, ctx)
    fc = fc.model_copy(update={"sale_probability_percent": sp})
    fc = fc.model_copy(update={"probability_weighted_profit_ton": calculate_probability_weighted_profit(fc)})
    eff = calculate_capital_efficiency(fc)
    return sp, float(fc.probability_weighted_profit_ton or 0), eff


class SkippedCandidate(BaseModel):
    collection: str
    number: int | None = None
    buy_price_ton: float | None = None
    reason: str
    decision_type: str | None = None
    confidence_score: int | None = None
    risk_score: int | None = None


class CapitalMultiplierPlan(BaseModel):
    starting_budget_ton: float
    reserve_ton: float
    available_after_reserve_ton: float
    max_per_deal_ton: float
    max_speculative_deal_ton: float
    selected_candidates: list[FlipCandidate] = Field(default_factory=list)
    skipped_candidates: list[SkippedCandidate] = Field(default_factory=list)
    total_allocated_ton: float = 0.0
    unallocated_ton: float = 0.0
    expected_total_profit_ton: float = 0.0
    expected_total_roi_percent: float = 0.0
    probability_weighted_profit_ton: float = 0.0
    downside_scenario_ton: float = 0.0
    upside_scenario_ton: float = 0.0
    plan_risk_label: str = ""
    plan_confidence_label: str = ""
    next_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    market_regime: str | None = None


def estimate_sale_probability(
    candidate: FlipCandidate,
    market_context: dict[str, Any] | None = None,
) -> float:
    ctx = market_context or {}
    liq = float(candidate.liquidity_score or ctx.get("liquidity_score") or 50)
    conf = float(candidate.confidence_score or ctx.get("confidence_score") or 50)
    risk = float(candidate.risk_score or ctx.get("risk_score") or 50)
    has_recent = bool(candidate.has_recent_sales or ctx.get("has_recent_sales"))
    has_trait = bool(candidate.has_trait_sales or ctx.get("has_trait_sales"))
    recent_n = int(ctx.get("recent_sales_count") or 0)
    buy = float(candidate.buy_price_ton or ctx.get("listing_price_ton") or 0)
    floor = float(ctx.get("floor_ton") or 0)
    median_sale = ctx.get("median_sale_ton")
    median_sale_f = float(median_sale) if median_sale is not None else None
    normal_list = float(candidate.list_price_ton or ctx.get("normal_list_price_ton") or 0)
    spread = float(ctx.get("spread_percent") or 0)
    src = str(candidate.source_quality or ctx.get("source_quality") or "real")
    fresh = str(candidate.freshness_label or ctx.get("freshness_label") or "unknown")
    regime = str(ctx.get("market_regime") or "neutral")
    decision = str(candidate.decision_type or ctx.get("decision_type") or "")
    liq_adj = float(candidate.rarity_score or ctx.get("liquidity_adjusted_rarity") or 0)
    max_trait_sales = ctx.get("max_trait_recent_sales")
    mts = int(max_trait_sales) if max_trait_sales is not None else None
    rare_no_trait = bool(
        (mts is not None and mts == 0 and liq_adj >= 45) or ctx.get("rare_trait_no_sales")
    )

    base = 56.0
    base += (liq - 50) * 0.22
    base += (conf - 58) * 0.18
    base -= max(0.0, risk - 48) * 0.2
    if has_recent:
        base += 9.0
    if recent_n >= 5:
        base += 5.0
    if has_trait:
        base += 6.0
    if floor > 0 and buy > 0:
        rel = buy / floor
        if 0.88 <= rel <= 1.02:
            base += 4.0
        elif rel > 1.18:
            base -= 10.0
    if median_sale_f and median_sale_f > 0 and normal_list > 0:
        ratio = normal_list / median_sale_f
        if ratio <= 1.08:
            base += 6.0
        elif ratio > 1.22:
            base -= 14.0
    if spread > 45:
        base -= 11.0
    elif spread > 30:
        base -= 5.0
    if decision == "STRONG_BUY":
        base += 7.0
    elif decision == "SPECULATIVE_BUY":
        base -= 6.0
    elif decision in {"AVOID", "NEED_MORE_DATA"}:
        base -= 25.0
    if regime == "risk_on":
        base += 4.0
    elif regime in {"risk_off", "illiquid"}:
        base -= 12.0
    elif regime == "data_poor":
        base -= 8.0
    if src == "real" and fresh == "fresh" and has_recent and liq >= 58:
        base += 5.0

    caps: list[float] = [92.0]
    if src == "mock":
        caps.append(40.0)
    if src == "manual" and fresh == "stale":
        caps.append(50.0)
    if not has_recent and recent_n == 0:
        caps.append(55.0)
    if rare_no_trait:
        caps.append(45.0)
    if fresh == "old":
        caps.append(35.0)
    if regime == "illiquid":
        caps.append(40.0)
    if regime == "data_poor":
        caps.append(45.0)

    prob = min(base, min(caps))
    return round(_clamp(prob, 5.0, 90.0), 1)


def calculate_probability_weighted_profit(candidate: FlipCandidate) -> float:
    exp = candidate.expected_profit_ton
    if exp is None:
        return 0.0
    return round(float(exp) * (candidate.sale_probability_percent / 100.0), 2)


def _warning_penalty(warnings: list[str]) -> float:
    blob = " ".join(warnings).lower()
    pen = 0.0
    for key in ("illiquid", "фейк", "fake", "нет recent", "стоп", "риск"):
        if key in blob:
            pen += 2.5
    return pen


def calculate_capital_efficiency(candidate: FlipCandidate) -> float:
    roi = max(0.0, float(candidate.expected_roi_percent or 0.0))
    p = float(candidate.sale_probability_percent)
    c = max(1.0, float(candidate.confidence_score))
    l = max(1.0, float(candidate.liquidity_score))
    r = float(candidate.risk_score or 50)
    risk_penalty = r / 5.0 + _warning_penalty(candidate.warnings)
    scaled_roi = min(roi, 120.0) / 35.0
    raw = scaled_roi * 100.0 * (p / 100.0) * (c / 100.0) * (l / 100.0) - risk_penalty
    return round(_clamp(raw, 0.0, 100.0), 2)


def rank_candidates_for_budget(
    candidates: list[FlipCandidate],
    budget_ton: float,
    settings: Settings | None = None,
) -> list[FlipCandidate]:
    _ = budget_ton, settings
    enriched: list[FlipCandidate] = []
    for c in candidates:
        pw = calculate_probability_weighted_profit(c)
        eff = calculate_capital_efficiency(c.model_copy(update={"probability_weighted_profit_ton": pw}))
        enriched.append(c.model_copy(update={"probability_weighted_profit_ton": pw, "capital_efficiency_score": eff}))
    return sorted(enriched, key=lambda x: x.capital_efficiency_score, reverse=True)


def _is_speculative_row(estimate: FlipAnalysisResult) -> bool:
    dec = getattr(estimate, "decision_type", None)
    if dec == "SPECULATIVE_BUY":
        return True
    liq_adj = float(getattr(estimate, "liquidity_adjusted_rarity_score", 0) or 0)
    mts = getattr(estimate, "max_trait_recent_sales", None)
    if mts is not None and int(mts) == 0 and liq_adj >= 45:
        return True
    return False


def _warnings_from_row(estimate: FlipAnalysisResult, quality: Any) -> list[str]:
    w: list[str] = []
    if quality is not None:
        for x in getattr(quality, "warnings", None) or []:
            if x:
                w.append(str(x))
    for r in (estimate.reasons or [])[:6]:
        if any(k in r.lower() for k in ("риск", "осторож", "мало", "стары", "mock", "manual")):
            w.append(r)
    return w[:12]


def flip_candidate_from_opportunity_row(
    row: dict[str, Any],
    *,
    market_regime: str | None,
    settings: Settings | None = None,
) -> FlipCandidate:
    st = settings or get_settings()
    listing = row["listing"]
    estimate: FlipAnalysisResult = row["estimate"]
    score: OpportunityScore = row["score"]
    stats: dict = row.get("stats") or {}
    quality = row.get("quality")
    fresh = row.get("freshness_label") or "unknown"
    listing_src = getattr(listing, "source", "") or ""
    is_mock = bool(getattr(quality, "is_mock_data", False)) if quality is not None else False
    src_bucket = _source_quality_bucket(listing_src, is_mock)
    has_recent = bool(
        stats.get("sales_age_minutes") is not None and int(stats.get("sales_age_minutes") or 999999) <= 7 * 24 * 60
    )
    real_sales = int(row.get("real_sales_count") or stats.get("real_sales_count") or 0)
    mts = getattr(estimate, "max_trait_recent_sales", None)
    has_trait = bool(mts is not None and int(mts) > 0)

    max_buy = _max_buy_ton(estimate)
    floor_ton = 0.0
    coll_profile_json = getattr(estimate, "market_intelligence_json", None)
    if coll_profile_json:
        try:
            blob = json.loads(coll_profile_json)
            floor_ton = float(blob.get("collection_floor_ton") or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            floor_ton = 0.0
    median_sale = None
    if coll_profile_json:
        try:
            blob = json.loads(coll_profile_json)
            v = blob.get("median_sale_price_ton")
            median_sale = float(v) if v is not None else None
        except (json.JSONDecodeError, TypeError, ValueError):
            median_sale = None

    spec = _is_speculative_row(estimate)
    ctx = {
        "liquidity_score": estimate.liquidity_score,
        "confidence_score": estimate.confidence_score,
        "risk_score": estimate.risk_score,
        "has_recent_sales": has_recent,
        "has_trait_sales": has_trait,
        "recent_sales_count": real_sales,
        "listing_price_ton": float(listing.price_ton),
        "floor_ton": floor_ton,
        "median_sale_ton": median_sale,
        "normal_list_price_ton": float(getattr(estimate, "normal_list_price_ton", None) or estimate.list_price_ton or 0),
        "spread_percent": float(stats.get("spread_percent") or 0),
        "source_quality": src_bucket,
        "freshness_label": fresh,
        "market_regime": market_regime or stats.get("market_regime"),
        "decision_type": getattr(estimate, "decision_type", None) or "",
        "liquidity_adjusted_rarity": float(getattr(estimate, "liquidity_adjusted_rarity_score", 0) or 0),
        "max_trait_recent_sales": mts,
        "rare_trait_no_sales": bool(
            mts is not None and int(mts) == 0 and float(getattr(estimate, "liquidity_adjusted_rarity_score", 0) or 0) >= 45
        ),
    }
    base = FlipCandidate(
        collection=listing.collection,
        number=listing.number,
        nft_address=getattr(listing, "nft_address", None),
        source_url=getattr(listing, "url", None),
        buy_price_ton=float(listing.price_ton),
        safe_buy_price_ton=getattr(estimate, "safe_buy_price_ton", None),
        max_buy_price_ton=max_buy if max_buy > 0 else None,
        aggressive_buy_price_ton=getattr(estimate, "aggressive_buy_price_ton", None),
        list_price_ton=float(getattr(estimate, "normal_list_price_ton", None) or estimate.list_price_ton),
        high_list_price_ton=float(getattr(estimate, "high_list_price_ton", None) or estimate.optimistic_price_ton),
        quick_sell_price_ton=float(estimate.quick_sell_price_ton),
        stop_loss_price_ton=float(estimate.stop_price_ton),
        expected_profit_ton=float(estimate.expected_profit_ton),
        expected_roi_percent=float(estimate.expected_roi_percent),
        time_to_sell_estimate=str(getattr(estimate, "time_to_sell_estimate", None) or "") or "неизвестно",
        risk_score=int(estimate.risk_score or 0),
        confidence_score=int(estimate.confidence_score or 0),
        liquidity_score=int(estimate.liquidity_score or 0),
        rarity_score=getattr(estimate, "rarity_score", None),
        trait_opportunity_score=getattr(estimate, "trait_opportunity_score", None),
        decision_type=str(getattr(estimate, "decision_type", None) or ""),
        recommendation=getattr(estimate, "recommendation", None),
        tier=score.final_rank_label,
        source_quality=src_bucket,
        freshness_label=fresh,
        has_recent_sales=has_recent,
        has_trait_sales=has_trait,
        is_speculative=spec,
        reasons=list(estimate.reasons or [])[:8],
        warnings=_warnings_from_row(estimate, quality),
    )
    sp = estimate_sale_probability(base, ctx)
    base = base.model_copy(update={"sale_probability_percent": sp})
    pw = calculate_probability_weighted_profit(base)
    eff = calculate_capital_efficiency(base.model_copy(update={"probability_weighted_profit_ton": pw}))
    return base.model_copy(update={"probability_weighted_profit_ton": pw, "capital_efficiency_score": eff})


def _portfolio_rows_from_gifts(gifts: list[Any]) -> list[dict]:
    return [{"collection": g.collection, "value_ton": float(g.purchase_price_ton or 0.0)} for g in gifts]


def collection_regimes_from_ranked(ranked: list[dict], portfolio_rows: list[dict]) -> list[Any]:
    if not ranked:
        return []
    by_collection: dict[str, list[dict]] = {}
    for row in ranked:
        by_collection.setdefault(row["listing"].collection, []).append(row)
    coll_abs = calculate_collection_exposure(portfolio_rows)
    total_pf = sum(coll_abs.values()) or 1.0
    reports = []
    for coll, items in by_collection.items():
        exp_pct = float(coll_abs.get(coll, 0.0)) / total_pf * 100.0
        reports.append(
            evaluate_collection_regime(
                collection=coll,
                opportunities=items,
                portfolio_exposure_percent=exp_pct,
            )
        )
    reports.sort(key=lambda x: x.relative_strength_score, reverse=True)
    return reports


async def gather_ranked_with_market_regime(
    user: Any,
    universe_collections: list[str],
    settings: Settings,
    portfolio_rows: list[dict],
) -> tuple[list[dict], str | None]:
    from app.services.universe_opportunities import gather_ranked_universe_opportunities

    ranked = await gather_ranked_universe_opportunities(user, universe_collections, settings)
    reports = collection_regimes_from_ranked(ranked, portfolio_rows)
    regime = evaluate_universe_regime(reports) if reports else None
    regime_name = regime.regime if regime else None
    ranked2 = await gather_ranked_universe_opportunities(
        user, universe_collections, settings, market_regime=regime_name
    )
    return ranked2, regime_name


async def build_capital_multiplier_plan(
    user: Any,
    budget_ton: float,
    settings: Settings,
    *,
    universe_collections: list[str],
    gifts_for_regime: list[Any] | None = None,
    lite_mode: bool = False,
    max_selected_override: int | None = None,
    ranked_row_limit: int | None = None,
) -> tuple[CapitalMultiplierPlan, list[dict]]:
    from app.services.universe_opportunities import gather_ranked_universe_opportunities

    reserve_pct = float(user.reserve_percent if user.reserve_percent is not None else 20)
    deal_pct = float(user.max_deal_percent if user.max_deal_percent is not None else 25)
    reserve_ton = round(budget_ton * reserve_pct / 100.0, 2)
    available = round(max(0.0, budget_ton - reserve_ton), 2)
    max_per_deal = round(budget_ton * deal_pct / 100.0, 2)
    max_spec = round(budget_ton * float(settings.capital_multiplier_speculative_max_percent) / 100.0, 2)

    portfolio_rows = _portfolio_rows_from_gifts(gifts_for_regime or [])
    if lite_mode:
        ranked = await gather_ranked_universe_opportunities(user, universe_collections, settings)
        regime_name = None
        lim = ranked_row_limit if ranked_row_limit is not None else 24
        ranked = ranked[:lim]
    else:
        ranked, regime_name = await gather_ranked_with_market_regime(
            user, universe_collections, settings, portfolio_rows
        )

    min_p = int(settings.capital_multiplier_min_sale_probability)
    min_c = int(settings.capital_multiplier_min_confidence)
    if lite_mode:
        min_p = max(35, min_p - 12)
        min_c = max(42, min_c - 8)
    max_r = int(settings.capital_multiplier_max_risk)
    min_profit = float(settings.min_profit_ton)

    candidates_with_rows: list[tuple[FlipCandidate, dict]] = []
    skipped: list[SkippedCandidate] = []

    for row in ranked:
        est = row["estimate"]
        listing = row["listing"]
        price = float(listing.price_ton)
        max_buy = _max_buy_ton(est)
        dec = getattr(est, "decision_type", None)
        fresh = row.get("freshness_label") or "unknown"
        real_sales = int(row.get("real_sales_count") or 0)
        fc = flip_candidate_from_opportunity_row(row, market_regime=regime_name, settings=settings)

        def _skip(reason: str) -> None:
            skipped.append(
                SkippedCandidate(
                    collection=listing.collection,
                    number=listing.number,
                    buy_price_ton=price,
                    reason=reason,
                    decision_type=str(dec) if dec else None,
                    confidence_score=int(est.confidence_score) if est.confidence_score is not None else None,
                    risk_score=int(est.risk_score) if est.risk_score is not None else None,
                )
            )

        if max_buy > 0 and price > max_buy * 1.02:
            _skip(f"Цена выше max buy ~{max_buy:.1f} TON")
            continue
        if float(est.expected_profit_ton or 0) <= min_profit:
            _skip("Ожидаемая прибыль ниже порога после комиссий (оценка)")
            continue
        if int(est.confidence_score or 0) < min_c:
            _skip("Низкая уверенность (confidence) для плана")
            continue
        if fc.sale_probability_percent < min_p:
            _skip(
                f"Низкая оценка вероятности продажи ({fc.sale_probability_percent:.0f}% < {min_p}%)"
            )
            continue
        if dec in {"AVOID", "NEED_MORE_DATA"}:
            _skip(f"Decision engine: {dec}")
            continue
        if fresh == "old" and real_sales == 0:
            _skip("Устаревшие данные без недавних продаж")
            continue
        if int(est.risk_score or 100) > max_r:
            _skip(f"Риск выше лимита ({est.risk_score} > {max_r})")
            continue

        candidates_with_rows.append((fc, row))

    candidates_with_rows.sort(key=lambda x: x[0].capital_efficiency_score, reverse=True)
    top_n = int(max_selected_override) if max_selected_override is not None else int(settings.capital_multiplier_top_n)
    pool = candidates_with_rows[: max(top_n * 3, top_n)]

    selected: list[FlipCandidate] = []
    selected_rows: list[dict] = []
    remaining = available
    spec_used = 0.0
    spec_positions = 0
    small_budget = budget_ton < 80.0

    for c, row in pool:
        price = c.buy_price_ton
        if price > remaining + 1e-6:
            continue
        if price > max_per_deal + 1e-6:
            continue
        if c.is_speculative:
            if spec_used + price > max_spec + 1e-6:
                continue
            if small_budget and spec_positions >= 1:
                continue
            spec_used += price
            spec_positions += 1
        remaining -= price
        selected.append(c)
        selected_rows.append(row)
        if len(selected) >= top_n:
            break

    if not selected and candidates_with_rows:
        warn = (
            "Сильных позиций под лимиты сделки/спекуляции мало — рабочий капитал лучше оставить в кэше "
            "(сценарий, не совет)."
        )
    else:
        warn = ""

    total_alloc = sum(s.buy_price_ton for s in selected)
    unalloc = round(max(0.0, available - total_alloc), 2)
    exp_profit = sum(float(s.expected_profit_ton or 0) for s in selected)
    pw_sum = sum(float(s.probability_weighted_profit_ton or 0) for s in selected)
    roi_avg = (exp_profit / total_alloc * 100.0) if total_alloc > 0 else 0.0

    downside = round(-0.22 * total_alloc, 2)
    upside = round(pw_sum * 1.12, 2)

    if selected:
        avg_risk = sum(s.risk_score for s in selected) / len(selected)
        avg_conf = sum(s.confidence_score for s in selected) / len(selected)
        risk_l = "high" if avg_risk >= 68 else ("medium" if avg_risk >= 48 else "low")
        conf_l = "high" if avg_conf >= 72 else ("medium" if avg_conf >= 55 else "low")
    else:
        risk_l, conf_l = "n/a", "n/a"

    next_steps = [
        "Не покупать выше max buy из карточки сделки.",
        "Не заходить всем бюджетом в один NFT — держите лимиты.",
        "Если несколько дней нет сделки — пересмотреть quick sell (оценка).",
        "В режиме risk_off держите больше кэша.",
    ]
    warnings_out: list[str] = []
    if lite_mode:
        warnings_out.append(
            "Lite-режим: один проход по рынку и узкий набор коллекций; полный universe scan — в Pro (/upgrade)."
        )
    if warn:
        warnings_out.append(warn)
    if regime_name in {"illiquid", "data_poor", "risk_off"}:
        warnings_out.append(
            f"Режим рынка {regime_name}: вероятности и ликвидность могут быть хуже ожидаемого (оценка)."
        )

    plan = CapitalMultiplierPlan(
        starting_budget_ton=round(budget_ton, 2),
        reserve_ton=reserve_ton,
        available_after_reserve_ton=available,
        max_per_deal_ton=max_per_deal,
        max_speculative_deal_ton=max_spec,
        selected_candidates=selected,
        skipped_candidates=skipped[:25],
        total_allocated_ton=round(total_alloc, 2),
        unallocated_ton=unalloc,
        expected_total_profit_ton=round(exp_profit, 2),
        expected_total_roi_percent=round(roi_avg, 2),
        probability_weighted_profit_ton=round(pw_sum, 2),
        downside_scenario_ton=downside,
        upside_scenario_ton=upside,
        plan_risk_label=risk_l,
        plan_confidence_label=conf_l,
        next_steps=next_steps,
        warnings=warnings_out,
        market_regime=regime_name,
    )
    return plan, selected_rows


def format_capital_multiplier_plan(
    plan: CapitalMultiplierPlan,
    *,
    compact: bool = False,
    signal_hint_lines: list[str] | None = None,
) -> str:
    lines = [
        f"💼 Flip Plan на {plan.starting_budget_ton:.0f} TON",
        "",
        f"Резерв: {plan.reserve_ton:.0f} TON",
        f"Рабочий капитал: {plan.available_after_reserve_ton:.0f} TON",
        f"Max на сделку: {plan.max_per_deal_ton:.0f} TON",
        f"Speculative max: {plan.max_speculative_deal_ton:.0f} TON",
    ]
    if plan.market_regime:
        lines.append(f"Режим рынка (оценка): {plan.market_regime}")
    lines.append("")
    if plan.warnings:
        lines.append("⚠️ " + " ".join(plan.warnings))
        lines.append("")
    if not plan.selected_candidates:
        lines.append("Сейчас нет кандидатов, которые проходят фильтры под этот бюджет — кэш допустим (сценарий).")
    else:
        lines.append("Лучшие сделки:")
        lines.append("")
        for i, c in enumerate(plan.selected_candidates, start=1):
            safe_lo = c.safe_buy_price_ton or 0
            safe_hi = c.max_buy_price_ton or 0
            lo = min(safe_lo, safe_hi) * 0.97 if safe_lo and safe_hi else (safe_lo or safe_hi or 0)
            hi = max(safe_lo, safe_hi) * 0.99 if safe_lo and safe_hi else (safe_hi or 0)
            lines.append(f"{i}) {c.collection} #{c.number}")
            lines.append(f"Купить до: {(c.max_buy_price_ton or 0):.0f} TON")
            if lo > 0 and hi > 0:
                lines.append(f"Лучше брать: {lo:.0f}–{hi:.0f} TON")
            lp = c.list_price_ton or 0
            hlp = c.high_list_price_ton or 0
            if lp and hlp:
                lines.append(f"Выставить: {lp:.0f}–{hlp:.0f} TON")
            elif lp:
                lines.append(f"Выставить: ~{lp:.0f} TON")
            lines.append(f"Quick sell: {(c.quick_sell_price_ton or 0):.0f} TON")
            lines.append(f"Stop: {(c.stop_loss_price_ton or 0):.0f} TON")
            ep = c.expected_profit_ton or 0
            er = c.expected_roi_percent or 0
            lines.append(f"Ожидание (сценарий): {ep:+.0f} TON / {er:+.0f}%")
            lines.append(f"Вероятность продажи (оценка): {c.sale_probability_percent:.0f}%")
            lines.append(f"Capital efficiency: {c.capital_efficiency_score:.0f}/100")
            rlab = "high" if c.risk_score >= 68 else ("medium" if c.risk_score >= 48 else "low")
            lines.append(f"Risk: {rlab} ({c.risk_score}/100)")
            lines.append(f"Confidence: {c.confidence_score}")
            if not compact:
                lines.append(
                    f"Почему: {', '.join(c.reasons[:3]) if c.reasons else 'модель opportunity + ликвидность'}"
                )
            lines.append("")
    if plan.skipped_candidates and not compact:
        lines.append("Пропущено:")
        for s in plan.skipped_candidates[:8]:
            price_bit = f" за {s.buy_price_ton:.0f} TON" if s.buy_price_ton else ""
            lines.append(f"- {s.collection} #{s.number}{price_bit} — {s.reason}.")
        lines.append("")
    lines.append("План действий:")
    for i, ns in enumerate(plan.next_steps, start=1):
        lines.append(f"{i}. {ns}")
    lines.append("")
    if signal_hint_lines:
        lines.append("Signal IDs (оценка снимка):")
        lines.extend(signal_hint_lines)
        lines.append("")
    lines.append(
        "Дисклеймер: сценарный расчёт, не финансовый совет; прибыль и срок продажи не гарантируются."
    )
    return "\n".join(lines)

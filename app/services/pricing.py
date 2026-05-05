from __future__ import annotations

import statistics

from app.config import Settings, get_settings
from app.schemas.analysis import FlipAnalysisResult
from app.schemas.gift import GiftCard
from app.schemas.market_brain import CollectionMarketProfile, PrecisionPricePlan
from app.services.rarity import rarity_score


def roi_targets_from_settings(settings: Settings | None = None) -> dict[str, float]:
    s = settings or get_settings()
    return {
        "conservative": float(s.pricing_target_roi_conservative),
        "normal": float(s.pricing_target_roi_normal),
        "aggressive": float(s.pricing_target_roi_aggressive),
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def estimate_gift_price(
    gift: GiftCard,
    market_data: dict,
    risk_mode: str = "normal",
    buy_price_ton: float | None = None,
    marketplace_fee_percent: float = 5.0,
    estimated_extra_costs_ton: float = 0.0,
    min_profit_ton: float = 5.0,
    settings: Settings | None = None,
) -> FlipAnalysisResult:
    floor = float(market_data.get("collection_floor", 0.0) or 0.0)
    trait_floors = [float(x) for x in market_data.get("trait_floors", []) if x]
    listing_prices = [float(x) for x in market_data.get("similar_listings", []) if x]
    recent_sales = [float(x) for x in market_data.get("recent_sales", []) if x]
    listed_count = int(market_data.get("listed_count", 0) or 0)

    samples = listing_prices + recent_sales
    market_median = _median(samples) or floor or 0.0
    floor_anchor = _median([floor] + trait_floors) if trait_floors else floor
    floor_anchor = floor_anchor or market_median

    rare_boost = 1.0 + min(0.18, rarity_score(gift.attributes) * 0.18)
    fair_price = (market_median * 0.72 + floor_anchor * 0.28) * rare_boost

    low_similar = min(listing_prices) if listing_prices else fair_price * 0.92
    high_similar = max(listing_prices) if listing_prices else fair_price * 1.08
    quick_sell = min(fair_price * 0.95, low_similar * 1.01)
    quick_sell = max(quick_sell, (floor * 0.95 if floor else quick_sell))

    risk_map = {"conservative": 1.13, "normal": 1.2, "aggressive": 1.27}
    opt_mul = risk_map.get(risk_mode, 1.2)
    list_price = min(max(fair_price * 1.12, market_median * 1.06), high_similar * 1.02)
    optimistic = fair_price * opt_mul
    stop_price = max(quick_sell * 0.98, floor * 0.97 if floor else quick_sell * 0.98)

    fee_factor = 1 - marketplace_fee_percent / 100.0
    net_sale = list_price * fee_factor

    roi_targets = roi_targets_from_settings(settings)
    required_roi = roi_targets.get(risk_mode, roi_targets["normal"])

    sales_count = len(recent_sales)
    liquidity_score = 45
    liquidity_score += min(30, sales_count * 4)
    liquidity_score += min(20, max(0, 120 - listed_count) // 10)
    liquidity_score = max(5, min(95, liquidity_score))

    spread_ratio = ((high_similar - low_similar) / low_similar) if low_similar else 0.0
    risk_score = 35 + int(spread_ratio * 35)
    if liquidity_score < 40:
        required_roi += 6
        risk_score += 14
    elif liquidity_score < 55:
        required_roi += 3
        risk_score += 8

    confidence = 78
    reasons: list[str] = []
    if sales_count < 5:
        confidence -= 16
        reasons.append("Мало последних продаж, уверенность снижена.")
    if trait_floors and max(trait_floors) > floor:
        reasons.append("Trait floor выше floor коллекции — это поддерживает цену.")
    if listing_prices and min(listing_prices) < fair_price * 0.9:
        confidence -= 10
        reasons.append("Есть похожие лоты заметно дешевле рынка.")
    rarity = rarity_score(gift.attributes)
    if rarity > 0.6:
        reasons.append("У подарка редкие атрибуты, это повышает справедливую цену.")
    if rarity > 0.55 and sales_count == 0:
        confidence = min(confidence, 52)
        reasons.append("Редкость без подтвержденных продаж не дает высокой уверенности.")
    if spread_ratio > 0.3:
        risk_score += 12
        reasons.append("Высокий разброс цен по листингам повышает риск.")
    if liquidity_score < 40:
        reasons.append("Ликвидность низкая, требуется больший запас по ROI.")
    if low_similar < list_price * 0.9:
        reasons.append("Похожие лоты дешевле расчетной цены листинга.")

    confidence -= max(0, int(spread_ratio * 12))
    confidence = max(25, min(95, confidence))
    risk_score = max(10, min(95, risk_score))

    buy_zone_max = (net_sale - estimated_extra_costs_ton) / (1 + required_roi / 100.0) if net_sale > 0 else 0.0
    buy_zone_min = buy_zone_max * 0.92

    actual_buy = buy_price_ton if buy_price_ton is not None and buy_price_ton > 0 else buy_zone_max
    roi_estimated = buy_price_ton is None
    expected_profit = net_sale - actual_buy - estimated_extra_costs_ton
    expected_roi = (expected_profit / actual_buy * 100.0) if actual_buy > 0 else -100.0

    recommendation = "AVOID"
    if buy_price_ton is not None:
        if expected_profit <= 0 or expected_roi < required_roi or expected_profit < min_profit_ton:
            recommendation = "AVOID" if buy_price_ton > buy_zone_max * 1.08 else "BUY_ONLY_CHEAP"
        elif confidence >= 55 and risk_score <= 60:
            recommendation = "BUY_FOR_FLIP"
        else:
            recommendation = "BUY_ONLY_CHEAP"
    else:
        if fair_price > floor * 1.12 and low_similar >= floor * 1.08:
            recommendation = "LIST_HIGHER"
        elif quick_sell < floor * 1.02 and confidence < 55:
            recommendation = "SELL_FAST"
        else:
            recommendation = "HOLD"

    if not reasons:
        reasons.append("Рынок стабильный, выраженных аномалий не найдено.")
    if roi_estimated:
        reasons.append("ROI рассчитан от расчетной buy zone, а не от фактической цены покупки.")

    return FlipAnalysisResult(
        buy_zone_min_ton=round(buy_zone_min, 2),
        buy_zone_max_ton=round(buy_zone_max, 2),
        quick_sell_price_ton=round(quick_sell, 2),
        fair_price_ton=round(fair_price, 2),
        list_price_ton=round(list_price, 2),
        optimistic_price_ton=round(optimistic, 2),
        stop_price_ton=round(stop_price, 2),
        marketplace_fee_percent=round(marketplace_fee_percent, 2),
        expected_net_sale_ton=round(net_sale, 2),
        expected_profit_ton=round(expected_profit, 2),
        expected_roi_percent=round(expected_roi, 2),
        liquidity_score=liquidity_score,
        risk_score=risk_score,
        confidence_score=confidence,
        recommendation=recommendation,
        roi_based_on_estimated_buy_zone=roi_estimated,
        reasons=reasons,
    )


def calculate_safe_buy_price(
    *,
    net_normal_sale: float,
    median_sale: float | None,
    floor: float,
    required_roi: float,
    marketplace_fee_percent: float,
    estimated_extra_costs_ton: float,
    min_profit_ton: float,
    confidence: float,
    sales_count: int,
    is_mock_or_stale: bool,
    settings: Settings | None = None,
) -> float:
    s = settings or get_settings()
    fee_factor = 1 - marketplace_fee_percent / 100.0
    base = (net_normal_sale - estimated_extra_costs_ton) / (1 + required_roi / 100.0) if net_normal_sale > 0 else 0.0
    if median_sale and median_sale > 0 and sales_count >= 2:
        cap_from_sales = median_sale * fee_factor - estimated_extra_costs_ton - min_profit_ton
        cap_from_sales /= 1 + required_roi / 100.0
        base = min(base, cap_from_sales)
    elif sales_count == 0 and floor > 0:
        base = min(base, floor * float(s.pricing_no_sales_safe_buy_discount))
    conf_mul = 0.78 + min(0.15, confidence / 700.0)
    if confidence < 50:
        conf_mul *= float(s.pricing_low_confidence_discount)
    if is_mock_or_stale:
        conf_mul *= float(s.pricing_stale_data_discount)
    return max(0.01, base * conf_mul)


def calculate_max_buy_price(
    *,
    net_normal_sale: float,
    required_roi: float,
    estimated_extra_costs_ton: float,
    min_profit_ton: float,
) -> float:
    if net_normal_sale <= 0:
        return 0.0
    min_roi_floor = (net_normal_sale - estimated_extra_costs_ton - min_profit_ton) / (1 + required_roi / 100.0)
    return max(0.01, min_roi_floor * 1.04)


def calculate_list_targets(
    fair: float,
    normal_list: float,
    high_allowed: bool,
    liquidity: float,
    volatility_high: bool,
) -> tuple[float, float, float, list[str]]:
    warnings: list[str] = []
    quick_flip = min(fair * 0.96, normal_list * 0.94)
    high = normal_list * 1.12 if high_allowed else normal_list * 1.04
    if not high_allowed:
        warnings.append("High list ограничен: нужны сильная редкость и ликвидность.")
    if liquidity < 50:
        high = min(high, normal_list * 1.06)
        warnings.append("Ликвидность средняя/низкая — осторожнее с верхней ценой листинга.")
    if volatility_high:
        high = min(high, normal_list * 1.08)
        warnings.append("Повышенная волатильность — high list снижен.")
    return round(quick_flip, 2), round(normal_list, 2), round(high, 2), warnings


def calculate_quick_sell_price(fair: float, floor: float, low_listing: float | None) -> float:
    q = min(fair * 0.95, (low_listing * 1.01) if low_listing else fair * 0.95)
    if floor > 0:
        q = max(q, floor * 0.93)
    return round(q, 2)


def calculate_stop_loss_price(
    safe_buy: float,
    floor: float,
    quick_sell: float,
    volatility_score: float,
) -> float:
    """Exit level; must not be above safe_buy (risk management anchor)."""
    widen = 1.0 + min(0.08, volatility_score / 500.0)
    raw = min(safe_buy * 0.92 * widen, quick_sell * 0.94, floor * 0.9 if floor else safe_buy * 0.9)
    return round(min(raw, safe_buy * 0.995), 2)


def estimate_time_to_sell(liquidity_score: float, sales_count: int) -> str:
    if liquidity_score >= 70 and sales_count >= 5:
        return "оценочно 2–5 дней"
    if liquidity_score >= 50:
        return "оценочно 3–10 дней"
    if liquidity_score >= 35:
        return "оценочно 1–3 недели"
    return "оценочно неопределённо (мало ликвидности)"


def calculate_precision_price_plan(
    base: FlipAnalysisResult,
    coll: CollectionMarketProfile | None,
    *,
    risk_mode: str,
    marketplace_fee_percent: float,
    estimated_extra_costs_ton: float,
    min_profit_ton: float,
    floor: float,
    median_sale: float | None,
    sales_count: int,
    listing_low: float | None,
    combined_liquidity_adj_rarity: float,
    is_mock_or_stale: bool,
    settings: Settings | None = None,
) -> PrecisionPricePlan:
    s = settings or get_settings()
    roi_targets = roi_targets_from_settings(s)
    required_roi = roi_targets.get(risk_mode, roi_targets["normal"])
    fee_factor = 1 - marketplace_fee_percent / 100.0
    normal_list = float(base.list_price_ton or 0)
    net_normal = normal_list * fee_factor
    safe = calculate_safe_buy_price(
        net_normal_sale=net_normal,
        median_sale=median_sale,
        floor=floor,
        required_roi=required_roi,
        marketplace_fee_percent=marketplace_fee_percent,
        estimated_extra_costs_ton=estimated_extra_costs_ton,
        min_profit_ton=min_profit_ton,
        confidence=float(base.confidence_score or 50),
        sales_count=sales_count,
        is_mock_or_stale=is_mock_or_stale,
        settings=s,
    )
    max_buy = calculate_max_buy_price(
        net_normal_sale=net_normal,
        required_roi=required_roi,
        estimated_extra_costs_ton=estimated_extra_costs_ton,
        min_profit_ton=min_profit_ton,
    )
    max_buy = min(max_buy, float(base.buy_zone_max_ton or max_buy))
    aggressive = min(max_buy, safe * 1.06)
    vol_high = bool(coll and coll.volatility_score > 35)
    high_ok = combined_liquidity_adj_rarity >= 58 and (coll.liquidity_score if coll else 0) >= 55 and sales_count >= 3
    qf, nl, hl, lw = calculate_list_targets(
        float(base.fair_price_ton or 0),
        normal_list,
        high_ok,
        float(coll.liquidity_score if coll else base.liquidity_score or 40),
        vol_high,
    )
    qs = calculate_quick_sell_price(float(base.fair_price_ton or 0), floor, listing_low)
    stop = calculate_stop_loss_price(safe, floor, qs, float(coll.volatility_score if coll else 30))
    downside = round(min(floor * 0.88, qs * 0.92) if floor else qs * 0.9, 2)
    upside = round(max(hl * fee_factor, net_normal * 1.05), 2)
    buy_ref = max_buy
    exp_profit = net_normal - buy_ref - estimated_extra_costs_ton
    exp_roi = (exp_profit / buy_ref * 100.0) if buy_ref > 0 else 0.0
    reasons = [
        "Safe buy учитывает комиссию, минимальную прибыль и целевой ROI.",
        "Max buy — верхняя граница, выше которой сделка обычно слабеет.",
    ]
    warnings = list(lw)
    if sales_count == 0:
        warnings.append("Нет недавних продаж — safe buy сильно консервативен относительно floor.")
    tts = estimate_time_to_sell(float(coll.liquidity_score if coll else base.liquidity_score or 40), sales_count)
    return PrecisionPricePlan(
        safe_buy_price_ton=round(safe, 2),
        max_buy_price_ton=round(max_buy, 2),
        aggressive_buy_price_ton=round(aggressive, 2),
        quick_flip_list_price_ton=qf,
        normal_list_price_ton=nl,
        high_list_price_ton=hl,
        quick_sell_price_ton=qs,
        stop_loss_price_ton=stop,
        downside_price_ton=downside,
        upside_price_ton=upside,
        expected_net_sale_ton=round(net_normal, 2),
        expected_net_profit_ton=round(exp_profit, 2),
        expected_roi_percent=round(exp_roi, 2),
        marketplace_fee_percent=marketplace_fee_percent,
        estimated_extra_costs_ton=estimated_extra_costs_ton,
        time_to_sell_estimate=tts,
        confidence_score=float(base.confidence_score or 0),
        risk_score=float(base.risk_score or 0),
        liquidity_score=float(coll.liquidity_score if coll else base.liquidity_score or 0),
        recommendation="precision_plan",
        reasons=reasons,
        warnings=warnings,
    )


def format_precision_price_plan(plan: PrecisionPricePlan) -> str:
    return (
        "💎 Precision price plan\n"
        f"Safe buy ≤ {plan.safe_buy_price_ton:.2f} TON\n"
        f"Max buy ≤ {plan.max_buy_price_ton:.2f} TON\n"
        f"Aggressive buy ~ {plan.aggressive_buy_price_ton:.2f} TON\n"
        f"List: quick {plan.quick_flip_list_price_ton:.2f} · normal {plan.normal_list_price_ton:.2f} · high {plan.high_list_price_ton:.2f} TON\n"
        f"Quick sell ~ {plan.quick_sell_price_ton:.2f} TON · Stop ~ {plan.stop_loss_price_ton:.2f} TON\n"
        f"Expected net sale ~ {plan.expected_net_sale_ton:.2f} TON · PnL ~ {plan.expected_net_profit_ton:+.2f} TON · ROI ~ {plan.expected_roi_percent:+.1f}%\n"
        f"Time to sell: {plan.time_to_sell_estimate}\n"
        f"Confidence {plan.confidence_score:.0f}/100 · Risk {plan.risk_score:.0f}/100 · Liquidity {plan.liquidity_score:.0f}/100"
    )


def explain_price_plan_bounds(plan: PrecisionPricePlan) -> tuple[str, str]:
    """Why max buy is capped / why safe buy is not lower (plain-language risk framing)."""
    why_not_higher = (
        f"Max buy ({plan.max_buy_price_ton:.2f} TON) ограничен целевым ROI и net sale ~{plan.expected_net_sale_ton:.2f} TON после комиссии; "
        "выше этого входа запас маржи обычно слишком тонкий."
    )
    why_not_lower = (
        f"Safe buy ({plan.safe_buy_price_ton:.2f} TON) уже учитывает комиссию, минимальную прибыль и консервативный ROI; "
        "ещё ниже — только если готовы жёстче фильтровать сделки и держать кэш дольше."
    )
    return why_not_higher, why_not_lower


def format_precision_price_plan_extended(
    plan: PrecisionPricePlan,
    *,
    listing_price_ton: float | None = None,
    confidence_explanation: str = "",
) -> str:
    base = format_precision_price_plan(plan)
    lines = [base]
    if listing_price_ton is not None and listing_price_ton > 0:
        lines.append(f"\nТекущий ориентир цены (листинг/ввод): {listing_price_ton:.2f} TON")
    if confidence_explanation.strip():
        lines.append("\n" + confidence_explanation.strip())
    wh, wl = explain_price_plan_bounds(plan)
    lines.append("\nПочему не выше (max buy):\n" + wh)
    lines.append("\nПочему не ниже (safe buy):\n" + wl)
    lines.append(
        "\nЭто сценарный план, не обещание прибыли. Рынок может сдвинуться до исполнения."
    )
    return "".join(lines)


def is_viable_flip(estimate: FlipAnalysisResult, risk_mode: str = "normal", settings: Settings | None = None) -> bool:
    target = roi_targets_from_settings(settings).get(risk_mode, 18.0)
    if estimate.expected_profit_ton <= 0:
        return False
    if estimate.expected_roi_percent < target:
        return False
    return estimate.recommendation in ("BUY_FOR_FLIP", "BUY_ONLY_CHEAP")

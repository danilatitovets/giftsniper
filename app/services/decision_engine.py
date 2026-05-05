from __future__ import annotations

from app.config import Settings, get_settings
from app.schemas.analysis import FlipAnalysisResult
from app.schemas.market_brain import DecisionResult, DecisionType, PrecisionPricePlan


def recommendation_for_decision(decision: DecisionType) -> str:
    m: dict[DecisionType, str] = {
        "STRONG_BUY": "BUY_FOR_FLIP",
        "BUY_IF_UNDER": "BUY_ONLY_CHEAP",
        "SPECULATIVE_BUY": "BUY_ONLY_CHEAP",
        "HOLD": "HOLD",
        "LIST_NOW": "LIST_HIGHER",
        "LIST_HIGH": "LIST_HIGHER",
        "QUICK_SELL": "SELL_FAST",
        "AVOID": "AVOID",
        "NEED_MORE_DATA": "HOLD",
    }
    return m.get(decision, "HOLD")


def _critical_warning_hit(reasons: list[str], plan_warnings: list[str]) -> bool:
    blob = " ".join(reasons + plan_warnings).lower()
    return any(
        x in blob
        for x in ("фейк", "fake premium", "нет recent sales", "нет недавних продаж", "illiquid", "неликвид")
    )


def make_buy_decision(
    *,
    buy_price: float | None,
    plan: PrecisionPricePlan,
    base: FlipAnalysisResult,
    trait_opp_score: float | None,
    combined_rarity_adj: float,
    sales_count: int,
    market_regime: str | None,
    settings: Settings | None = None,
    strong_buy_trait_ok: bool = True,
    spread_percent: float | None = None,
) -> DecisionResult:
    reasons: list[str] = []
    warnings: list[str] = []
    conf = float(base.confidence_score or 0)
    risk = float(base.risk_score or 50)
    liq = float(plan.liquidity_score or base.liquidity_score or 40)
    safe = plan.safe_buy_price_ton
    max_buy = plan.max_buy_price_ton
    next_actions: list[str] = []
    cfg = settings or get_settings()
    critical = _critical_warning_hit(list(base.reasons or []), list(plan.warnings or []))
    if spread_percent is not None and spread_percent > 55:
        critical = True
        warnings.append("Очень широкий спред — STRONG_BUY отключён.")

    if conf < 50:
        return DecisionResult(
            decision="NEED_MORE_DATA",
            action_label_ru="Нужно больше данных",
            max_buy_price_ton=max_buy,
            safe_buy_price_ton=safe,
            confidence_score=conf,
            risk_score=risk,
            reasons=["Confidence ниже 50 — не показываем агрессивный buy."],
            warnings=["Проверьте свежие продажи и ликвидность."],
            next_actions=["Обновите market data", "Сравните с trait floor"],
        )

    if buy_price is None:
        hold = make_hold_decision(plan=plan, base=base, combined_rarity_adj=combined_rarity_adj)
        return hold

    if buy_price > max_buy * 1.02 or (conf < 40 and buy_price > safe * 1.15):
        reasons.append(f"Цена выше max buy ~{max_buy:.1f} TON — сделка выглядит слабой.")
        next_actions=[f"Пробовать вход ниже {max_buy:.1f} TON", "Перепроверить trait premium"]
        return DecisionResult(
            decision="AVOID",
            action_label_ru="Не покупать по этой цене",
            max_buy_price_ton=max_buy,
            safe_buy_price_ton=safe,
            confidence_score=conf,
            risk_score=risk,
            reasons=reasons,
            warnings=warnings,
            next_actions=next_actions,
        )

    if buy_price <= safe * 1.01:
        reasons.append("Цена в safe-зоне относительно плана; прибыль не гарантируется.")
        warnings.append("Рынок может сдвинуться — используйте stop и лимиты.")

    req_sales = cfg.pricing_strong_buy_require_recent_sales
    sales_ok = (sales_count >= 3) if req_sales else True
    strong = (
        conf >= float(cfg.pricing_strong_buy_min_confidence)
        and liq >= float(cfg.pricing_strong_buy_min_liquidity)
        and sales_ok
        and risk <= 62
        and buy_price <= safe * 1.03
        and ((trait_opp_score or 0) >= 40 or sales_count >= 8)
        and strong_buy_trait_ok
        and not critical
    )
    if strong:
        reasons.append("Сильный сигнал: ликвидность, продажи и цена в зоне.")
        return DecisionResult(
            decision="STRONG_BUY",
            action_label_ru="Сильный интерес (осторожно, не гарантия)",
            max_buy_price_ton=max_buy,
            safe_buy_price_ton=safe,
            confidence_score=conf,
            risk_score=risk,
            reasons=reasons,
            warnings=warnings + ["Не используйте кредитное плечо; соблюдайте лимиты банка."],
            next_actions=["Лимитный вход около safe buy", f"Не выше max buy {max_buy:.1f}"],
        )

    speculative = sales_count < 2 or (trait_opp_score or 0) < 35 or combined_rarity_adj < 40
    if speculative and buy_price <= max_buy:
        reasons.append("Спекулятивный сценарий: мало продаж или слабый rarity-сигнал.")
        if market_regime in {"risk_off", "illiquid", "data_poor"}:
            warnings.append(f"Режим {market_regime}: уменьшите размер позиции.")
        return DecisionResult(
            decision="SPECULATIVE_BUY",
            action_label_ru="Спекулятивный вход только маленьким размером",
            max_buy_price_ton=max_buy,
            safe_buy_price_ton=safe,
            confidence_score=conf,
            risk_score=risk,
            reasons=reasons,
            warnings=warnings,
            next_actions=["Малый размер", f"Цель выхода около {plan.normal_list_price_ton:.1f}"],
        )

    if buy_price <= max_buy:
        reasons.append(f"Покупка допустима только ниже ~{max_buy:.1f} TON (max buy).")
        return DecisionResult(
            decision="BUY_IF_UNDER",
            action_label_ru=f"Покупать только ниже ~{max_buy:.0f} TON",
            max_buy_price_ton=max_buy,
            safe_buy_price_ton=safe,
            confidence_score=conf,
            risk_score=risk,
            reasons=reasons,
            warnings=warnings,
            next_actions=[f"Лимит {max_buy:.1f}", f"Stop около {plan.stop_loss_price_ton:.1f}"],
        )

    return DecisionResult(
        decision="AVOID",
        action_label_ru="Вне зоны",
        max_buy_price_ton=max_buy,
        safe_buy_price_ton=safe,
        confidence_score=conf,
        risk_score=risk,
        reasons=["Условия не сходятся."],
        warnings=warnings,
        next_actions=[],
    )


def make_sell_decision(
    *,
    plan: PrecisionPricePlan,
    base: FlipAnalysisResult,
    purchase_price: float | None,
    market_regime: str | None,
) -> DecisionResult:
    reasons: list[str] = []
    if market_regime in {"risk_off", "illiquid"}:
        return DecisionResult(
            decision="QUICK_SELL",
            action_label_ru="Быстрый выход или удержание кэша",
            quick_sell_price_ton=plan.quick_sell_price_ton,
            list_price_ton=plan.quick_flip_list_price_ton,
            stop_loss_price_ton=plan.stop_loss_price_ton,
            confidence_score=float(base.confidence_score or 0),
            risk_score=float(base.risk_score or 0),
            reasons=["Режим риска off/illiquid — приоритет ликвидности."],
            warnings=[],
            next_actions=[f"Рассмотреть продажу около {plan.quick_sell_price_ton:.1f}"],
        )
    if purchase_price and plan.normal_list_price_ton > purchase_price * 1.12:
        reasons.append("Оценочная цена листинга даёт запас над покупкой.")
        return DecisionResult(
            decision="LIST_NOW",
            action_label_ru="Можно выставлять по нормальному листу",
            list_price_ton=plan.normal_list_price_ton,
            quick_sell_price_ton=plan.quick_sell_price_ton,
            stop_loss_price_ton=plan.stop_loss_price_ton,
            confidence_score=float(base.confidence_score or 0),
            risk_score=float(base.risk_score or 0),
            reasons=reasons,
            warnings=[],
            next_actions=[f"Ориентир листинга {plan.normal_list_price_ton:.1f}"],
        )
    return DecisionResult(
        decision="LIST_HIGH",
        action_label_ru="Пробовать верх диапазона только при сильной редкости",
        list_price_ton=plan.high_list_price_ton,
        quick_sell_price_ton=plan.quick_sell_price_ton,
        stop_loss_price_ton=plan.stop_loss_price_ton,
        confidence_score=float(base.confidence_score or 0),
        risk_score=float(base.risk_score or 0),
        reasons=["Используйте high list только если ликвидность подтверждена."],
        warnings=plan.warnings[:3],
        next_actions=["Следите за конкурентными лотами"],
    )


def make_hold_decision(*, plan: PrecisionPricePlan, base: FlipAnalysisResult, combined_rarity_adj: float) -> DecisionResult:
    return DecisionResult(
        decision="HOLD",
        action_label_ru="Удержание / ждать данных",
        list_price_ton=plan.normal_list_price_ton,
        quick_sell_price_ton=plan.quick_sell_price_ton,
        stop_loss_price_ton=plan.stop_loss_price_ton,
        confidence_score=float(base.confidence_score or 0),
        risk_score=float(base.risk_score or 0),
        reasons=[f"Комбинированная редкость (adj) ~{combined_rarity_adj:.0f}/100 — без цены входа держим нейтрально."],
        warnings=[],
        next_actions=["Уточните цену через /deal ... | <TON>"],
    )


def make_unified_decision(
    *,
    buy_price: float | None,
    plan: PrecisionPricePlan,
    base: FlipAnalysisResult,
    trait_opp_score: float | None,
    combined_rarity_adj: float,
    sales_count: int,
    market_regime: str | None,
    owns_asset: bool,
    purchase_price: float | None,
    settings: Settings | None = None,
    strong_buy_trait_ok: bool = True,
    spread_percent: float | None = None,
) -> DecisionResult:
    if owns_asset and buy_price is None:
        return make_sell_decision(
            plan=plan, base=base, purchase_price=purchase_price, market_regime=market_regime
        )
    return make_buy_decision(
        buy_price=buy_price,
        plan=plan,
        base=base,
        trait_opp_score=trait_opp_score,
        combined_rarity_adj=combined_rarity_adj,
        sales_count=sales_count,
        market_regime=market_regime,
        settings=settings,
        strong_buy_trait_ok=strong_buy_trait_ok,
        spread_percent=spread_percent,
    )


def apply_decision_to_estimate(base: FlipAnalysisResult, decision: DecisionResult) -> FlipAnalysisResult:
    rec = recommendation_for_decision(decision.decision)
    return base.model_copy(
        update={
            "recommendation": rec,
            "decision_type": decision.decision,
            "decision_summary": decision.action_label_ru,
        }
    )


def format_decision_matrix(d: DecisionResult) -> str:
    return (
        f"Verdict: {d.decision} — {d.action_label_ru}\n"
        f"Safe buy: {d.safe_buy_price_ton}\nMax buy: {d.max_buy_price_ton}\n"
        f"List: {d.list_price_ton} · Quick: {d.quick_sell_price_ton} · Stop: {d.stop_loss_price_ton}\n"
        + ("Почему:\n- " + "\n- ".join(d.reasons) if d.reasons else "")
        + ("\nРиск:\n- " + "\n- ".join(d.warnings) if d.warnings else "")
    )

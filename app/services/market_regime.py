from __future__ import annotations

from app.schemas.analysis import CollectionIntelligence, MarketRegime


def get_regime_allocation_multiplier(regime: str) -> float:
    return {
        "risk_on": 1.0,
        "neutral": 0.75,
        "risk_off": 0.45,
        "illiquid": 0.25,
        "data_poor": 0.3,
    }.get(regime, 0.5)


def _label_from_freshness(values: list[str]) -> str:
    if not values:
        return "unknown"
    if any(v == "old" for v in values):
        return "old"
    if any(v == "stale" for v in values):
        return "stale"
    if any(v == "fresh" for v in values):
        return "fresh"
    return "unknown"


def evaluate_collection_regime(collection: str, opportunities: list[dict], portfolio_exposure_percent: float = 0.0) -> CollectionIntelligence:
    if not opportunities:
        return CollectionIntelligence(
            collection=collection,
            regime="data_poor",
            relative_strength_score=25,
            avg_opportunity_score=0,
            best_opportunity_score=0,
            liquidity_score=20,
            freshness_label="unknown",
            real_data_available=False,
            manual_data_available=False,
            recent_sales_count=0,
            warnings=["Нет кандидатов по коллекции"],
            recommendation="DATA_NEEDED",
        )
    avg_score = int(sum(x["score"].total_score for x in opportunities) / len(opportunities))
    best_score = max(x["score"].total_score for x in opportunities)
    avg_liq = int(sum(int(x["estimate"].liquidity_score or 0) for x in opportunities) / len(opportunities))
    avg_risk = int(sum(int(x["estimate"].risk_score or 100) for x in opportunities) / len(opportunities))
    fresh_labels = [x.get("freshness_label", "unknown") for x in opportunities]
    freshness_label = _label_from_freshness(fresh_labels)
    real_data = any(x["listing"].source.lower() == "getgems" for x in opportunities)
    manual_data = any(x["listing"].source.lower() == "manual" for x in opportunities)
    recent_sales_count = sum(int(x.get("real_sales_count", 0) or 0) for x in opportunities)
    warnings: list[str] = []
    regime = "neutral"
    if not real_data and manual_data and recent_sales_count == 0:
        regime = "data_poor"
        warnings.append("Преобладают manual/mock данные без подтвержденных продаж")
    elif avg_liq < 35 or recent_sales_count == 0:
        regime = "illiquid"
        warnings.append("Низкая ликвидность или нет recent sales")
    elif freshness_label in {"stale", "old"} or avg_risk > 70:
        regime = "risk_off"
        warnings.append("Свежесть/риск ухудшают рыночный режим")
    elif best_score >= 75 and avg_liq >= 55 and freshness_label == "fresh" and recent_sales_count > 0:
        regime = "risk_on"
    strength = int(max(15, min(95, avg_score * 0.45 + best_score * 0.25 + avg_liq * 0.2 + (15 if real_data else -5))))
    recommendation = "WATCH"
    if regime == "risk_on" and strength >= 70:
        recommendation = "PRIORITIZE"
    elif regime in {"risk_off", "illiquid"}:
        recommendation = "REDUCE_EXPOSURE" if portfolio_exposure_percent > 40 else "WATCH"
    elif regime == "data_poor":
        recommendation = "DATA_NEEDED"
    if portfolio_exposure_percent > 60:
        recommendation = "REDUCE_EXPOSURE"
        warnings.append(f"Экспозиция {portfolio_exposure_percent:.0f}% уже слишком высокая")
    if strength < 35 and recommendation not in {"DATA_NEEDED"}:
        recommendation = "AVOID_FOR_NOW"
    return CollectionIntelligence(
        collection=collection,
        regime=regime,
        relative_strength_score=strength,
        avg_opportunity_score=avg_score,
        best_opportunity_score=best_score,
        liquidity_score=avg_liq,
        freshness_label=freshness_label,
        real_data_available=real_data,
        manual_data_available=manual_data,
        recent_sales_count=recent_sales_count,
        warnings=warnings,
        recommendation=recommendation,
    )


def evaluate_universe_regime(collection_reports: list[CollectionIntelligence]) -> MarketRegime:
    if not collection_reports:
        return MarketRegime(
            regime="data_poor",
            score=20,
            liquidity_score=20,
            sales_activity_score=15,
            freshness_score=20,
            source_quality_score=25,
            opportunity_quality_score=20,
            risk_score=80,
            warnings=["Universe пуст или не содержит пригодных данных"],
            reasons=["Добавьте коллекции и данные для анализа"],
        )
    liq = int(sum(x.liquidity_score for x in collection_reports) / len(collection_reports))
    opp = int(sum(x.avg_opportunity_score for x in collection_reports) / len(collection_reports))
    fresh_map = {"fresh": 85, "stale": 55, "old": 25, "unknown": 40}
    fresh = int(sum(fresh_map.get(x.freshness_label, 40) for x in collection_reports) / len(collection_reports))
    source_quality = int(
        sum((75 if x.real_data_available else (45 if x.manual_data_available else 25)) for x in collection_reports) / len(collection_reports)
    )
    sales = int(sum(min(100, x.recent_sales_count * 15) for x in collection_reports) / len(collection_reports))
    risk = int(max(10, min(95, 100 - (liq * 0.35 + opp * 0.25 + fresh * 0.2 + source_quality * 0.2))))
    score = int(max(0, min(100, liq * 0.2 + sales * 0.2 + fresh * 0.2 + source_quality * 0.2 + opp * 0.2 - risk * 0.15)))
    warnings: list[str] = []
    reasons: list[str] = []
    regime = "neutral"
    if source_quality < 45 or sales < 25:
        regime = "data_poor"
        reasons.append("Мало реальных данных и/или продаж")
    elif liq < 35:
        regime = "illiquid"
        reasons.append("Низкая ликвидность по universe")
    elif risk > 65 or fresh < 50:
        regime = "risk_off"
        reasons.append("Повышенный риск и/или устаревшие данные")
    elif score >= 65 and liq >= 55 and sales >= 45 and fresh >= 60:
        regime = "risk_on"
        reasons.append("Свежие данные, продажи и ликвидность поддерживают риск-on")
    else:
        regime = "neutral"
        reasons.append("Смешанный рынок без явного перевеса")
    if regime in {"risk_off", "illiquid", "data_poor"}:
        warnings.append("Рекомендуется более консервативный вход и больший кеш-резерв")
    return MarketRegime(
        regime=regime,
        score=score,
        liquidity_score=liq,
        sales_activity_score=sales,
        freshness_score=fresh,
        source_quality_score=source_quality,
        opportunity_quality_score=opp,
        risk_score=risk,
        warnings=warnings,
        reasons=reasons,
    )


def format_market_regime_report(regime: MarketRegime) -> str:
    reasons = "\n".join(f"- {x}" for x in regime.reasons) if regime.reasons else "- нет"
    warnings = "\n".join(f"- {x}" for x in regime.warnings) if regime.warnings else "- нет"
    actions = {
        "risk_on": "- можно работать стандартным риском\n- приоритет A/S_TIER",
        "neutral": "- умеренный размер позиций\n- избегать слабых C_TIER",
        "risk_off": "- не входить полной суммой\n- повышать требования к дисконту",
        "illiquid": "- брать только самые ликвидные сделки\n- остальное пропускать",
        "data_poor": "- нужны реальные/ручные данные для надежного анализа\n- лучше держать кэш",
    }.get(regime.regime, "- действовать консервативно")
    return (
        "🌡 Market Regime\n\n"
        f"Режим: {regime.regime}\n"
        f"Score: {regime.score}/100\n\n"
        f"Почему:\n{reasons}\n\n"
        f"Метрики:\n"
        f"Liquidity: {regime.liquidity_score}/100\n"
        f"Sales activity: {regime.sales_activity_score}/100\n"
        f"Freshness: {regime.freshness_score}/100\n"
        f"Source quality: {regime.source_quality_score}/100\n"
        f"Opportunity quality: {regime.opportunity_quality_score}/100\n"
        f"Risk: {regime.risk_score}/100\n\n"
        f"Warnings:\n{warnings}\n\n"
        f"Что делать:\n{actions}"
    )

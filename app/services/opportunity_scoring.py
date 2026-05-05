from __future__ import annotations

from app.config import get_settings
from app.schemas.analysis import OpportunityScore


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, round(value))))


def _tier_from_score(total_score: int) -> str:
    if total_score >= 85:
        return "S_TIER"
    if total_score >= 70:
        return "A_TIER"
    if total_score >= 55:
        return "B_TIER"
    if total_score >= 40:
        return "C_TIER"
    return "AVOID"


def calculate_opportunity_score(analysis_result, market_quality, freshness: dict) -> OpportunityScore:
    roi = float(analysis_result.expected_roi_percent or 0.0)
    profit = float(analysis_result.expected_profit_ton or 0.0)
    liquidity = int(analysis_result.liquidity_score or 0)
    confidence = int(analysis_result.confidence_score or 0)
    risk = int(analysis_result.risk_score or 100)
    freshness_label = freshness.get("label", "unknown")
    has_recent_sales = freshness.get("has_recent_sales", False)
    listing_price = freshness.get("listing_price_ton")
    sources = [s.lower() for s in (market_quality.sources_used or [])]

    trait_opp = float(getattr(analysis_result, "trait_opportunity_score", 0) or 0)
    prec_conf = float(getattr(analysis_result, "confidence_score", 0) or 0)
    liq_adj_rare = float(getattr(analysis_result, "liquidity_adjusted_rarity_score", 0) or 0)
    max_buy = getattr(analysis_result, "buy_zone_max_ton", None)
    decision_type = getattr(analysis_result, "decision_type", None)
    max_trait_sales = getattr(analysis_result, "max_trait_recent_sales", None)
    spread_pct = float(freshness.get("spread_percent") or 0)
    settings = get_settings()

    roi_score = _clamp((roi + 10) * 2.5)
    profit_score = _clamp((profit + 5) * 3.0)
    liquidity_score = _clamp(liquidity)
    confidence_score = _clamp(confidence)
    freshness_map = {"fresh": 90, "stale": 60, "old": 30, "unknown": 45}
    freshness_score = freshness_map.get(freshness_label, 45)

    source_quality_score = 55
    if "getgems" in sources:
        source_quality_score += 25
    if "manual" in sources:
        source_quality_score -= 10
    if "tonapi" in sources:
        source_quality_score += 5
    if market_quality.is_mock_data or "mock" in sources:
        source_quality_score = min(source_quality_score, 35)
    source_quality_score = _clamp(source_quality_score)
    risk_penalty = _clamp(risk)

    boost = min(18, trait_opp * 0.12 + liq_adj_rare * 0.05)

    total = (
        roi_score * 0.22
        + profit_score * 0.18
        + liquidity_score * 0.14
        + confidence_score * 0.14
        + freshness_score * 0.09
        + source_quality_score * 0.09
        - risk_penalty * 0.14
        + boost
    )

    if profit <= 0:
        total = min(total, 35)
    if freshness_label == "old" and not has_recent_sales:
        total = min(total, 58)
    if market_quality.is_mock_data or "mock" in sources:
        total = min(total, 50)
    if freshness_label == "stale" and "manual" in sources and "getgems" not in sources:
        total = min(total, 69)
    if liquidity_score < 45 and total > 84:
        total = 84
    if confidence_score < 50 and total > 74:
        total = 74
    if prec_conf < 55:
        total = min(total, 78)

    total_score = _clamp(total)
    tier = _tier_from_score(total_score)
    if (market_quality.is_mock_data or "mock" in sources) and tier in {"S_TIER", "A_TIER", "B_TIER"}:
        tier = "C_TIER"
    if freshness_label == "old" and not has_recent_sales and tier in {"S_TIER", "A_TIER"}:
        tier = "B_TIER"

    target_roi = float(settings.pricing_target_roi_normal)
    if roi < target_roi or profit <= 0:
        if tier in {"S_TIER", "A_TIER"}:
            tier = "B_TIER"
    if confidence_score < 58 or liquidity_score < 48:
        if tier == "S_TIER":
            tier = "A_TIER"
    if freshness_label == "old" or (not has_recent_sales and int(freshness.get("real_sales_count") or 0) == 0):
        if tier == "S_TIER":
            tier = "A_TIER"
    mb = float(max_buy or 0)
    sp = float(listing_price or 0)
    if sp > 0 and mb > 0 and sp > mb * 1.02:
        if tier in {"S_TIER", "A_TIER"}:
            tier = "B_TIER"
    if liq_adj_rare >= 60 and trait_opp < 25 and int(freshness.get("real_sales_count") or 0) == 0:
        if tier == "S_TIER":
            tier = "B_TIER"
    if decision_type == "SPECULATIVE_BUY" and tier in {"S_TIER", "A_TIER"}:
        tier = "B_TIER"
    if decision_type in {"NEED_MORE_DATA", "AVOID"} and tier in {"S_TIER", "A_TIER", "B_TIER"}:
        tier = "C_TIER"
    if decision_type == "STRONG_BUY" and int(freshness.get("real_sales_count") or 0) < 3:
        if tier == "S_TIER":
            tier = "A_TIER"
    if spread_pct > 50 and tier in {"S_TIER", "A_TIER"}:
        tier = "B_TIER"
    if (
        max_trait_sales is not None
        and max_trait_sales == 0
        and liq_adj_rare >= 45
        and settings.pricing_rare_no_sales_max_tier.upper() == "B_TIER"
    ):
        if tier == "S_TIER":
            tier = "B_TIER"
        elif tier == "A_TIER":
            tier = "B_TIER"

    breakdown = [
        f"ROI score: {roi_score}/100",
        f"Profit score: {profit_score}/100",
        f"Liquidity score: {liquidity_score}/100",
        f"Confidence score: {confidence_score}/100",
        f"Freshness score: {freshness_score}/100",
        f"Source quality score: {source_quality_score}/100",
        f"Risk penalty: -{risk_penalty}",
    ]
    return OpportunityScore(
        total_score=total_score,
        roi_score=roi_score,
        profit_score=profit_score,
        liquidity_score=liquidity_score,
        confidence_score=confidence_score,
        freshness_score=freshness_score,
        risk_penalty=risk_penalty,
        source_quality_score=source_quality_score,
        final_rank_label=tier,
        breakdown=breakdown,
    )


def rank_opportunities(opportunities: list[dict]) -> list[dict]:
    return sorted(opportunities, key=lambda x: x["score"].total_score, reverse=True)


def format_score_breakdown(score: OpportunityScore) -> str:
    return (
        "🧠 Score breakdown:\n"
        f"Total: {score.total_score}/100 — {score.final_rank_label}\n"
        f"ROI: {score.roi_score}/100\n"
        f"Profit: {score.profit_score}/100\n"
        f"Liquidity: {score.liquidity_score}/100\n"
        f"Confidence: {score.confidence_score}/100\n"
        f"Freshness: {score.freshness_score}/100\n"
        f"Source quality: {score.source_quality_score}/100\n"
        f"Risk penalty: -{score.risk_penalty}"
    )

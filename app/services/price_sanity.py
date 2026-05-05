"""Stage 37 — cap unrealistic prices when market evidence is weak."""

from __future__ import annotations

from typing import Any

from app.schemas.analysis import FlipAnalysisResult


def detect_unrealistic_price_gap(
    *,
    anchor_ton: float | None,
    fair_ton: float,
    floor_ton: float | None,
    sales_count: int,
    source_is_mock: bool,
) -> bool:
    if anchor_ton is None or anchor_ton <= 0:
        return False
    if fair_ton <= 0:
        return False
    if anchor_ton >= 5 and fair_ton > anchor_ton * 6 and sales_count == 0:
        return True
    if floor_ton and floor_ton > 0 and fair_ton > floor_ton * 5 and sales_count == 0:
        return True
    if source_is_mock and anchor_ton < 15 and fair_ton > 50:
        return True
    return False


def apply_price_sanity_caps(
    result: FlipAnalysisResult,
    *,
    listing_hint_ton: float | None,
    floor_ton: float | None,
    sales_count: int,
    max_trait_sales: int,
    collection_known: bool,
) -> FlipAnalysisResult:
    """Lower fair/list ceilings when model explodes without sales support."""
    reasons = list(result.reasons or [])
    fair = float(result.fair_price_ton or 0)
    anchor = listing_hint_ton or floor_ton
    mockish = sales_count == 0 and max_trait_sales == 0

    if not collection_known and mockish and fair > 30:
        cap = min(fair, 30.0)
        if cap < fair:
            reasons.append("Цена не повышалась: коллекция не в registry и нет подтверждённых продаж.")
        result = result.model_copy(update={"fair_price_ton": cap, "reasons": reasons})

    if detect_unrealistic_price_gap(
        anchor_ton=anchor,
        fair_ton=float(result.fair_price_ton or 0),
        floor_ton=floor_ton,
        sales_count=sales_count,
        source_is_mock=False,
    ):
        cap2 = max(anchor or 0, floor_ton or 0) * 1.25 if (anchor or floor_ton) else fair
        cap2 = min(cap2, fair)
        if cap2 < fair - 1:
            reasons.append("Цена ограничена: нет подтверждённых продаж по trait / выборке.")
        result = result.model_copy(
            update={
                "fair_price_ton": min(fair, cap2),
                "buy_zone_max_ton": min(result.buy_zone_max_ton, cap2 * 1.05) if result.buy_zone_max_ton else result.buy_zone_max_ton,
                "reasons": reasons,
            }
        )

    if max_trait_sales == 0 and sales_count == 0 and result.buy_zone_max_ton and floor_ton and floor_ton > 0:
        max_buy_cap = floor_ton * 1.35
        if result.buy_zone_max_ton > max_buy_cap:
            reasons.append("Max buy ограничен относительно floor без продаж.")
            result = result.model_copy(
                update={
                    "buy_zone_max_ton": min(result.buy_zone_max_ton, max_buy_cap),
                    "reasons": reasons,
                }
            )

    return result


def validate_price_plan_against_market(result: FlipAnalysisResult, *, floor_ton: float | None) -> FlipAnalysisResult:
    _ = floor_ton
    return result

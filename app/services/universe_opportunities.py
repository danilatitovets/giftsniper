"""Shared universe opportunity gathering (Stage 34): scan + analyze + score + rank."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.schemas.gift import GiftCard
from app.services.analyzer import AnalyzerService
from app.services.market_data_validity import filter_mock_listings_for_production
from app.services.opportunity_scoring import calculate_opportunity_score, rank_opportunities
from app.sources.factory import create_market_source


async def gather_ranked_universe_opportunities(
    user: Any,
    collections: list[str],
    settings: Settings,
    *,
    market_regime: str | None = None,
) -> list[dict]:
    source = create_market_source(settings, user_id=user.id)
    analyzer = AnalyzerService(source)
    opportunities: list[dict] = []
    for collection in collections:
        listings = await source.search_underpriced(collection, filters={})
        listings = filter_mock_listings_for_production(settings, listings)
        for listing in listings:
            estimate = await analyzer.analyze_gift(
                GiftCard(collection=listing.collection, number=listing.number),
                risk_mode=user.risk_mode,
                buy_price_ton=listing.price_ton,
                market_regime=market_regime,
            )
            quality = analyzer.last_data_quality
            stats = analyzer.last_market_stats
            freshness_label = (
                "old"
                if "old" in [stats.get("floor_freshness"), stats.get("sales_freshness")]
                else (
                    "stale"
                    if "stale"
                    in [
                        stats.get("floor_freshness"),
                        stats.get("sales_freshness"),
                        stats.get("listings_freshness"),
                    ]
                    else "fresh"
                )
            )
            score = calculate_opportunity_score(
                estimate,
                quality,
                {
                    "label": freshness_label,
                    "has_recent_sales": bool(
                        stats.get("sales_age_minutes") is not None
                        and stats.get("sales_age_minutes") <= 7 * 24 * 60
                    ),
                    "listing_price_ton": float(listing.price_ton),
                    "real_sales_count": int(stats.get("real_sales_count") or 0),
                    "spread_percent": float(stats.get("spread_percent") or 0),
                },
            )
            opportunities.append(
                {
                    "listing": listing,
                    "estimate": estimate,
                    "score": score,
                    "freshness_label": freshness_label,
                    "real_sales_count": int(stats.get("real_sales_count") or 0),
                    "stats": stats,
                    "quality": quality,
                    "signal_label": (
                        "real listing signal"
                        if listing.source.lower() in {"getgems", "tonnel", "fragment"}
                        else (
                            "manual estimate, verify before buying (fresh)"
                            if listing.source.lower() == "manual" and freshness_label == "fresh"
                            else (
                                "manual estimate, verify before buying (stale)"
                                if listing.source.lower() == "manual"
                                else "test signal"
                            )
                        )
                    ),
                }
            )
    return rank_opportunities(opportunities)

from __future__ import annotations

import statistics

from app.config import Settings
from app.schemas.market import ListingSchema, MarketFloor, SaleSchema
from app.schemas.market_brain import CollectionMarketProfile, TraitMarketProfile
from app.sources.base import MarketSource


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.mean(vals))


def _stdev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return float(statistics.stdev(vals))


def calculate_liquidity_velocity(sales_count: int, listing_count: int, window_days: int = 7) -> float:
    """Rough velocity: sales per listing per day (normalized)."""
    if listing_count <= 0:
        return float(sales_count) / max(window_days, 1)
    return float(sales_count) / max(listing_count, 1) / max(window_days, 1)


def calculate_market_depth(listing_prices: list[float], floor_ton: float) -> float:
    if not listing_prices or floor_ton <= 0:
        return 0.0
    sorted_p = sorted(listing_prices)
    n = min(5, len(sorted_p))
    band = sorted_p[n - 1] - sorted_p[0] if n > 1 else 0.0
    depth = max(0.0, 1.0 - min(1.0, band / max(floor_ton, 1e-6)))
    return round(depth * 100.0, 2)


def calculate_spread_risk(low: float | None, high: float | None) -> float:
    if not low or not high or low <= 0:
        return 0.0
    return max(0.0, (high - low) / low * 100.0)


def calculate_floor_stability(
    collection_floor: float,
    lowest_listing: float | None,
    median_listing: float | None,
) -> tuple[float, list[str]]:
    warnings: list[str] = []
    if collection_floor <= 0:
        return 30.0, ["Нет надёжного floor для оценки стабильности."]
    score = 70.0
    if lowest_listing is not None and lowest_listing > 0:
        gap = (collection_floor - lowest_listing) / collection_floor * 100.0
        if gap > 12:
            warnings.append("Floor нестабилен / риск андеркута: есть листинги заметно ниже опорного floor.")
            score -= 25
        elif gap > 5:
            score -= 10
            warnings.append("Есть листинги ниже floor — проверьте актуальность данных.")
    if median_listing is not None and median_listing > 0 and lowest_listing:
        if lowest_listing < median_listing * 0.85:
            warnings.append("Низкие лоты сильно ниже медианы листингов — возможен разрыв ликвидности.")
            score -= 12
    return max(5.0, min(100.0, score)), warnings


def calculate_trait_premium(trait_floor: float | None, collection_floor: float) -> float | None:
    if trait_floor is None or collection_floor <= 0:
        return None
    return (trait_floor - collection_floor) / collection_floor * 100.0


def compare_trait_vs_collection_floor(trait_floor: float | None, collection_floor: float) -> str:
    p = calculate_trait_premium(trait_floor, collection_floor)
    if p is None:
        return "нет данных по trait floor"
    if p > 25:
        return f"trait floor заметно выше коллекции (~{p:.0f}%)"
    if p > 5:
        return f"умеренный премиум к коллекции (~{p:.0f}%)"
    if p < -5:
        return "trait floor ниже или на уровне коллекции"
    return "премиум к коллекции небольшой"


def detect_overpriced_trait(profile: TraitMarketProfile) -> bool:
    if profile.trait_floor_ton is None or profile.trait_floor_ton <= 0:
        return False
    if profile.trait_recent_sales_count == 0 and profile.trait_listing_count <= 1:
        return profile.trait_floor_ton > 0  # thin book + high floor = risky
    return False


def detect_undervalued_trait(profile: TraitMarketProfile) -> bool:
    if profile.trait_median_sale_price_ton is None:
        return False
    if profile.trait_floor_ton is None:
        return False
    return profile.trait_median_sale_price_ton > profile.trait_floor_ton * 1.08


def _listing_matches_trait(listing: ListingSchema, trait_type: str, trait_value: str) -> bool:
    attrs = listing.attributes_json.get("attributes") or listing.attributes_json.get("traits") or []
    if isinstance(attrs, dict):
        attrs = [attrs]
    tt = trait_type.strip().lower()
    tv = trait_value.strip().lower()
    for a in attrs:
        if not isinstance(a, dict):
            continue
        t1 = str(a.get("trait_type") or a.get("type") or "").lower()
        v1 = str(a.get("trait_value") or a.get("value") or "").lower()
        if t1 == tt and v1 == tv:
            return True
    return False


def sale_matches_trait(sale: SaleSchema, trait_type: str, trait_value: str) -> bool:
    attrs = sale.attributes_json.get("attributes") or sale.attributes_json.get("traits") or []
    if isinstance(attrs, dict):
        attrs = [attrs]
    tt = trait_type.strip().lower()
    tv = trait_value.strip().lower()
    for a in attrs:
        if not isinstance(a, dict):
            continue
        t1 = str(a.get("trait_type") or a.get("type") or "").lower()
        v1 = str(a.get("trait_value") or a.get("value") or "").lower()
        if t1 == tt and v1 == tv:
            return True
    return False


def build_collection_market_profile(
    collection: str,
    floor: MarketFloor | None,
    listings: list[ListingSchema],
    sales: list[SaleSchema],
    settings: Settings,
    *,
    source_quality: str = "unknown",
    freshness_label: str = "unknown",
) -> CollectionMarketProfile:
    warnings: list[str] = []
    floor_ton = float(floor.floor_ton) if floor else 0.0
    listed_meta = int(floor.listed_count or 0) if floor else 0
    prices = [float(l.price_ton) for l in listings if l.price_ton and l.price_ton > 0]
    sale_prices = [float(s.price_ton) for s in sales if s.price_ton and s.price_ton > 0]
    listing_count = len(prices) or listed_meta
    med_l = _median(prices)
    avg_l = _mean(prices)
    low_l = min(prices) if prices else None
    sorted_p = sorted(prices)
    low5 = _mean(sorted_p[: min(5, len(sorted_p))]) if sorted_p else None
    med_s = _median(sale_prices)
    avg_s = _mean(sale_prices)
    spread = None
    if prices and len(prices) >= 2:
        spread = calculate_spread_risk(min(prices), max(prices))
    gap = None
    if med_s and floor_ton > 0:
        gap = (floor_ton - med_s) / med_s * 100.0

    velocity = calculate_liquidity_velocity(len(sales), max(listing_count, 1))
    depth = calculate_market_depth(prices, floor_ton) if floor_ton > 0 else 0.0
    vol = min(100.0, _stdev(sale_prices + prices) / max(floor_ton or 1.0, 1.0) * 50.0) if (sale_prices or prices) else 0.0

    liq = 40.0
    liq += min(35.0, len(sales) * 3.5)
    liq += min(15.0, velocity * 200.0)
    liq += min(10.0, depth / 10.0)
    if listing_count > 30 and len(sales) < 3:
        warnings.append("Много листингов при малых продажах — риск неликвидности.")
        liq -= 15
    if not sales:
        warnings.append("Нет недавних продаж — не разгоняйте confidence только от floor.")
        liq -= 12
    liq = max(5.0, min(100.0, liq))

    stab, stab_w = calculate_floor_stability(floor_ton, low_l, med_l)
    warnings.extend(stab_w)

    if low_l and floor_ton > 0 and low_l < floor_ton * 0.88:
        warnings.append("Самые дешёвые листинги заметно ниже floor — возможен нестабильный опорный уровень.")

    return CollectionMarketProfile(
        collection=collection,
        collection_floor_ton=floor_ton,
        median_listing_price_ton=med_l,
        average_listing_price_ton=avg_l,
        lowest_listing_price_ton=low_l,
        lowest_5_avg_price_ton=low5,
        listing_count=listing_count,
        listing_depth_score=depth,
        recent_sales_count=len(sales),
        median_sale_price_ton=med_s,
        average_sale_price_ton=avg_s,
        floor_to_sale_gap_percent=gap,
        spread_percent=spread,
        liquidity_score=liq,
        volatility_score=vol,
        floor_stability_score=stab,
        source_quality=source_quality,
        freshness_label=freshness_label,
        warnings=warnings,
    )


def build_trait_market_profile(
    collection: str,
    trait_type: str,
    trait_value: str,
    trait_floor_ton: float | None,
    coll: CollectionMarketProfile,
    listings: list[ListingSchema],
    sales: list[SaleSchema],
    rarity_percent: float | None,
    settings: Settings,
) -> TraitMarketProfile:
    warnings: list[str] = []
    t_listings = [l for l in listings if _listing_matches_trait(l, trait_type, trait_value)]
    t_sales = [s for s in sales if sale_matches_trait(s, trait_type, trait_value)]
    t_prices = [float(l.price_ton) for l in t_listings]
    s_prices = [float(s.price_ton) for s in t_sales]
    med_sale = _median(s_prices)
    avg_sale = _mean(s_prices)
    prem = calculate_trait_premium(trait_floor_ton, coll.collection_floor_ton)
    sale_vs = None
    if med_sale and coll.median_sale_price_ton:
        sale_vs = (med_sale - coll.median_sale_price_ton) / coll.median_sale_price_ton * 100.0

    if prem and prem > 35 and not t_sales:
        warnings.append("Возможный «фейковый» премиум: trait floor сильно выше коллекции, но продаж по trait нет.")

    prem_score = 0.0
    if med_sale and coll.median_sale_price_ton and sale_vs and sale_vs > 8:
        prem_score = min(100.0, 40 + sale_vs)
    elif prem and prem > 15 and t_sales:
        prem_score = min(80.0, 30 + prem * 0.5)
    elif prem and prem > 15 and not t_sales:
        prem_score = min(35.0, 15 + prem * 0.2)

    t_liq = 50.0 + min(40.0, len(t_sales) * 5) + min(10.0, len(t_listings) * 2)
    if not t_sales:
        t_liq -= 20
    t_liq = max(5.0, min(100.0, t_liq))

    overpay = max(0.0, 100.0 - t_liq * 0.6 + (10 if detect_overpriced_trait(
        TraitMarketProfile(
            collection=collection,
            trait_type=trait_type,
            trait_value=trait_value,
            trait_floor_ton=trait_floor_ton,
            trait_listing_count=len(t_listings),
            trait_recent_sales_count=len(t_sales),
        )
    ) else 0))

    underval = 0.0
    if med_sale and trait_floor_ton and trait_floor_ton < med_sale * 0.92:
        underval = min(100.0, (med_sale - trait_floor_ton) / med_sale * 80.0)

    trait_sales_coverage = min(100.0, float(len(t_sales)) * 25.0 + float(len(t_listings)) * 5.0)
    trait_sales_recency_label = "none" if not t_sales else "recent"
    trait_sales_confidence = min(100.0, 25.0 + len(t_sales) * 18.0 + len(t_listings) * 4.0)
    if not t_sales:
        trait_sales_confidence = max(0.0, trait_sales_confidence * 0.35)
    trait_premium_confirmed = len(t_sales) > 0

    return TraitMarketProfile(
        collection=collection,
        trait_type=trait_type,
        trait_value=trait_value,
        trait_floor_ton=trait_floor_ton,
        trait_listing_count=len(t_listings),
        trait_recent_sales_count=len(t_sales),
        trait_median_sale_price_ton=med_sale,
        trait_average_sale_price_ton=avg_sale,
        trait_floor_vs_collection_floor_percent=prem,
        trait_sale_vs_collection_sale_percent=sale_vs,
        rarity_percent=rarity_percent,
        trait_premium_score=prem_score,
        trait_liquidity_score=t_liq,
        trait_overpay_risk=min(100.0, overpay),
        trait_undervalued_score=underval,
        trait_sales_coverage=trait_sales_coverage,
        trait_sales_recency_label=trait_sales_recency_label,
        trait_sales_confidence=trait_sales_confidence,
        trait_premium_confirmed=trait_premium_confirmed,
        warnings=warnings,
    )


def format_market_intelligence_report(profile: CollectionMarketProfile) -> str:
    lines = [
        f"📊 Market intel · {profile.collection}",
        f"Floor: {profile.collection_floor_ton:.2f} TON",
        f"Listings: {profile.listing_count} (median {profile.median_listing_price_ton or 'n/a'})",
        f"Sales (sample): {profile.recent_sales_count} (median sale {profile.median_sale_price_ton or 'n/a'})",
        f"Liquidity score: {profile.liquidity_score:.0f}/100",
        f"Spread: {profile.spread_percent or 0:.1f}% · Volatility: {profile.volatility_score:.1f}",
        f"Floor stability: {profile.floor_stability_score:.0f}/100",
        f"Source quality: {profile.source_quality} · Freshness: {profile.freshness_label}",
    ]
    if profile.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {w}" for w in profile.warnings[:8])
    return "\n".join(lines)


async def build_collection_profile_from_source(
    collection: str,
    market_source: MarketSource,
    settings: Settings,
) -> tuple[CollectionMarketProfile, list[ListingSchema], list[SaleSchema], MarketFloor | None]:
    floor = await market_source.get_collection_floor(collection)
    listings = await market_source.get_similar_listings(collection, [], limit=40)
    sales = await market_source.get_recent_sales(collection, limit=40)
    sq = getattr(market_source, "name", "unknown") or "unknown"
    profile = build_collection_market_profile(
        collection,
        floor,
        listings,
        sales,
        settings,
        source_quality=sq,
        freshness_label="unknown",
    )
    return profile, listings, sales, floor


def format_trait_intel_report(profile: TraitMarketProfile) -> str:
    lines = [
        f"🧬 Trait intel · {profile.collection}",
        f"{profile.trait_type}: {profile.trait_value}",
        f"Trait floor: {profile.trait_floor_ton}",
        f"Listings w/ trait (sample): {profile.trait_listing_count} · Sales: {profile.trait_recent_sales_count}",
        f"Median sale (trait): {profile.trait_median_sale_price_ton}",
        f"Premium confirmed (sales): {'yes' if profile.trait_premium_confirmed else 'no'}",
        f"Trait sales coverage: {profile.trait_sales_coverage:.0f}/100 · recency: {profile.trait_sales_recency_label}",
        f"Trait sales confidence: {profile.trait_sales_confidence:.0f}/100",
        f"Premium vs collection floor: {profile.trait_floor_vs_collection_floor_percent}",
        f"Premium vs collection sales: {profile.trait_sale_vs_collection_sale_percent}",
        f"Trait premium score: {profile.trait_premium_score:.0f}/100",
        f"Liquidity: {profile.trait_liquidity_score:.0f}/100",
        f"Overpay risk: {profile.trait_overpay_risk:.0f}/100 · Undervalued score: {profile.trait_undervalued_score:.0f}/100",
    ]
    if profile.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {w}" for w in profile.warnings[:8])
    return "\n".join(str(x) for x in lines)

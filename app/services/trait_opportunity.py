from __future__ import annotations

from app.config import Settings
from app.schemas.gift import GiftAttributeSchema
from app.schemas.market_brain import TraitOpportunity
from app.services.important_traits import score_important_trait_keyword
from app.services.market_cache import TTL_RARE_DEALS, get_cached, set_cached
from app.services.market_intelligence import build_collection_market_profile, sale_matches_trait
from app.sources.base import MarketSource


def detect_trait_floor_gap(
    listing_price: float,
    trait_floor: float | None,
    collection_floor: float,
) -> float | None:
    if trait_floor is None or trait_floor <= 0:
        return None
    return (trait_floor - listing_price) / trait_floor * 100.0


def detect_mispriced_rare_listing(
    listing_price: float,
    trait_floor: float | None,
    trait_median_sale: float | None,
    collection_floor: float,
    *,
    trait_sales_n: int,
    listing_count_trait: int,
    important_score: float,
    liquidity: float,
) -> tuple[float, list[str]]:
    """Returns opportunity_score 0..100 and reasons."""
    reasons: list[str] = []
    score = 20.0
    gap_tf = detect_trait_floor_gap(listing_price, trait_floor, collection_floor)
    if gap_tf is not None and gap_tf > 15:
        score += min(35.0, gap_tf * 0.8)
        reasons.append(f"Лот ниже trait floor примерно на {gap_tf:.0f}%")
    gap_sale = None
    if trait_median_sale and trait_median_sale > 0:
        gap_sale = (trait_median_sale - listing_price) / trait_median_sale * 100.0
        if gap_sale > 10 and trait_sales_n >= 2:
            score += min(30.0, gap_sale * 0.7)
            reasons.append("Цена ниже медианы недавних продаж по trait")
        elif gap_sale > 15 and trait_sales_n == 0:
            score += 5
            reasons.append("Скидка к медиане продаж выглядит крупной, но продаж по trait нет — только спекуляция")

    if important_score > 5:
        score += min(15.0, important_score * 0.5)
        reasons.append("Важный trait (keyword) — повышенное внимание, не автоматический buy")

    score += min(20.0, liquidity * 0.15)

    if trait_sales_n == 0:
        score *= 0.55
        reasons.append("Нет подтверждающих продаж по trait — максимум осторожный сценарий")
    if listing_count_trait <= 1:
        score *= 0.75
        reasons.append("Мало листингов с этим trait — книга заявок тонкая")

    if listing_price > collection_floor * 1.05 and trait_floor and listing_price > trait_floor * 0.95:
        reasons.append("Цена близка к trait floor — арбитража может не быть")

    return max(0.0, min(100.0, score)), reasons


def rank_trait_opportunities(items: list[TraitOpportunity]) -> list[TraitOpportunity]:
    return sorted(items, key=lambda x: x.opportunity_score, reverse=True)


def format_trait_opportunity_report(items: list[TraitOpportunity], limit: int = 10) -> str:
    if not items:
        return "Trait opportunities: подходящих лотов не найдено."
    lines = ["🎯 Trait opportunities:"]
    for idx, o in enumerate(items[:limit], start=1):
        lines.append(
            f"#{idx} {o.collection} #{o.number or '?'} · {o.trait_type}={o.trait_value}\n"
            f"Price {o.listing_price_ton:.2f} TON · score {o.opportunity_score:.0f}\n"
            f"{o.recommendation}\n"
            + ("\n".join(f"- {r}" for r in o.reasons[:4]) if o.reasons else "")
        )
    return "\n\n".join(lines)


async def scan_trait_opportunities(
    collection: str,
    market_source: MarketSource,
    settings: Settings,
    *,
    limit_listings: int = 30,
) -> list[TraitOpportunity]:
    sname = getattr(market_source, "name", "unknown") or "unknown"
    ckey = collection.strip().lower()
    cached = get_cached(ckey, sname, "rare_deals")
    if cached is not None:
        return list(cached)

    from app.services.market_data_validity import filter_mock_listings_for_production

    floor = await market_source.get_collection_floor(collection)
    listings = await market_source.search_underpriced(collection, filters={})
    listings = filter_mock_listings_for_production(settings, list(listings))
    sales = await market_source.get_recent_sales(collection, limit=40)
    depth_listings = await market_source.get_similar_listings(collection, [], limit=40)
    coll_profile = build_collection_market_profile(
        collection,
        floor,
        depth_listings,
        sales,
        settings,
        source_quality=getattr(market_source, "name", "unknown") or "unknown",
    )
    opportunities: list[TraitOpportunity] = []
    for listing in listings[:limit_listings]:
        attrs_raw = listing.attributes_json.get("attributes") or listing.attributes_json.get("traits") or []
        if isinstance(attrs_raw, dict):
            attrs_raw = [attrs_raw]
        attrs: list[GiftAttributeSchema] = []
        for a in attrs_raw:
            if not isinstance(a, dict):
                continue
            tt = str(a.get("trait_type") or a.get("type") or "")
            tv = str(a.get("trait_value") or a.get("value") or "")
            if tt and tv:
                attrs.append(GiftAttributeSchema(trait_type=tt, trait_value=tv))
        if not attrs:
            continue
        best_opp: TraitOpportunity | None = None
        for attr in attrs:
            tf = await market_source.get_trait_floor(collection, attr.trait_type, attr.trait_value)
            trait_floor_ton = tf.floor_ton if tf else None
            t_sales = [s for s in sales if sale_matches_trait(s, attr.trait_type, attr.trait_value)]
            trait_sales_prices = [float(s.price_ton) for s in t_sales]
            trait_sales_n = len(trait_sales_prices)
            med_sale = None
            if trait_sales_prices:
                med_sale = float(sorted(trait_sales_prices)[len(trait_sales_prices) // 2])
            imp = score_important_trait_keyword(attr.trait_type, attr.trait_value, settings)
            score, reasons = detect_mispriced_rare_listing(
                listing.price_ton,
                trait_floor_ton,
                med_sale,
                coll_profile.collection_floor_ton or (floor.floor_ton if floor else 0),
                trait_sales_n=trait_sales_n,
                listing_count_trait=1,
                important_score=imp,
                liquidity=coll_profile.liquidity_score,
            )
            if trait_floor_ton is None and imp < 4:
                continue
            if score < 28 and imp < 8:
                continue
            rec = "Рассмотреть как trait-arb" if score >= 55 and trait_sales_n >= 2 else (
                "Спекулятивно" if score >= 35 else "Слабый сигнал"
            )
            opp = TraitOpportunity(
                collection=listing.collection,
                number=listing.number,
                trait_type=attr.trait_type,
                trait_value=attr.trait_value,
                listing_price_ton=listing.price_ton,
                collection_floor_ton=float(floor.floor_ton) if floor else 0.0,
                trait_floor_ton=trait_floor_ton,
                trait_recent_sale_median_ton=med_sale,
                discount_to_trait_floor_percent=detect_trait_floor_gap(
                    listing.price_ton, trait_floor_ton, coll_profile.collection_floor_ton
                ),
                discount_to_trait_sales_percent=(
                    (med_sale - listing.price_ton) / med_sale * 100.0 if med_sale and med_sale > 0 else None
                ),
                rarity_score=min(100.0, imp * 2 + score * 0.2),
                liquidity_score=coll_profile.liquidity_score,
                confidence_score=min(90.0, 40 + trait_sales_n * 8 + (10 if imp else 0)),
                risk_score=100 - coll_profile.liquidity_score,
                opportunity_score=score,
                recommendation=rec,
                reasons=reasons,
                source_url=listing.url,
            )
            if best_opp is None or opp.opportunity_score > best_opp.opportunity_score:
                best_opp = opp
        if best_opp:
            if best_opp.trait_recent_sale_median_ton is None and (best_opp.trait_floor_ton or 0) > 0:
                best_opp = best_opp.model_copy(
                    update={
                        "opportunity_score": min(best_opp.opportunity_score, 50.0),
                        "recommendation": "Спекулятивно — нет подтверждающих продаж по trait",
                    }
                )
            opportunities.append(best_opp)
    ranked = rank_trait_opportunities(opportunities)
    set_cached(ckey, sname, "rare_deals", ranked, TTL_RARE_DEALS)
    return ranked

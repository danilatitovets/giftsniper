from __future__ import annotations

from app.schemas.gift import GiftAttributeSchema
from app.schemas.market_brain import RarityTraitProfile, TraitMarketProfile


def rarity_score(attributes: list[GiftAttributeSchema]) -> float:
    values = [a.rarity_percent for a in attributes if a.rarity_percent is not None]
    if not values:
        return 0.0
    score = 0.0
    for rarity in values:
        score += max(0.0, (5.0 - rarity) / 5.0)
    return score / len(values)


def detect_fake_rarity(profile: RarityTraitProfile) -> bool:
    return profile.is_fake_rarity


def detect_rare_but_illiquid(profile: RarityTraitProfile) -> bool:
    return profile.is_rare_but_illiquid


def calculate_trait_rarity_profile(
    attr: GiftAttributeSchema,
    trait_market: TraitMarketProfile | None,
    collection_floor: float,
    *,
    important_bonus: float = 0.0,
) -> RarityTraitProfile:
    rarity_pct = attr.rarity_percent
    base = 0.0
    if rarity_pct is not None:
        base = max(0.0, min(1.0, (5.0 - rarity_pct) / 5.0)) * 100.0

    floor_prem = trait_market.trait_floor_vs_collection_floor_percent if trait_market else None
    sale_prem = None
    if trait_market and trait_market.trait_median_sale_price_ton and collection_floor > 0:
        sale_prem = (trait_market.trait_median_sale_price_ton - collection_floor) / collection_floor * 100.0

    liq = trait_market.trait_liquidity_score if trait_market else 30.0
    sales_n = trait_market.trait_recent_sales_count if trait_market else 0
    list_n = trait_market.trait_listing_count if trait_market else 0

    rarity_score_val = base * 0.6
    if floor_prem and floor_prem > 10:
        rarity_score_val += min(25.0, floor_prem * 0.35)
    if sale_prem and sale_prem > 5 and sales_n >= 2:
        rarity_score_val += min(30.0, sale_prem * 0.4)
    rarity_score_val += min(10.0, important_bonus * 0.3)
    rarity_score_val = max(0.0, min(100.0, rarity_score_val))

    liq_adj = rarity_score_val * (0.45 + 0.55 * (liq / 100.0))
    if sales_n == 0:
        liq_adj *= 0.55
    liq_adj = max(0.0, min(100.0, liq_adj))

    is_fake = False
    flags: list[str] = []
    if base > 55 and sales_n == 0 and (not trait_market or trait_market.trait_floor_ton):
        is_fake = True
        flags.append("Редкость по метаданным без продаж — не усиливать цену.")
    if trait_market and trait_market.trait_floor_ton and sales_n == 0 and list_n > 3:
        cheap_hint = trait_market.trait_listing_count >= 3
        if cheap_hint:
            flags.append("Много листингов по trait при отсутствии продаж — слабый rarity-сигнал.")
            liq_adj *= 0.85

    rare_illiquid = base > 50 and sales_n < 2 and liq < 45

    return RarityTraitProfile(
        trait_type=attr.trait_type,
        trait_value=attr.trait_value,
        rarity_percent=rarity_pct,
        supply_count=None,
        listing_count=list_n or None,
        sale_count=sales_n or None,
        floor_premium_percent=floor_prem,
        sale_premium_percent=sale_prem,
        rarity_score=round(rarity_score_val, 2),
        liquidity_adjusted_rarity_score=round(liq_adj, 2),
        is_important_trait=important_bonus > 0,
        is_fake_rarity=is_fake,
        is_rare_but_illiquid=rare_illiquid,
        warning_flags=flags,
    )


def calculate_combined_rarity_score(
    attributes: list[GiftAttributeSchema],
    trait_profiles: list[RarityTraitProfile],
) -> tuple[float, float]:
    if not trait_profiles:
        return 0.0, 0.0
    raw = sum(p.rarity_score for p in trait_profiles) / len(trait_profiles)
    adj = sum(p.liquidity_adjusted_rarity_score for p in trait_profiles) / len(trait_profiles)
    combined_raw = min(100.0, raw * (1.0 + 0.08 * max(0, len(trait_profiles) - 1)))
    combined_adj = min(100.0, adj * (1.0 + 0.05 * max(0, len(trait_profiles) - 1)))
    if any(p.is_rare_but_illiquid for p in trait_profiles):
        combined_adj *= 0.82
    return round(combined_raw, 2), round(combined_adj, 2)


def detect_rare_traits(
    attributes: list[GiftAttributeSchema],
    trait_profiles: list[RarityTraitProfile],
) -> list[RarityTraitProfile]:
    return [p for p in trait_profiles if p.rarity_score >= 45 or (p.rarity_percent is not None and p.rarity_percent < 2.0)]


def format_rarity_breakdown(trait_profiles: list[RarityTraitProfile]) -> str:
    if not trait_profiles:
        return "Rarity: нет профилей по traits."
    lines = ["Rarity traits:"]
    for p in trait_profiles[:6]:
        tag = "strong" if p.liquidity_adjusted_rarity_score >= 55 and p.sale_count and p.sale_count >= 2 else (
            "speculative" if p.is_fake_rarity or p.is_rare_but_illiquid or not p.sale_count else "weak"
        )
        lines.append(
            f"- {p.trait_type}: {p.trait_value} — {tag} "
            f"(score {p.liquidity_adjusted_rarity_score:.0f}, sales {p.sale_count or 0})"
        )
    return "\n".join(lines)

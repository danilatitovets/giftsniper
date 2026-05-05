"""Pydantic models for Stage 30: market intelligence, precision pricing, decisions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DecisionType = Literal[
    "STRONG_BUY",
    "BUY_IF_UNDER",
    "SPECULATIVE_BUY",
    "HOLD",
    "LIST_NOW",
    "LIST_HIGH",
    "QUICK_SELL",
    "AVOID",
    "NEED_MORE_DATA",
]


class CollectionMarketProfile(BaseModel):
    collection: str
    collection_floor_ton: float
    median_listing_price_ton: float | None = None
    average_listing_price_ton: float | None = None
    lowest_listing_price_ton: float | None = None
    lowest_5_avg_price_ton: float | None = None
    listing_count: int = 0
    listing_depth_score: float = 0.0
    recent_sales_count: int = 0
    median_sale_price_ton: float | None = None
    average_sale_price_ton: float | None = None
    floor_to_sale_gap_percent: float | None = None
    spread_percent: float | None = None
    liquidity_score: float = 0.0
    volatility_score: float = 0.0
    floor_stability_score: float = 0.0
    source_quality: str = "unknown"
    freshness_label: str = "unknown"
    warnings: list[str] = Field(default_factory=list)


class TraitMarketProfile(BaseModel):
    collection: str
    trait_type: str
    trait_value: str
    trait_floor_ton: float | None = None
    trait_listing_count: int = 0
    trait_recent_sales_count: int = 0
    trait_median_sale_price_ton: float | None = None
    trait_average_sale_price_ton: float | None = None
    trait_floor_vs_collection_floor_percent: float | None = None
    trait_sale_vs_collection_sale_percent: float | None = None
    rarity_percent: float | None = None
    trait_premium_score: float = 0.0
    trait_liquidity_score: float = 0.0
    trait_overpay_risk: float = 0.0
    trait_undervalued_score: float = 0.0
    trait_sales_coverage: float = 0.0
    trait_sales_recency_label: str = "none"
    trait_sales_confidence: float = 0.0
    trait_premium_confirmed: bool = False
    warnings: list[str] = Field(default_factory=list)


class RarityTraitProfile(BaseModel):
    trait_type: str
    trait_value: str
    rarity_percent: float | None = None
    supply_count: int | None = None
    listing_count: int | None = None
    sale_count: int | None = None
    floor_premium_percent: float | None = None
    sale_premium_percent: float | None = None
    rarity_score: float = 0.0
    liquidity_adjusted_rarity_score: float = 0.0
    is_important_trait: bool = False
    is_fake_rarity: bool = False
    is_rare_but_illiquid: bool = False
    warning_flags: list[str] = Field(default_factory=list)


class PrecisionPricePlan(BaseModel):
    safe_buy_price_ton: float
    max_buy_price_ton: float
    aggressive_buy_price_ton: float
    quick_flip_list_price_ton: float
    normal_list_price_ton: float
    high_list_price_ton: float
    quick_sell_price_ton: float
    stop_loss_price_ton: float
    downside_price_ton: float
    upside_price_ton: float
    expected_net_sale_ton: float
    expected_net_profit_ton: float
    expected_roi_percent: float
    marketplace_fee_percent: float
    estimated_extra_costs_ton: float
    time_to_sell_estimate: str = ""
    confidence_score: float = 0.0
    risk_score: float = 0.0
    liquidity_score: float = 0.0
    recommendation: str = ""
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DecisionResult(BaseModel):
    decision: DecisionType
    action_label_ru: str
    max_buy_price_ton: float | None = None
    safe_buy_price_ton: float | None = None
    list_price_ton: float | None = None
    quick_sell_price_ton: float | None = None
    stop_loss_price_ton: float | None = None
    confidence_score: float = 0.0
    risk_score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class TraitOpportunity(BaseModel):
    collection: str
    number: int | None = None
    nft_address: str | None = None
    trait_type: str
    trait_value: str
    listing_price_ton: float
    collection_floor_ton: float
    trait_floor_ton: float | None = None
    trait_recent_sale_median_ton: float | None = None
    discount_to_trait_floor_percent: float | None = None
    discount_to_trait_sales_percent: float | None = None
    rarity_score: float = 0.0
    liquidity_score: float = 0.0
    confidence_score: float = 0.0
    risk_score: float = 0.0
    opportunity_score: float = 0.0
    recommendation: str = ""
    reasons: list[str] = Field(default_factory=list)
    source_url: str | None = None

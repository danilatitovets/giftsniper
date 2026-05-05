from typing import Literal

from pydantic import BaseModel, Field


class OpportunityScore(BaseModel):
    total_score: int
    roi_score: int
    profit_score: int
    liquidity_score: int
    confidence_score: int
    freshness_score: int
    risk_penalty: int
    source_quality_score: int
    final_rank_label: str
    breakdown: list[str] = Field(default_factory=list)


class CapitalPlanItem(BaseModel):
    collection: str
    number: int
    price_ton: float
    tier: str
    score: int
    allocated_ton: float
    reason: str


class CapitalPlan(BaseModel):
    bankroll_ton: float
    reserve_ton: float
    available_ton: float
    max_per_deal_ton: float
    max_per_collection_ton: float
    selected_opportunities: list[CapitalPlanItem] = Field(default_factory=list)
    skipped_opportunities: list[CapitalPlanItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    expected_profit_ton: float = 0.0
    expected_roi_percent: float = 0.0
    downside_scenario_ton: dict[str, float] = Field(default_factory=dict)


class MarketRegime(BaseModel):
    regime: str
    score: int
    liquidity_score: int
    sales_activity_score: int
    freshness_score: int
    source_quality_score: int
    opportunity_quality_score: int
    risk_score: int
    warnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class CollectionIntelligence(BaseModel):
    collection: str
    regime: str
    relative_strength_score: int
    avg_opportunity_score: int
    best_opportunity_score: int
    liquidity_score: int
    freshness_label: str
    real_data_available: bool
    manual_data_available: bool
    recent_sales_count: int
    warnings: list[str] = Field(default_factory=list)
    recommendation: str


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

PricingSourceLabel = Literal["real", "manual", "mock", "unavailable", "mixed"]


class SourcePricingContext(BaseModel):
    pricing_source: PricingSourceLabel = "unavailable"
    metadata_source: str = "unknown"
    market_source_names: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FlipAnalysisResult(BaseModel):
    buy_zone_min_ton: float
    buy_zone_max_ton: float
    quick_sell_price_ton: float
    fair_price_ton: float
    list_price_ton: float
    optimistic_price_ton: float
    stop_price_ton: float
    marketplace_fee_percent: float
    expected_net_sale_ton: float
    expected_profit_ton: float
    expected_roi_percent: float
    liquidity_score: int
    risk_score: int
    confidence_score: int
    recommendation: str
    roi_based_on_estimated_buy_zone: bool = False
    reasons: list[str] = Field(default_factory=list)
    opportunity_score: OpportunityScore | None = None
    safe_buy_price_ton: float | None = None
    aggressive_buy_price_ton: float | None = None
    quick_flip_list_price_ton: float | None = None
    normal_list_price_ton: float | None = None
    high_list_price_ton: float | None = None
    downside_price_ton: float | None = None
    upside_price_ton: float | None = None
    time_to_sell_estimate: str | None = None
    decision_type: DecisionType | None = None
    decision_summary: str | None = None
    rarity_score: float | None = None
    liquidity_adjusted_rarity_score: float | None = None
    trait_opportunity_score: float | None = None
    max_trait_recent_sales: int | None = None
    market_intelligence_json: str | None = None
    precision_plan_json: str | None = None
    decision_json: str | None = None
    pricing_suppressed: bool = False
    market_validity_message_ru: str | None = None
    price_source_label: str | None = None
    source_pricing_context: SourcePricingContext | None = None


PriceEstimate = FlipAnalysisResult

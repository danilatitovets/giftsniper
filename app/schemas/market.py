from datetime import datetime, timezone

from pydantic import BaseModel, Field


class DataFreshness(BaseModel):
    floor_age_minutes: int | None = None
    trait_floor_age_minutes: int | None = None
    listings_age_minutes: int | None = None
    sales_age_minutes: int | None = None
    freshness_label: str = "unknown"
    confidence_penalty: int = 0
    warnings: list[str] = Field(default_factory=list)


class MarketFloor(BaseModel):
    collection: str
    source: str
    floor_ton: float
    volume_24h_ton: float | None = None
    listed_count: int | None = None
    created_at: datetime | None = None


class ListingSchema(BaseModel):
    external_id: str
    source: str
    collection: str
    number: int
    price_ton: float
    url: str
    image_url: str | None = None
    attributes_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SaleSchema(BaseModel):
    external_id: str
    source: str
    collection: str
    number: int
    price_ton: float
    sold_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attributes_json: dict = Field(default_factory=dict)


class MarketDataQuality(BaseModel):
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
    confidence_penalty: int = 0
    warnings: list[str] = Field(default_factory=list)
    is_mock_data: bool = False
    is_partial_data: bool = False
    data_freshness: DataFreshness | None = None

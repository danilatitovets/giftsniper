from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import ListingSchema, MarketDataQuality, MarketFloor, SaleSchema


class MarketSource(ABC):
    name: str = "base"
    last_quality: MarketDataQuality | None = None

    @abstractmethod
    async def get_collection_floor(self, collection: str) -> MarketFloor | None:
        raise NotImplementedError

    @abstractmethod
    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str) -> MarketFloor | None:
        raise NotImplementedError

    @abstractmethod
    async def get_recent_sales(self, collection: str, limit: int = 20) -> list[SaleSchema]:
        raise NotImplementedError

    @abstractmethod
    async def get_similar_listings(
        self, collection: str, attributes: list[GiftAttributeSchema], limit: int = 20
    ) -> list[ListingSchema]:
        raise NotImplementedError

    @abstractmethod
    async def search_underpriced(self, collection: str, filters: dict) -> list[ListingSchema]:
        raise NotImplementedError

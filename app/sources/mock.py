from __future__ import annotations

from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import ListingSchema, MarketFloor, SaleSchema
from app.sources.base import MarketSource


class MockMarketSource(MarketSource):
    name = "mock"

    async def get_collection_floor(self, collection: str) -> MarketFloor | None:
        if collection.lower() != "ice cream":
            return MarketFloor(collection=collection, source=self.name, floor_ton=120.0, listed_count=80)
        return MarketFloor(collection="Ice Cream", source=self.name, floor_ton=186.0, listed_count=134)

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str) -> MarketFloor | None:
        key = f"{trait_type}:{trait_value}".lower()
        trait_floors = {
            "symbol:moon": 240.0,
            "backdrop:ivory white": 220.0,
            "model:vice dream": 210.0,
        }
        floor = trait_floors.get(key)
        if floor is None:
            return None
        return MarketFloor(collection=collection, source=self.name, floor_ton=floor)

    async def get_recent_sales(self, collection: str, limit: int = 20) -> list[SaleSchema]:
        data = [190, 198, 205, 221, 235, 242, 250]
        return [
            SaleSchema(
                external_id=f"mock_sale_{i}",
                source=self.name,
                collection=collection,
                number=217000 + i,
                price_ton=price,
            )
            for i, price in enumerate(data[:limit], 1)
        ]

    async def get_similar_listings(
        self, collection: str, attributes: list[GiftAttributeSchema], limit: int = 20
    ) -> list[ListingSchema]:
        data = [220, 228, 239, 251, 267, 280]
        return [
            ListingSchema(
                external_id=f"mock_listing_{i}",
                source=self.name,
                collection=collection,
                number=217460 + i,
                price_ton=price,
                url=f"https://mock.market/{collection}/{217460+i}",
            )
            for i, price in enumerate(data[:limit], 1)
        ]

    async def search_underpriced(self, collection: str, filters: dict) -> list[ListingSchema]:
        return [
            ListingSchema(
                external_id="mock_flip_1",
                source=self.name,
                collection=collection,
                number=219999,
                price_ton=170.0,
                url=f"https://mock.market/{collection}/219999",
                attributes_json={"Symbol": "Moon"},
            )
        ]

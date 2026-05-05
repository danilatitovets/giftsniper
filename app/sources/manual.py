from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db.models import Listing, MarketSnapshot, Sale, TraitFloor
from app.db.session import SessionLocal
from app.config import get_settings
from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import DataFreshness, ListingSchema, MarketDataQuality, MarketFloor, SaleSchema
from app.sources.base import MarketSource


class ManualSource(MarketSource):
    name = "Manual"

    def __init__(self, user_id: int | None) -> None:
        self.user_id = user_id
        self.settings = get_settings()
        self.last_quality = MarketDataQuality(
            sources_used=[self.name],
            warnings=["Используются ручные рыночные данные"],
            confidence_penalty=10,
            is_mock_data=False,
            is_partial_data=True,
        )

    def _age_minutes(self, dt: datetime | None) -> int | None:
        if dt is None:
            return None
        now = datetime.now(timezone.utc)
        source_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return max(0, int((now - source_dt).total_seconds() // 60))

    def _freshness_label(self, age_minutes: int | None) -> str:
        if age_minutes is None:
            return "unknown"
        if age_minutes <= self.settings.fresh_floor_max_minutes:
            return "fresh"
        if age_minutes <= self.settings.stale_floor_max_minutes:
            return "stale"
        return "old"

    def _quality_with_freshness(
        self,
        floor_age: int | None = None,
        trait_age: int | None = None,
        listings_age: int | None = None,
        sales_age: int | None = None,
    ) -> None:
        warnings = ["Используются ручные рыночные данные"]
        penalty = 10
        floor_label = self._freshness_label(floor_age)
        trait_label = self._freshness_label(trait_age)
        sales_label = self._freshness_label(sales_age)
        if floor_label == "fresh":
            warnings.append("Manual floor свежий")
        elif floor_label in {"stale", "old"}:
            warnings.append("Manual floor устарел")
            penalty += 8 if floor_label == "stale" else 15
        if trait_label in {"stale", "old"}:
            warnings.append("Manual trait floor устарел")
            penalty += 6 if trait_label == "stale" else 10
        if sales_age is not None and sales_age > self.settings.recent_sales_max_days * 24 * 60:
            warnings.append("Manual sales старые")
            penalty += 8
        label = "unknown"
        labels = [x for x in [floor_label, trait_label, self._freshness_label(listings_age), sales_label] if x != "unknown"]
        if "old" in labels:
            label = "old"
        elif "stale" in labels:
            label = "stale"
        elif "fresh" in labels:
            label = "fresh"
        freshness = DataFreshness(
            floor_age_minutes=floor_age,
            trait_floor_age_minutes=trait_age,
            listings_age_minutes=listings_age,
            sales_age_minutes=sales_age,
            freshness_label=label,
            confidence_penalty=penalty,
            warnings=warnings,
        )
        self.last_quality = MarketDataQuality(
            sources_used=[self.name],
            warnings=warnings,
            confidence_penalty=min(35, penalty),
            is_mock_data=False,
            is_partial_data=True,
            data_freshness=freshness,
        )

    async def get_collection_floor(self, collection: str) -> MarketFloor | None:
        if self.user_id is None:
            return None
        async with SessionLocal() as session:
            stmt = (
                select(MarketSnapshot)
                .where(
                    MarketSnapshot.user_id == self.user_id,
                    MarketSnapshot.source == "Manual",
                    MarketSnapshot.collection == collection,
                )
                .order_by(MarketSnapshot.created_at.desc())
                .limit(1)
            )
            row = await session.scalar(stmt)
        if row is None:
            return None
        self._quality_with_freshness(floor_age=self._age_minutes(row.created_at))
        return MarketFloor(
            collection=row.collection,
            source=self.name,
            floor_ton=row.floor_ton,
            volume_24h_ton=row.volume_24h_ton,
            listed_count=row.listed_count,
            created_at=row.created_at,
        )

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str) -> MarketFloor | None:
        if self.user_id is None:
            return None
        async with SessionLocal() as session:
            stmt = (
                select(TraitFloor)
                .where(
                    TraitFloor.user_id == self.user_id,
                    TraitFloor.source == "Manual",
                    TraitFloor.collection == collection,
                    TraitFloor.trait_type == trait_type,
                    TraitFloor.trait_value == trait_value,
                )
                .order_by(TraitFloor.created_at.desc())
                .limit(1)
            )
            row = await session.scalar(stmt)
        if row is None:
            return None
        self._quality_with_freshness(trait_age=self._age_minutes(row.created_at))
        return MarketFloor(collection=row.collection, source=self.name, floor_ton=row.floor_ton, created_at=row.created_at)

    async def get_recent_sales(self, collection: str, limit: int = 20) -> list[SaleSchema]:
        if self.user_id is None:
            return []
        async with SessionLocal() as session:
            stmt = (
                select(Sale)
                .where(Sale.user_id == self.user_id, Sale.source == "Manual", Sale.collection == collection)
                .order_by(Sale.sold_at.desc())
                .limit(limit)
            )
            rows = list((await session.scalars(stmt)).all())
        self._quality_with_freshness(sales_age=self._age_minutes(rows[0].sold_at) if rows else None)
        return [
            SaleSchema(
                external_id=row.external_id,
                source=self.name,
                collection=row.collection,
                number=row.number,
                price_ton=row.price_ton,
                sold_at=row.sold_at,
                attributes_json=row.attributes_json or {},
            )
            for row in rows
        ]

    async def get_similar_listings(
        self, collection: str, attributes: list[GiftAttributeSchema], limit: int = 20
    ) -> list[ListingSchema]:
        if self.user_id is None:
            return []
        async with SessionLocal() as session:
            stmt = (
                select(Listing)
                .where(Listing.user_id == self.user_id, Listing.source == "Manual", Listing.collection == collection)
                .order_by(Listing.price_ton.asc())
                .limit(limit)
            )
            rows = list((await session.scalars(stmt)).all())
        self._quality_with_freshness(listings_age=self._age_minutes(rows[0].created_at) if rows else None)
        return [
            ListingSchema(
                external_id=row.external_id,
                source=self.name,
                collection=row.collection,
                number=row.number,
                price_ton=row.price_ton,
                url=row.url,
                image_url=row.image_url,
                attributes_json=row.attributes_json or {},
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def search_underpriced(self, collection: str, filters: dict) -> list[ListingSchema]:
        return await self.get_similar_listings(collection, attributes=[], limit=int(filters.get("limit", 20)))

    async def clear_collection_data(self, collection: str) -> None:
        if self.user_id is None:
            return
        async with SessionLocal() as session:
            await session.execute(
                delete(MarketSnapshot).where(
                    MarketSnapshot.user_id == self.user_id,
                    MarketSnapshot.source == "Manual",
                    MarketSnapshot.collection == collection,
                )
            )
            await session.execute(
                delete(TraitFloor).where(
                    TraitFloor.user_id == self.user_id,
                    TraitFloor.source == "Manual",
                    TraitFloor.collection == collection,
                )
            )
            await session.execute(
                delete(Sale).where(Sale.user_id == self.user_id, Sale.source == "Manual", Sale.collection == collection)
            )
            await session.execute(
                delete(Listing).where(Listing.user_id == self.user_id, Listing.source == "Manual", Listing.collection == collection)
            )
            await session.commit()

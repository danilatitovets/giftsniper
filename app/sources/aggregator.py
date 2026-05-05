from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import ListingSchema, MarketDataQuality, MarketFloor, SaleSchema
from app.sources.base import MarketSource

logger = logging.getLogger(__name__)


class MarketSourceAggregator(MarketSource):
    name = "aggregator"

    def __init__(self, sources: list[MarketSource], fallback_source: MarketSource | None = None) -> None:
        self.sources = sources
        self.fallback_source = fallback_source
        self.last_quality = MarketDataQuality()

    def _append_source_quality(self, source: MarketSource, warnings: list[str], failed: list[str]) -> None:
        quality = getattr(source, "last_quality", None)
        if quality is None:
            return
        warnings.extend(quality.warnings)
        for item in quality.sources_failed:
            if item not in failed:
                failed.append(item)

    def _quality(self, used: list[str], failed: list[str], warnings: list[str]) -> MarketDataQuality:
        warning_set = list(dict.fromkeys(warnings))
        real_used = [s for s in used if s.lower() != "mock"]
        penalty = 0
        if failed:
            penalty += 12
        if len(used) <= 1:
            penalty += 8
        if "Используются mock-данные" in warning_set:
            penalty += 20
        if "Часть источников недоступна" in warning_set:
            penalty += 10
        if not real_used:
            penalty += 12
        elif len(real_used) >= 2:
            penalty = max(0, penalty - 5)
        quality = MarketDataQuality(
            sources_used=used,
            sources_failed=failed,
            confidence_penalty=min(50, penalty),
            warnings=warning_set,
            is_mock_data=any(src == "mock" for src in used),
            is_partial_data=bool(failed) or len(used) <= 1,
        )
        self.last_quality = quality
        return quality

    def _age_minutes(self, dt: datetime | None) -> int | None:
        if dt is None:
            return None
        now = datetime.now(timezone.utc)
        source_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return max(0, int((now - source_dt).total_seconds() // 60))

    def _freshness_label(self, age_minutes: int | None) -> str:
        if age_minutes is None:
            return "unknown"
        if age_minutes < 60:
            return "fresh"
        if age_minutes <= 720:
            return "stale"
        return "old"

    def _source_priority(self, source_name: str, freshness: str) -> int:
        lower = source_name.lower()
        if lower == "getgems" and freshness == "fresh":
            return 0
        if lower == "manual" and freshness == "fresh":
            return 1
        if lower == "getgems" and freshness in {"stale", "unknown"}:
            return 2
        if lower == "manual" and freshness in {"stale", "unknown"}:
            return 3
        if lower == "mock":
            return 5
        return 4

    async def _fallback_floor(self, collection: str, warnings: list[str]) -> MarketFloor | None:
        if self.fallback_source is None:
            return None
        warnings.append("Используются mock-данные")
        warnings.append("Часть источников недоступна")
        return await self.fallback_source.get_collection_floor(collection)

    async def get_collection_floor(self, collection: str) -> MarketFloor | None:
        floors: list[MarketFloor] = []
        used: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        for source in self.sources:
            try:
                item = await source.get_collection_floor(collection)
                self._append_source_quality(source, warnings, failed)
                if item is not None:
                    floors.append(item)
                    used.append(source.name)
            except Exception as exc:
                failed.append(source.name)
                logger.warning("Source %s failed for collection floor: %s", source.name, exc)
        if not floors:
            floor = await self._fallback_floor(collection, warnings)
            if floor is None:
                self._quality(used, failed, warnings)
                return None
            used.append(self.fallback_source.name)
            self._quality(used, failed, warnings)
            return floor
        best = min(
            floors,
            key=lambda x: (
                self._source_priority(x.source, self._freshness_label(self._age_minutes(x.created_at))),
                x.floor_ton,
            ),
        )
        spread = max(x.floor_ton for x in floors) - min(x.floor_ton for x in floors)
        if spread > max(10.0, best.floor_ton * 0.12):
            warnings.append("Большой разброс floor между источниками")
        if failed:
            warnings.append("Часть источников недоступна")
        if any(src == "mock" for src in used):
            warnings.append("Используются mock-данные")
        if self._freshness_label(self._age_minutes(best.created_at)) in {"stale", "old"}:
            warnings.append("Выбранный floor не свежий")
        self._quality(used, failed, warnings)
        return best

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str) -> MarketFloor | None:
        floors: list[MarketFloor] = []
        used: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        for source in self.sources:
            try:
                item = await source.get_trait_floor(collection, trait_type, trait_value)
                self._append_source_quality(source, warnings, failed)
                if item is not None:
                    floors.append(item)
                    used.append(source.name)
            except Exception as exc:
                failed.append(source.name)
                logger.warning("Source %s failed for trait floor: %s", source.name, exc)
        if not floors and self.fallback_source is not None:
            warnings.append("Используются mock-данные")
            floor = await self.fallback_source.get_trait_floor(collection, trait_type, trait_value)
            if floor is not None:
                used.append(self.fallback_source.name)
                self._quality(used, failed, warnings)
                return floor
        if not floors:
            self._quality(used, failed, warnings)
            return None
        best = min(
            floors,
            key=lambda x: (
                self._source_priority(x.source, self._freshness_label(self._age_minutes(x.created_at))),
                x.floor_ton,
            ),
        )
        if len(floors) == 1:
            warnings.append("Trait floor найден только в одном источнике")
        if failed:
            warnings.append("Часть источников недоступна")
        if any(src == "mock" for src in used):
            warnings.append("Используются mock-данные")
        if self._freshness_label(self._age_minutes(best.created_at)) in {"stale", "old"}:
            warnings.append("Выбранный trait floor не свежий")
        self._quality(used, failed, warnings)
        return best

    def _dedupe_listings(self, items: list[ListingSchema]) -> list[ListingSchema]:
        seen: set[str] = set()
        out: list[ListingSchema] = []
        for item in items:
            key = (
                f"{item.source}:{item.external_id}"
                if item.external_id
                else f"{item.collection}:{item.number}:{item.price_ton}:{item.url}"
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _dedupe_sales(self, items: list[SaleSchema]) -> list[SaleSchema]:
        seen: set[str] = set()
        out: list[SaleSchema] = []
        for item in items:
            key = (
                f"{item.source}:{item.external_id}"
                if item.external_id
                else f"{item.collection}:{item.number}:{item.price_ton}:{item.sold_at.isoformat()}"
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    async def get_recent_sales(self, collection: str, limit: int = 20) -> list[SaleSchema]:
        all_sales: list[SaleSchema] = []
        used: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        for source in self.sources:
            try:
                sales = await source.get_recent_sales(collection, limit=limit)
                self._append_source_quality(source, warnings, failed)
                if sales:
                    used.append(source.name)
                    all_sales.extend(sales)
            except Exception as exc:
                failed.append(source.name)
                logger.warning("Source %s failed for sales: %s", source.name, exc)
        if not all_sales and self.fallback_source is not None:
            warnings.append("Используются mock-данные")
            warnings.append("Нет recent sales, confidence снижен")
            all_sales = await self.fallback_source.get_recent_sales(collection, limit=limit)
            if all_sales:
                used.append(self.fallback_source.name)
        deduped = self._dedupe_sales(all_sales)
        deduped.sort(key=lambda x: x.sold_at, reverse=True)
        if not deduped:
            warnings.append("Нет recent sales, confidence снижен")
        if failed:
            warnings.append("Часть источников недоступна")
        if deduped and self._freshness_label(self._age_minutes(deduped[0].sold_at)) in {"stale", "old"}:
            warnings.append("Recent sales могут быть устаревшими")
        self._quality(used, failed, warnings)
        return deduped[:limit]

    async def get_similar_listings(
        self, collection: str, attributes: list[GiftAttributeSchema], limit: int = 20
    ) -> list[ListingSchema]:
        all_listings: list[ListingSchema] = []
        used: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        for source in self.sources:
            try:
                listings = await source.get_similar_listings(collection, attributes, limit=limit)
                self._append_source_quality(source, warnings, failed)
                if listings:
                    used.append(source.name)
                    all_listings.extend(listings)
            except Exception as exc:
                failed.append(source.name)
                logger.warning("Source %s failed for listings: %s", source.name, exc)
        if not all_listings and self.fallback_source is not None:
            warnings.append("Используются mock-данные")
            all_listings = await self.fallback_source.get_similar_listings(collection, attributes, limit=limit)
            if all_listings:
                used.append(self.fallback_source.name)
        deduped = self._dedupe_listings(all_listings)
        deduped.sort(
            key=lambda x: (
                self._source_priority(x.source, self._freshness_label(self._age_minutes(x.created_at))),
                x.price_ton,
            )
        )
        if failed:
            warnings.append("Часть источников недоступна")
        if deduped and self._freshness_label(self._age_minutes(deduped[0].created_at)) in {"stale", "old"}:
            warnings.append("Listings могут быть устаревшими")
        self._quality(used, failed, warnings)
        return deduped[:limit]

    async def search_underpriced(self, collection: str, filters: dict) -> list[ListingSchema]:
        all_listings: list[ListingSchema] = []
        used: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        for source in self.sources:
            try:
                listings = await source.search_underpriced(collection, filters)
                self._append_source_quality(source, warnings, failed)
                if listings:
                    used.append(source.name)
                    all_listings.extend(listings)
            except Exception as exc:
                failed.append(source.name)
                logger.warning("Source %s failed for underpriced search: %s", source.name, exc)
        if not all_listings and self.fallback_source is not None:
            warnings.append("Используются mock-данные")
            all_listings = await self.fallback_source.search_underpriced(collection, filters)
            if all_listings:
                used.append(self.fallback_source.name)
        deduped = self._dedupe_listings(all_listings)
        deduped.sort(
            key=lambda x: (
                self._source_priority(x.source, self._freshness_label(self._age_minutes(x.created_at))),
                x.price_ton,
            )
        )
        if failed:
            warnings.append("Часть источников недоступна")
        self._quality(used, failed, warnings)
        return deduped

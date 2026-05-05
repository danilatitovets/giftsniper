import logging

from app.config import Settings
from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import ListingSchema, MarketDataQuality, MarketFloor, SaleSchema
from app.sources.base import MarketSource
from app.sources.collections import get_source_identifier, load_collection_registry
from app.sources.http import (
    MarketHTTPClient,
    MarketSourceError,
    MarketSourceUnavailable,
)
from app.sources.mappers.getgems import parse_getgems_floor, parse_getgems_listings, parse_getgems_sales

logger = logging.getLogger(__name__)


class GetGemsSource(MarketSource):
    name = "Getgems"

    def __init__(self, settings: Settings, http_client: MarketHTTPClient | None = None, registry: dict | None = None) -> None:
        self.enabled = settings.getgems_enabled
        self.base_url = settings.getgems_base_url.strip() or "https://api.getgems.io/public-api"
        self.api_key = settings.getgems_api_key.strip()
        self.registry = registry if registry is not None else load_collection_registry(settings.collection_registry_path)
        self.last_quality = MarketDataQuality()
        self.http = http_client or MarketHTTPClient(
            timeout_seconds=settings.market_http_timeout_seconds,
            retries=settings.market_http_retries,
            user_agent=settings.market_http_user_agent,
        )

    async def _request(self, path: str) -> dict | list | None:
        if not self.enabled:
            return None
        if not self.base_url:
            logger.info("Getgems endpoint is not configured/implemented yet")
            return None
        if not self.api_key:
            logger.info("Getgems API key is missing; source request skipped")
            return None
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            return await self.http.get_json(url, headers=headers)
        except MarketSourceUnavailable:
            return None
        except MarketSourceError as exc:
            logger.warning("Getgems source error: %s", exc)
            return None

    def _collection_address(self, collection: str) -> str | None:
        return get_source_identifier(collection, "getgems", "collection_address", registry=self.registry)

    def _set_quality(self, warnings: list[str], used: bool = False, failed: bool = False) -> None:
        self.last_quality = MarketDataQuality(
            sources_used=[self.name] if used else [],
            sources_failed=[self.name] if failed else [],
            warnings=list(dict.fromkeys(warnings)),
            confidence_penalty=20 if warnings else 0,
            is_mock_data=False,
            is_partial_data=True if warnings else False,
        )

    async def get_collection_floor(self, collection: str) -> MarketFloor | None:
        # Confirmed endpoint in docs: GET /v1/nfts/on-sale/{collectionAddress}
        address = self._collection_address(collection)
        if not address:
            self._set_quality(["Collection registry missing Getgems collection_address"])
            return None
        if not self.api_key:
            self._set_quality(["Getgems API key missing"])
            return None
        payload = await self._request(f"/v1/nfts/on-sale/{address}")
        if payload is None:
            self._set_quality(["Getgems endpoint is unavailable or returned empty"], failed=True)
            return None
        floor = parse_getgems_floor(payload, collection=collection)
        if floor is None:
            self._set_quality(["Getgems payload does not contain floor-compatible listing data"], used=True)
            return None
        self._set_quality(["Getgems v1 on-sale used for floor", "real floor: yes"], used=True)
        return floor

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str) -> MarketFloor | None:
        listings = await self.get_similar_listings(collection, [], limit=100)
        if not listings:
            self._set_quality(["trait floor unavailable"], used=False)
            return None
        matched: list[float] = []
        for item in listings:
            attrs = item.attributes_json.get("attributes") if isinstance(item.attributes_json, dict) else None
            if not isinstance(attrs, list):
                continue
            for attr in attrs:
                if not isinstance(attr, dict):
                    continue
                if str(attr.get("trait_type", "")).lower() == trait_type.lower() and str(attr.get("trait_value", "")).lower() == trait_value.lower():
                    matched.append(item.price_ton)
        if not matched:
            self._set_quality(["trait floor unavailable"], used=True)
            return None
        self._set_quality(["Trait floor рассчитан из listings"], used=True)
        return MarketFloor(collection=collection, source=self.name, floor_ton=min(matched))

    async def get_recent_sales(self, collection: str, limit: int = 20) -> list[SaleSchema]:
        # Confirmed endpoint in docs list: GET /v1/collection/history/{collectionAddress}
        address = self._collection_address(collection)
        if not address:
            self._set_quality(["Collection registry missing Getgems collection_address"])
            return []
        if not self.api_key:
            self._set_quality(["Getgems API key missing"])
            return []
        payload = await self._request(f"/v1/collection/history/{address}")
        sales = parse_getgems_sales(payload, collection=collection)
        if not sales:
            self._set_quality(["Нет recent sales из Getgems"], used=True)
            return []
        self._set_quality([f"real sales count: {len(sales)}"], used=True)
        return sales[:limit]

    async def get_similar_listings(
        self, collection: str, attributes: list[GiftAttributeSchema], limit: int = 20
    ) -> list[ListingSchema]:
        # Confirmed endpoint in docs: GET /v1/nfts/on-sale/{collectionAddress}
        address = self._collection_address(collection)
        if not address:
            self._set_quality(["Collection registry missing Getgems collection_address"])
            return []
        if not self.api_key:
            self._set_quality(["Getgems API key missing"])
            return []
        payload = await self._request(f"/v1/nfts/on-sale/{address}")
        listings = parse_getgems_listings(payload, collection=collection)
        warnings: list[str] = []
        warnings.append(f"real listings count: {len(listings)}")
        if attributes:
            has_attrs = any(bool(item.attributes_json.get("attributes")) for item in listings)
            if not has_attrs:
                warnings.append("trait attributes unavailable in Getgems payload")
        if any(bool(item.attributes_json.get("_price_units_uncertain")) for item in listings):
            warnings.append("price units uncertain in some listings")
        self._set_quality(warnings, used=True)
        return listings[:limit]

    async def search_underpriced(self, collection: str, filters: dict) -> list[ListingSchema]:
        return await self.get_similar_listings(collection, attributes=[], limit=int(filters.get("limit", 20)))

import logging

from app.config import Settings
from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import ListingSchema, MarketDataQuality, MarketFloor, SaleSchema
from app.sources.base import MarketSource
from app.sources.http import (
    MarketHTTPClient,
    MarketSourceError,
    MarketSourceNotFound,
    MarketSourceUnavailable,
)

logger = logging.getLogger(__name__)


class TonApiSource(MarketSource):
    name = "TonAPI"

    def __init__(self, settings: Settings, http_client: MarketHTTPClient | None = None) -> None:
        self.enabled = settings.tonapi_enabled
        self.base_url = settings.tonapi_base_url.strip()
        self.api_key = settings.tonapi_api_key.strip()
        self.last_quality = MarketDataQuality()
        self.http = http_client or MarketHTTPClient(
            timeout_seconds=settings.market_http_timeout_seconds,
            retries=settings.market_http_retries,
            user_agent=settings.market_http_user_agent,
        )

    def _set_quality(self, warnings: list[str], used: bool = False, failed: bool = False) -> None:
        self.last_quality = MarketDataQuality(
            sources_used=[self.name] if used else [],
            sources_failed=[self.name] if failed else [],
            warnings=warnings,
            confidence_penalty=6 if used else 0,
            is_mock_data=False,
            is_partial_data=True,
        )

    async def _request(self, path: str, params: dict | None = None) -> dict | list | None:
        if not self.enabled:
            return None
        if not self.base_url:
            self._set_quality(["TonAPI base URL missing"])
            return None
        if not self.api_key:
            self._set_quality(["TonAPI API key missing"])
            return None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            return await self.http.get_json(f"{self.base_url}{path}", headers=headers, params=params)
        except MarketSourceNotFound:
            self._set_quality([], failed=False)
            return None
        except MarketSourceUnavailable:
            self._set_quality(["TonAPI unavailable"], failed=True)
            return None
        except MarketSourceError as exc:
            logger.warning("TonAPI source error: %s", exc)
            self._set_quality(["TonAPI invalid response"], failed=True)
            return None

    async def get_collection_floor(self, collection: str) -> MarketFloor | None:
        self._set_quality(["TonAPI does not provide marketplace floor"], used=True)
        return None

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str) -> MarketFloor | None:
        self._set_quality(["TonAPI does not provide marketplace trait floor"], used=True)
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20) -> list[SaleSchema]:
        self._set_quality(["TonAPI history is on-chain data, sales unavailable or not reliable"], used=True)
        return []

    async def get_similar_listings(
        self, collection: str, attributes: list[GiftAttributeSchema], limit: int = 20
    ) -> list[ListingSchema]:
        self._set_quality(["TonAPI does not provide marketplace listings"], used=True)
        return []

    async def search_underpriced(self, collection: str, filters: dict) -> list[ListingSchema]:
        self._set_quality(["TonAPI does not provide live marketplace listings"], used=True)
        return []

    async def get_nft_by_address(self, address: str) -> dict | None:
        # Official TonAPI endpoint.
        payload = await self._request(f"/v2/nfts/{address}")
        return payload if isinstance(payload, dict) else None

    async def get_collection_info(self, collection_address: str) -> dict | None:
        # Official TonAPI endpoint.
        payload = await self._request(f"/v2/nfts/collections/{collection_address}")
        return payload if isinstance(payload, dict) else None

    async def get_collection_items(self, collection_address: str, limit: int = 100) -> list[dict]:
        payload = await self._request(f"/v2/nfts/collections/{collection_address}/items", params={"limit": limit})
        if not isinstance(payload, dict):
            return []
        items = payload.get("nft_items") or payload.get("items") or []
        return [item for item in items if isinstance(item, dict)]

    async def get_nft_history(self, address: str, limit: int = 50) -> list[dict]:
        # Official TonAPI endpoint for account events is address-based; best-effort NFT history.
        payload = await self._request(f"/v2/accounts/{address}/events", params={"limit": limit})
        if not isinstance(payload, dict):
            return []
        events = payload.get("events") or []
        return [item for item in events if isinstance(item, dict)]

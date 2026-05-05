import logging

from app.config import Settings
from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import ListingSchema, MarketFloor, SaleSchema
from app.sources.base import MarketSource
from app.sources.http import MarketHTTPClient, MarketSourceError, MarketSourceUnavailable

logger = logging.getLogger(__name__)


class FragmentSource(MarketSource):
    name = "Fragment"

    def __init__(self, settings: Settings, http_client: MarketHTTPClient | None = None) -> None:
        self.enabled = settings.fragment_enabled
        self.base_url = settings.fragment_base_url.strip()
        self.api_key = settings.fragment_api_key.strip()
        self.http = http_client or MarketHTTPClient(
            timeout_seconds=settings.market_http_timeout_seconds,
            retries=settings.market_http_retries,
            user_agent=settings.market_http_user_agent,
        )

    async def _request(self, path: str) -> dict | list | None:
        if not self.enabled:
            return None
        if not self.base_url:
            logger.info("Fragment endpoint is not configured/implemented yet")
            return None
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        try:
            return await self.http.get_json(f"{self.base_url}{path}", headers=headers)
        except MarketSourceUnavailable:
            return None
        except MarketSourceError as exc:
            logger.warning("Fragment source error: %s", exc)
            return None

    async def get_collection_floor(self, collection: str) -> MarketFloor | None:
        # TODO: implement once public market floor endpoint is confirmed.
        logger.info("Fragment collection floor endpoint is not configured/implemented yet")
        return None

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str) -> MarketFloor | None:
        logger.info("Fragment trait floor endpoint is not configured/implemented yet")
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20) -> list[SaleSchema]:
        logger.info("Fragment recent sales endpoint is not configured/implemented yet")
        return []

    async def get_similar_listings(
        self, collection: str, attributes: list[GiftAttributeSchema], limit: int = 20
    ) -> list[ListingSchema]:
        logger.info("Fragment similar listings endpoint is not configured/implemented yet")
        return []

    async def search_underpriced(self, collection: str, filters: dict) -> list[ListingSchema]:
        logger.info("Fragment underpriced search endpoint is not configured/implemented yet")
        return []

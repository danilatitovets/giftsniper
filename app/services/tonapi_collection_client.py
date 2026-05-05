"""Async TonAPI client for full collection scans (read-only, Bearer from settings only)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import Settings
from app.sources.http import (
    MarketHTTPClient,
    MarketSourceError,
    MarketSourceNotFound,
    MarketSourceRateLimited,
    MarketSourceUnavailable,
)
from app.services.tonapi_rate_limiter import wait_turn

logger = logging.getLogger(__name__)


class TonAPICollectionClient:
    """HTTP helper for NFT + collection item pagination. Does not log API keys."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = (settings.tonapi_base_url or "https://tonapi.io").rstrip("/")
        self._key = (settings.tonapi_api_key or "").strip()
        self._http = MarketHTTPClient(
            timeout_seconds=int(settings.full_market_http_timeout_seconds),
            retries=2,
            user_agent=settings.market_http_user_agent,
        )

    @property
    def configured(self) -> bool:
        return bool(self._settings.tonapi_enabled and self._base and self._key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}"}

    async def get_nft(self, address: str) -> dict[str, Any] | None:
        if not self.configured:
            return None
        path = f"/v2/nfts/{address.strip()}"
        return await self._get_json_with_429_backoff(f"{self._base}{path}", params=None)

    async def fetch_collection_items_page_raw(
        self,
        collection_address: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int, str, dict[str, Any] | None]:
        """
        Один HTTP-запрос страницы коллекции без ретраев 429 (адаптивный скан сам обрабатывает).
        Возвращает (items, http_status, body_snippet, parsed_json_or_none).
        При 200 и объекте JSON — четвёртый элемент весь корневой dict (для total коллекции и др.).
        """
        if not self.configured:
            return [], 401, ""
        url = f"{self._base}/v2/nfts/collections/{collection_address.strip()}/items"
        params = {"limit": max(1, int(limit)), "offset": max(0, int(offset))}
        timeout = float(self._settings.full_market_http_timeout_seconds)
        safe_headers = {"User-Agent": self._settings.market_http_user_agent, **self._headers()}
        try:
            await wait_turn(
                rps_limit=float(getattr(self._settings, "tonapi_global_rps_limit", 1.0) or 1.0),
                min_interval_ms=int(getattr(self._settings, "tonapi_global_min_interval_ms", 1200) or 1200),
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=safe_headers, params=params)
        except httpx.RequestError as exc:
            logger.warning("TonAPI collection items request failed: %s", exc)
            return [], 0, str(exc)[:500], None

        body_snip = (response.text or "")[:800]
        if response.status_code == 429:
            return [], 429, body_snip, None
        if response.status_code >= 500:
            return [], response.status_code, body_snip, None
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                return [], 200, body_snip, None
            if not isinstance(data, dict):
                return [], 200, body_snip, None
            items = data.get("nft_items") or data.get("items") or []
            return ([x for x in items if isinstance(x, dict)], 200, body_snip, data)
        return [], response.status_code, body_snip, None

    async def fetch_collection_items_page(
        self,
        collection_address: str,
        *,
        limit: int,
        offset: int,
        on_rate_limit: Callable[[], Awaitable[None]] | None = None,
    ) -> list[dict[str, Any]]:
        """Один запрос с backoff по 429 (для совместимости; полный скан использует fetch_collection_items_page_raw)."""
        if not self.configured:
            return []
        path = f"{self._base}/v2/nfts/collections/{collection_address.strip()}/items"
        params = {"limit": max(1, int(limit)), "offset": max(0, int(offset))}
        data = await self._get_json_with_429_backoff(path, params=params, on_rate_limit=on_rate_limit)
        if not isinstance(data, dict):
            return []
        items = data.get("nft_items") or data.get("items") or []
        return [x for x in items if isinstance(x, dict)]

    async def _get_json_with_429_backoff(
        self,
        url: str,
        params: dict | None,
        on_rate_limit: Callable[[], Awaitable[None]] | None = None,
    ) -> dict | list | None:
        max_r = max(1, int(self._settings.full_market_max_429_retries))
        sleep_s = float(self._settings.full_market_rate_limit_sleep_seconds)
        last_exc: Exception | None = None
        for attempt in range(max_r):
            try:
                return await self._http.get_json(url, headers=self._headers(), params=params)
            except MarketSourceNotFound:
                return None
            except MarketSourceRateLimited:
                last_exc = None
                logger.warning("TonAPI rate limited (attempt %s/%s), backing off", attempt + 1, max_r)
                if on_rate_limit:
                    try:
                        await on_rate_limit()
                    except Exception:
                        pass
                await asyncio.sleep(sleep_s * (1 + attempt * 0.25))
            except MarketSourceUnavailable as exc:
                last_exc = exc
                if attempt + 1 < max_r:
                    await asyncio.sleep(sleep_s * 0.5)
                    continue
                raise
            except MarketSourceError as exc:
                last_exc = exc
                break
        if last_exc:
            raise last_exc
        return None

    async def fetch_nft_collections_page(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
        """GET /v2/nfts/collections — one page for dynamic collection-by-name resolution."""
        if not self.configured:
            return [], 401, None
        url = f"{self._base}/v2/nfts/collections"
        params = {"limit": max(1, int(limit)), "offset": max(0, int(offset))}
        timeout = float(self._settings.full_market_http_timeout_seconds)
        safe_headers = {"User-Agent": self._settings.market_http_user_agent, **self._headers()}
        try:
            await wait_turn(
                rps_limit=float(getattr(self._settings, "tonapi_global_rps_limit", 1.0) or 1.0),
                min_interval_ms=int(getattr(self._settings, "tonapi_global_min_interval_ms", 1200) or 1200),
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=safe_headers, params=params)
        except httpx.RequestError as exc:
            logger.warning("TonAPI nft collections request failed: %s", exc)
            return [], 0, None

        if response.status_code != 200:
            return [], response.status_code, None
        try:
            data = response.json()
        except ValueError:
            return [], response.status_code, None
        if not isinstance(data, dict):
            return [], response.status_code, None
        cols = data.get("nft_collections") or []
        return ([x for x in cols if isinstance(x, dict)], response.status_code, data)

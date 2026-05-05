from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class ToncenterClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = (settings.toncenter_api_base_url or "https://toncenter.com/api/v3").rstrip("/")
        self._key = (settings.toncenter_api_key or "").strip()
        self._timeout = float(getattr(settings, "toncenter_timeout_seconds", 15) or 15)

    def configured(self) -> bool:
        return bool(
            getattr(self._settings, "toncenter_enabled", False)
            and getattr(self._settings, "nft_global_resolver_use_toncenter", True)
            and self._base
            and self._key
        )

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self._key,
            "User-Agent": self._settings.market_http_user_agent,
        }

    async def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> tuple[bool, dict | list | None, str | None]:
        if not self.configured():
            return False, None, "toncenter_not_configured"
        url = f"{self._base}{path}"
        retries = 2
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, params=params, headers=self._headers())
            except httpx.TimeoutException:
                if attempt < retries:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                return False, None, "timeout"
            except httpx.RequestError:
                if attempt < retries:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                return False, None, "request_error"

            if resp.status_code == 429:
                if attempt < retries:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                return False, None, "rate_limited"
            if resp.status_code >= 400:
                return False, None, f"http_{resp.status_code}"
            try:
                data = resp.json()
            except ValueError:
                return False, None, "invalid_json"
            return True, data, None
        return False, None, "unknown"

    @staticmethod
    def _extract_items(data: dict | list | None) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            one = data.get("item")
            if isinstance(one, dict):
                return [one]
            raw = (
                data.get("nft_items")
                or data.get("items")
                or data.get("result")
                or data.get("data")
                or []
            )
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
            if isinstance(raw, dict):
                return [raw]
            return []
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    async def fetch_nft_item_by_address(
        self, address: str, *, trace: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        ok, data, err = await self._get_json("/nft/items", params={"address": address.strip(), "limit": 1})
        items: list[dict[str, Any]] = []
        if ok and data is not None:
            items = self._extract_items(data)
        if trace is not None:
            trace["toncenter_http_ok"] = bool(ok)
            trace["toncenter_http_err"] = err
            trace["toncenter_items_count"] = len(items)
        if not ok:
            return None
        return items[0] if items else None

    async def fetch_nft_item_by_collection_and_index(self, collection_address: str, index: int) -> dict[str, Any] | None:
        ok, data, _err = await self._get_json(
            "/nft/items",
            params={"collection_address": collection_address.strip(), "index": int(index), "limit": 1},
        )
        if not ok:
            return None
        items = self._extract_items(data)
        return items[0] if items else None

    async def fetch_nft_collections_page(
        self, *, limit: int, offset: int
    ) -> tuple[bool, list[dict[str, Any]], str | None, dict | list | None]:
        ok, data, err = await self._get_json(
            "/nft/collections",
            params={"limit": max(1, int(limit)), "offset": max(0, int(offset))},
        )
        if not ok:
            return False, [], err, data
        rows = self._extract_items(data)
        return True, rows, None, data

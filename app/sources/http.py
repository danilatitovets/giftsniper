from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import get_settings
from app.services.tonapi_rate_limiter import wait_turn

logger = logging.getLogger(__name__)


class MarketSourceError(Exception):
    pass


class MarketSourceUnavailable(MarketSourceError):
    pass


class MarketSourceNotFound(MarketSourceError):
    """HTTP 404 or equivalent — do not retry the same resource on TonAPI/market HTTP."""

    pass


class MarketSourceRateLimited(MarketSourceError):
    pass


class MarketSourceInvalidResponse(MarketSourceError):
    pass


class MarketHTTPClient:
    def __init__(self, timeout_seconds: int = 10, retries: int = 2, user_agent: str = "GiftSniperBot/1.0") -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.user_agent = user_agent

    async def get_json(self, url: str, headers: dict | None = None, params: dict | None = None) -> dict | list | None:
        safe_headers = {"User-Agent": self.user_agent}
        if headers:
            safe_headers.update(headers)
        is_tonapi = "tonapi.io" in (url or "").lower()
        st = get_settings() if is_tonapi else None
        for attempt in range(1, self.retries + 2):
            try:
                if is_tonapi and st is not None:
                    await wait_turn(
                        rps_limit=float(getattr(st, "tonapi_global_rps_limit", 1.0) or 1.0),
                        min_interval_ms=int(getattr(st, "tonapi_global_min_interval_ms", 1200) or 1200),
                    )
                async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                    response = await client.get(url, headers=safe_headers, params=params)
                if response.status_code == 429:
                    if attempt <= self.retries:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise MarketSourceRateLimited("rate limited")
                if response.status_code >= 500:
                    if attempt <= self.retries:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise MarketSourceUnavailable(f"server error {response.status_code}")
                if response.status_code == 404:
                    raise MarketSourceNotFound("http error 404")
                if response.status_code >= 400:
                    raise MarketSourceUnavailable(f"http error {response.status_code}")
                try:
                    return response.json()
                except ValueError as exc:
                    raise MarketSourceInvalidResponse("invalid json response") from exc
            except MarketSourceError:
                raise
            except httpx.RequestError as exc:
                logger.warning("Market HTTP request failed (attempt %s): %s", attempt, exc)
                if attempt <= self.retries:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise MarketSourceUnavailable("request failed") from exc
        return None

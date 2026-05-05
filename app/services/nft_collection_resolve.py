"""Resolve NFT collection addresses via optional registry + TonAPI listing (no user-facing registry paths)."""

from __future__ import annotations

import difflib
import logging
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import Settings
from app.services.tonapi_collection_client import TonAPICollectionClient
from app.sources.collections import get_tonapi_collection_address, resolve_collection

logger = logging.getLogger(__name__)

CollectionSource = Literal["tonapi", "cache", "collections_json", "none"]
CollectionConfidence = Literal["high", "medium", "low"]

_COLLECTION_ADDR_CACHE: dict[str, tuple[str, str, float]] = {}
_CACHE_TTL_SECONDS = 86400.0
_TONAPI_SCAN_PAGE_SIZE = 100
_TONAPI_SCAN_MAX_PAGES = 60
_FUZZY_MIN_RATIO = 0.88
_FUZZY_ACCEPT_SINGLE_RATIO = 0.92


@dataclass
class CollectionCandidate:
    address: str
    name: str


@dataclass
class CollectionResolutionResult:
    address: str | None
    name: str | None
    source: CollectionSource
    confidence: CollectionConfidence
    candidates: list[CollectionCandidate] = field(default_factory=list)


def normalize_collection_match_key(label: str) -> str:
    """Lowercase NFKC label with collapsed spaces and common punctuation normalized."""
    s = unicodedata.normalize("NFKC", (label or "").strip())
    s = " ".join(s.split())
    for a, b in (
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u00b7", " "),
        ("`", "'"),
    ):
        s = s.replace(a, b)
    return s.casefold()


def display_name_from_tonapi_collection(coll: dict[str, Any]) -> str:
    meta = coll.get("metadata") if isinstance(coll.get("metadata"), dict) else {}
    return str(meta.get("name") or coll.get("name") or "").strip()


def remember_resolved_collection(norm_key: str, address: str, display_name: str) -> None:
    _COLLECTION_ADDR_CACHE[norm_key] = (address, display_name, time.time())


def _cache_get(norm_key: str) -> tuple[str, str] | None:
    hit = _COLLECTION_ADDR_CACHE.get(norm_key)
    if not hit:
        return None
    addr, name, ts = hit
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _COLLECTION_ADDR_CACHE.pop(norm_key, None)
        return None
    return addr, name


async def resolve_collection_address_by_name(
    collection_name: str,
    *,
    settings: Settings,
    client: TonAPICollectionClient,
    registry: dict[str, Any],
) -> CollectionResolutionResult:
    """
    Optional collections registry first, then in-memory cache, then TonAPI paginated /v2/nfts/collections.
    Does not read filesystem paths itself — caller passes ``registry`` from load_collection_registry.
    """
    _ = settings
    raw = (collection_name or "").strip()
    norm = normalize_collection_match_key(raw)
    if not norm:
        return CollectionResolutionResult(None, None, "none", "low", [])

    canonical, _payload = resolve_collection(raw, registry=registry)
    lookup_key = canonical or raw
    json_addr = get_tonapi_collection_address(lookup_key, registry=registry)
    if json_addr:
        disp = (canonical or raw).strip()
        remember_resolved_collection(norm, json_addr, disp)
        return CollectionResolutionResult(json_addr, disp, "collections_json", "high", [])

    cached = _cache_get(norm)
    if cached:
        a, n = cached
        return CollectionResolutionResult(a, n, "cache", "high", [])

    if not client.configured:
        logger.info("collection resolve skipped TonAPI scan: client not configured")
        return CollectionResolutionResult(None, raw, "none", "low", [])

    exact: list[CollectionCandidate] = []
    fuzzy_by_addr: dict[str, tuple[float, str]] = {}

    for page in range(_TONAPI_SCAN_MAX_PAGES):
        offset = page * _TONAPI_SCAN_PAGE_SIZE
        cols, status, _ = await client.fetch_nft_collections_page(
            limit=_TONAPI_SCAN_PAGE_SIZE, offset=offset
        )
        if status == 429:
            logger.warning("TonAPI 429 while listing nft collections (offset=%s)", offset)
            break
        if status != 200:
            logger.info("TonAPI nft collections page failed status=%s offset=%s", status, offset)
            break
        if not cols:
            break

        for coll in cols:
            addr = str(coll.get("address") or "").strip()
            dname = display_name_from_tonapi_collection(coll)
            mkey = normalize_collection_match_key(dname)
            if not addr or not mkey:
                continue
            if mkey == norm:
                exact.append(CollectionCandidate(address=addr, name=dname or raw))
            else:
                ratio = difflib.SequenceMatcher(None, norm, mkey).ratio()
                if ratio >= _FUZZY_MIN_RATIO:
                    prev = fuzzy_by_addr.get(addr)
                    if prev is None or ratio > prev[0]:
                        fuzzy_by_addr[addr] = (ratio, dname or addr)

        if len(cols) < _TONAPI_SCAN_PAGE_SIZE:
            break

    if len(exact) == 1:
        c = exact[0]
        remember_resolved_collection(norm, c.address, c.name)
        return CollectionResolutionResult(c.address, c.name, "tonapi", "high", [])

    if len(exact) > 1:
        return CollectionResolutionResult(None, None, "tonapi", "low", exact[:12])

    strong = [(addr, r, name) for addr, (r, name) in fuzzy_by_addr.items() if r >= _FUZZY_ACCEPT_SINGLE_RATIO]
    if len(strong) == 1:
        addr, _r, name = strong[0]
        remember_resolved_collection(norm, addr, name)
        return CollectionResolutionResult(addr, name, "tonapi", "medium", [])

    if len(strong) > 1:
        cands = [CollectionCandidate(address=a, name=n) for a, _r, n in strong][:12]
        return CollectionResolutionResult(None, None, "tonapi", "low", cands)

    logger.debug(
        "collection not found by name after TonAPI scan; optional registry alias missing name=%r",
        raw[:80],
    )
    return CollectionResolutionResult(None, raw, "none", "low", [])

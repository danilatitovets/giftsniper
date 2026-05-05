"""In-memory TTL cache for market profiles (MVP). TODO: Redis backend."""

from __future__ import annotations

import time
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}

# Seconds — collection/trait/rare_deals scan (Stage 31)
TTL_COLLECTION_PROFILE = 300
TTL_TRAIT_PROFILE = 600
TTL_RARE_DEALS = 300


def _now() -> float:
    return time.time()


def cache_key(collection: str, source: str, profile_type: str) -> str:
    return f"{profile_type}:{source}:{collection.strip().lower()}"


def get_cached(collection: str, source: str, profile_type: str) -> Any | None:
    key = cache_key(collection, source, profile_type)
    row = _CACHE.get(key)
    if not row:
        return None
    expires, value = row
    if _now() > expires:
        del _CACHE[key]
        return None
    return value


def set_cached(collection: str, source: str, profile_type: str, value: Any, ttl_seconds: float) -> None:
    key = cache_key(collection, source, profile_type)
    _CACHE[key] = (_now() + ttl_seconds, value)


def clear_market_cache(collection: str | None = None, source: str | None = None) -> int:
    """Clear entries; optional collection/source substring match (case-insensitive)."""
    global _CACHE
    if collection is None and source is None:
        n = len(_CACHE)
        _CACHE = {}
        return n
    removed = 0
    coll_l = collection.strip().lower() if collection else None
    src_l = source.strip().lower() if source else None
    keys = list(_CACHE.keys())
    for k in keys:
        parts = k.split(":", 2)
        kl = k.lower()
        if coll_l and coll_l not in kl:
            continue
        if src_l and (len(parts) < 2 or parts[1].lower() != src_l):
            continue
        del _CACHE[k]
        removed += 1
    return removed


def format_cache_status() -> str:
    now = _now()
    lines = [f"Market cache entries: {len(_CACHE)}"]
    for k, (exp, _) in sorted(_CACHE.items())[:25]:
        left = max(0, int(exp - now))
        lines.append(f"- {k} (TTL ~{left}s)")
    if len(_CACHE) > 25:
        lines.append(f"... +{len(_CACHE) - 25} more")
    lines.append("TODO: Redis for multi-worker consistency.")
    return "\n".join(lines)

import time

from app.services.market_cache import (
    TTL_COLLECTION_PROFILE,
    clear_market_cache,
    format_cache_status,
    get_cached,
    set_cached,
)


def test_market_cache_ttl_hit():
    clear_market_cache()
    set_cached("ice", "mock", "collection", {"x": 1}, TTL_COLLECTION_PROFILE)
    assert get_cached("ice", "mock", "collection") == {"x": 1}


def test_market_cache_expires():
    clear_market_cache()
    set_cached("a", "b", "collection", 42, 0.05)
    time.sleep(0.12)
    assert get_cached("a", "b", "collection") is None


def test_format_cache_status():
    clear_market_cache()
    set_cached("c", "d", "trait", {}, 300)
    s = format_cache_status()
    assert "trait" in s

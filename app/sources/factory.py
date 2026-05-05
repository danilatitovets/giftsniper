import logging

from app.sources.aggregator import MarketSourceAggregator
from app.sources.collections import get_source_identifier, load_collection_registry
from app.sources.fragment import FragmentSource
from app.sources.getgems import GetGemsSource
from app.sources.http import MarketHTTPClient
from app.sources.mock import MockMarketSource
from app.sources.manual import ManualSource
from app.sources.tonapi import TonApiSource
from app.sources.tonnel import TonnelSource

logger = logging.getLogger(__name__)


def create_market_source(settings, user_id: int | None = None):
    mock = MockMarketSource()
    registry = load_collection_registry(settings.collection_registry_path)
    http = MarketHTTPClient(
        timeout_seconds=settings.market_http_timeout_seconds,
        retries=settings.market_http_retries,
        user_agent=settings.market_http_user_agent,
    )
    prod_block_mock = bool(settings.production_mode) and not bool(settings.allow_mock_in_production)
    mock_for_trading = bool(settings.enable_mock_source) and not prod_block_mock

    if mock_for_trading:
        return MarketSourceAggregator(sources=[mock], fallback_source=mock)

    sources: list = []
    if settings.getgems_enabled:
        sources.append(GetGemsSource(settings, http_client=http, registry=registry))
    if settings.tonnel_enabled:
        sources.append(TonnelSource(settings, http_client=http))
    if settings.fragment_enabled:
        sources.append(FragmentSource(settings, http_client=http))
    if settings.manual_market_enabled:
        sources.append(ManualSource(user_id=user_id))
    if settings.tonapi_enabled:
        sources.append(TonApiSource(settings, http_client=http))

    if not sources:
        if prod_block_mock:
            logger.warning("Production: no sources configured; mock disabled — manual-only stub.")
            return MarketSourceAggregator(sources=[ManualSource(user_id=user_id)], fallback_source=None)
        logger.info("No real market sources enabled, fallback to mock.")
        return MarketSourceAggregator(sources=[mock], fallback_source=mock)

    fallback = None if prod_block_mock else mock
    return MarketSourceAggregator(sources=sources, fallback_source=fallback)


def describe_sources(settings) -> dict:
    registry = load_collection_registry(settings.collection_registry_path)
    ice_cream_address = get_source_identifier("Ice Cream", "getgems", "collection_address", registry=registry)
    prod = bool(settings.production_mode)
    allow_mock_prod = bool(settings.allow_mock_in_production)
    mock_trading_blocked = prod and not allow_mock_prod and bool(settings.block_trading_verdict_on_mock)
    gg_url = bool(settings.getgems_base_url.strip() or "https://api.getgems.io/public-api")
    gg_usable = bool(settings.getgems_enabled and gg_url and bool(settings.getgems_api_key.strip()))
    tn_usable = bool(settings.tonnel_enabled and settings.tonnel_base_url.strip() and settings.tonnel_api_key.strip())
    fr_usable = bool(settings.fragment_enabled and settings.fragment_base_url.strip() and settings.fragment_api_key.strip())
    return {
        "mock_enabled": settings.enable_mock_source,
        "mock_allowed_for_trading": bool(settings.enable_mock_source) and not (prod and not allow_mock_prod),
        "registry_path": settings.collection_registry_path,
        "collections_count": len(registry),
        "ice_cream_getgems_address_configured": bool(ice_cream_address),
        "production_mode": prod,
        "allow_mock_in_production": allow_mock_prod,
        "mock_trading_blocked": mock_trading_blocked,
        "require_real_or_manual": bool(settings.require_real_or_manual_for_trading),
        "getgems": {
            "enabled": settings.getgems_enabled,
            "has_base_url": gg_url,
            "has_api_key": bool(settings.getgems_api_key.strip()),
            "usable": gg_usable,
        },
        "tonnel": {
            "enabled": settings.tonnel_enabled,
            "has_base_url": bool(settings.tonnel_base_url.strip()),
            "has_api_key": bool(settings.tonnel_api_key.strip()),
            "usable": tn_usable,
        },
        "tonapi": {
            "enabled": settings.tonapi_enabled,
            "has_base_url": bool(settings.tonapi_base_url.strip()),
            "has_api_key": bool(settings.tonapi_api_key.strip()),
            "usable_metadata": bool(settings.tonapi_enabled),
        },
        "manual": {
            "enabled": bool(settings.manual_market_enabled),
            "has_base_url": True,
            "has_api_key": False,
            "usable": bool(settings.manual_market_enabled),
        },
        "fragment": {
            "enabled": settings.fragment_enabled,
            "has_base_url": bool(settings.fragment_base_url.strip()),
            "has_api_key": bool(settings.fragment_api_key.strip()),
            "usable": fr_usable,
        },
    }

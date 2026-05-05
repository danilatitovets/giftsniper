from app.bot.handlers.settings import render_sources_report
from app.config import Settings
from app.sources.aggregator import MarketSourceAggregator
from app.sources.factory import create_market_source, describe_sources


def _settings(**kwargs):
    payload = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    }
    payload.update(kwargs)
    return Settings(**payload)


def test_factory_respects_enabled_flags():
    s = _settings(
        ENABLE_MOCK_SOURCE=False,
        GETGEMS_ENABLED=False,
        TONAPI_ENABLED=False,
        TONNEL_ENABLED=False,
        FRAGMENT_ENABLED=False,
    )
    source = create_market_source(s)
    assert isinstance(source, MarketSourceAggregator)
    assert source.sources[0].name == "Manual"


def test_factory_uses_real_enabled_sources():
    s = _settings(
        ENABLE_MOCK_SOURCE=False,
        GETGEMS_ENABLED=True,
        TONNEL_ENABLED=False,
        FRAGMENT_ENABLED=False,
        GETGEMS_BASE_URL="https://api.getgems.io/public-api",
    )
    source = create_market_source(s)
    assert isinstance(source, MarketSourceAggregator)
    assert source.sources[0].name == "Getgems"
    assert source.sources[1].name == "Manual"


def test_sources_command_report_hides_api_keys():
    s = _settings(GETGEMS_API_KEY="SECRET_123")
    text = render_sources_report(s)
    assert "SECRET_123" not in text
    assert "API keys: скрыты" in text


def test_describe_sources_contains_flags():
    s = _settings()
    info = describe_sources(s)
    assert "getgems" in info
    assert "mock_enabled" in info

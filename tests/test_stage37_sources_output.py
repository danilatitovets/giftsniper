"""Stage 37 — /sources-style describe_sources is explicit."""

from app.bot.handlers.settings import render_sources_report
from app.config import Settings


def test_sources_report_shows_mock_trading_guard():
    s = Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        PRODUCTION_MODE=True,
        ALLOW_MOCK_IN_PRODUCTION=False,
        ENABLE_MOCK_SOURCE=True,
        TONAPI_ENABLED=True,
    )
    text = render_sources_report(s)
    assert "Mock trading blocked" in text or "mock" in text.lower()
    assert "TonAPI" in text

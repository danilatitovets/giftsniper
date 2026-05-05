import pytest

from app.services.nft_metadata import format_nft_check_result
from app.bot.handlers.settings import render_sources_report
from app.config import Settings


def _settings(**kwargs):
    payload = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    }
    payload.update(kwargs)
    return Settings(**payload)


def test_sources_report_not_show_tonapi_key():
    settings = _settings(TONAPI_API_KEY="SECRET")
    text = render_sources_report(settings)
    assert "SECRET" not in text
    assert "TonAPI" in text


def test_nft_check_format_without_secrets():
    result = {
        "status": "найден",
        "source": "TonAPI",
        "collection": "Ice Cream",
        "nft_address": "EQ_TEST",
        "owner": "EQ_OWNER",
        "attributes": [{"trait_type": "Symbol", "value": "Moon"}],
        "history_available": True,
    }
    text = format_nft_check_result(result)
    assert "TonAPI" in text
    assert "SECRET" not in text


@pytest.mark.asyncio
async def test_nft_check_need_address_message():
    text = format_nft_check_result({"status": "нужен address", "source": "TonAPI"})
    assert "нужен address" in text

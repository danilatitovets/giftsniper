"""`/check` routes NFT-like input to TonAPI full market only (no mock flip card)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import analysis
from app.services import nft_check_limits as nft_check_limits_mod


def _stub_user_session(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    u = MagicMock(language_code="en")
    monkeypatch.setattr(analysis, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(analysis.UserRepository, "get_or_create", AsyncMock(return_value=u))
    monkeypatch.setattr(nft_check_limits_mod, "record_successful_nft_check", AsyncMock(return_value=None))


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.chat = type("C", (), {"id": 4242})()
        self.out: list[str] = []

    async def answer(self, text: str = "", **kwargs):
        self.out.append(text)


@pytest.mark.asyncio
async def test_check_command_uses_real_market_not_mock_in_production(monkeypatch):
    async def fake_deliver(message, *, telegram_id, username, payload, settings):
        await message.answer("REAL_TONAPI_BLOCK")
        return ("done", True)

    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", fake_deliver)

    async def boom(*a, **k):
        raise AssertionError("run_gift_check must not run for NFT-like /check")

    monkeypatch.setattr(analysis, "run_gift_check", boom)

    _stub_user_session(monkeypatch)

    msg = _Msg("/check Ice Cream #217467")
    await analysis.check_handler(msg, AsyncMock())
    assert any("REAL_TONAPI_BLOCK" in x for x in msg.out)


@pytest.mark.asyncio
async def test_check_non_nft_payload_still_runs_gift_check(monkeypatch):
    async def legacy_deliver(*a, **k):
        return ("legacy", False)

    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", legacy_deliver)

    called = {"n": 0}

    async def fake_run_gift_check(*a, **k):
        called["n"] += 1
        from app.services.gift_analysis_flow import UniversalCheckOutcome

        return UniversalCheckOutcome(False, error="not an nft-like payload")

    monkeypatch.setattr(analysis, "run_gift_check", fake_run_gift_check)

    _stub_user_session(monkeypatch)

    msg = _Msg("/check totally_unknown_format_xyz_no_url_no_hash")
    await analysis.check_handler(msg, AsyncMock())
    assert called["n"] == 1
    assert msg.out and "not an nft-like" in msg.out[-1]

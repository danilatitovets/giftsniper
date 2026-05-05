"""MVP рефералок: парсинг payload, ссылки, лимиты + бонусные проверки."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.referral_constants import (
    REFERRAL_BONUS_EVERY_N_REWARD,
    REFERRAL_BONUS_EVERY_N_USERS,
    REFERRAL_BONUS_PER_USER,
)
from app.services import nft_check_limits as nft_limits_mod
from app.services.referrals import ReferralStats, build_referral_link, build_referral_share_url, parse_referrer_telegram_id_from_start_payload


def test_parse_referrer_telegram_id() -> None:
    assert parse_referrer_telegram_id_from_start_payload("ref_123456789") == 123456789
    assert parse_referrer_telegram_id_from_start_payload("ref_abc") is None
    assert parse_referrer_telegram_id_from_start_payload("check_invoice") is None


def test_build_referral_link_and_share() -> None:
    link = build_referral_link(telegram_id=999, bot_username="@GiftRadarBot")
    assert link == "https://t.me/GiftRadarBot?start=ref_999"
    share = build_referral_share_url(ref_link=link, share_text="Hello")
    assert share.startswith("https://t.me/share/url?")
    assert "ref_999" in share


def test_milestone_bonus_totals_three_invites() -> None:
    """3 друга: +2 +2 +2 +5 = 11 бонусных проверок у реферера."""
    per = REFERRAL_BONUS_PER_USER
    n = REFERRAL_BONUS_EVERY_N_USERS
    ms = REFERRAL_BONUS_EVERY_N_REWARD
    total = 0
    for i in range(1, 4):
        total += per
        if i % n == 0:
            total += ms
    assert total == 11


class _DummySessionCM:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_a: object) -> bool:
        return False


class _RecordingSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


class _RecordingSessionCM:
    def __init__(self) -> None:
        self.session = _RecordingSession()

    async def __aenter__(self) -> _RecordingSession:
        return self.session

    async def __aexit__(self, *_a: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_assert_nft_daily_check_allowed_under_daily_limit_skips_bonus(monkeypatch: pytest.MonkeyPatch) -> None:
    class UR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_or_create(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="ru")

    class NCR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_count(self, _uid: int) -> int:
            return 1

    monkeypatch.setattr(nft_limits_mod, "SessionLocal", lambda: _DummySessionCM())
    monkeypatch.setattr(nft_limits_mod, "UserRepository", UR)
    monkeypatch.setattr(nft_limits_mod, "UserNftCheckDayRepository", NCR)
    monkeypatch.setattr(nft_limits_mod, "checks_per_day_limit", lambda _u: 3)
    spy = AsyncMock(return_value=99)
    monkeypatch.setattr(nft_limits_mod, "get_bonus_checks", spy)

    msg = MagicMock()
    msg.answer = AsyncMock()
    ok = await nft_limits_mod.assert_nft_daily_check_allowed(msg, 1, "u")
    assert ok is True
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_assert_nft_daily_check_allowed_uses_bonus_when_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class UR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_or_create(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="ru")

    class NCR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_count(self, _uid: int) -> int:
            return 3

    monkeypatch.setattr(nft_limits_mod, "SessionLocal", lambda: _DummySessionCM())
    monkeypatch.setattr(nft_limits_mod, "UserRepository", UR)
    monkeypatch.setattr(nft_limits_mod, "UserNftCheckDayRepository", NCR)
    monkeypatch.setattr(nft_limits_mod, "checks_per_day_limit", lambda _u: 3)
    monkeypatch.setattr(nft_limits_mod, "get_bonus_checks", AsyncMock(return_value=2))

    msg = MagicMock()
    msg.answer = AsyncMock()
    ok = await nft_limits_mod.assert_nft_daily_check_allowed(msg, 1, "u")
    assert ok is True
    msg.answer.assert_not_called()


@pytest.mark.asyncio
async def test_assert_nft_daily_check_blocked_when_over_and_no_bonus(monkeypatch: pytest.MonkeyPatch) -> None:
    class UR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_or_create(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="ru")

    class NCR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_count(self, _uid: int) -> int:
            return 3

    monkeypatch.setattr(nft_limits_mod, "SessionLocal", lambda: _DummySessionCM())
    monkeypatch.setattr(nft_limits_mod, "UserRepository", UR)
    monkeypatch.setattr(nft_limits_mod, "UserNftCheckDayRepository", NCR)
    monkeypatch.setattr(nft_limits_mod, "checks_per_day_limit", lambda _u: 3)
    monkeypatch.setattr(nft_limits_mod, "get_bonus_checks", AsyncMock(return_value=0))

    msg = MagicMock()
    msg.answer = AsyncMock()
    ok = await nft_limits_mod.assert_nft_daily_check_allowed(msg, 1, "u")
    assert ok is False
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_record_successful_uses_daily_when_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class UR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_or_create(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="ru")

    class NCR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_count(self, _uid: int) -> int:
            return 1

        async def increment(self, _uid: int) -> int:
            return 2

    cm = _RecordingSessionCM()
    monkeypatch.setattr(nft_limits_mod, "SessionLocal", lambda: cm)
    monkeypatch.setattr(nft_limits_mod, "UserRepository", UR)
    monkeypatch.setattr(nft_limits_mod, "UserNftCheckDayRepository", NCR)
    monkeypatch.setattr(nft_limits_mod, "checks_per_day_limit", lambda _u: 3)
    consume = AsyncMock(return_value=True)
    monkeypatch.setattr(nft_limits_mod, "consume_bonus_check_if_available", consume)

    rem = await nft_limits_mod.record_successful_nft_check(1, "u", notify_message=None)
    assert rem is None
    consume.assert_not_called()
    cm.session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_record_successful_consumes_bonus_when_at_daily_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class UR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_or_create(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="ru")

    class NCR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_count(self, _uid: int) -> int:
            return 3

        async def increment(self, _uid: int) -> int:
            raise AssertionError("increment should not run when using bonus")

    cm = _RecordingSessionCM()
    monkeypatch.setattr(nft_limits_mod, "SessionLocal", lambda: cm)
    monkeypatch.setattr(nft_limits_mod, "UserRepository", UR)
    monkeypatch.setattr(nft_limits_mod, "UserNftCheckDayRepository", NCR)
    monkeypatch.setattr(nft_limits_mod, "checks_per_day_limit", lambda _u: 3)
    monkeypatch.setattr(nft_limits_mod, "consume_bonus_check_if_available", AsyncMock(return_value=True))
    monkeypatch.setattr(nft_limits_mod, "get_bonus_checks", AsyncMock(return_value=4))

    msg = MagicMock()
    msg.answer = AsyncMock()
    rem = await nft_limits_mod.record_successful_nft_check(1, "u", notify_message=msg)
    assert rem == 4
    msg.answer.assert_awaited()
    cm.session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_ref_screen_contains_link_and_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.bot.handlers import start as start_mod

    monkeypatch.setattr(
        start_mod,
        "get_referral_stats",
        AsyncMock(return_value=ReferralStats(invited_count=3, bonus_checks_available=11)),
    )
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: _DummySessionCM())
    monkeypatch.setattr(start_mod, "get_settings", lambda: SimpleNamespace(public_bot_username="TestBot"))

    m = MagicMock()
    m.bot.username = "TestBotFallback"
    body, kb = await start_mod._referral_screen_parts(m, lang="ru", user_id=1, telegram_id=42)
    assert "ref_42" in body
    assert "11" in body
    assert kb.inline_keyboard

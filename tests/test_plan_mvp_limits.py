"""MVP: планы Free/Pro/Sniper, лимиты из Settings, списание market checks, UX лимитов."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import analysis as analysis_mod
from app.config import Settings
from app.i18n import localized_carousel_body, t
from app.services import nft_check_limits
from app.services.feature_limits import get_plan_limits, normalize_plan_for_limits
from app.services.plan_catalog import PLAN_ORDER, carousel_body, plan_price_ton


def _settings(**kw: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "t",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "plan_free_daily_nft_checks": 3,
        "plan_free_watchlist_limit": 3,
        "plan_pro_price_ton": 2.0,
        "plan_pro_daily_nft_checks": 100,
        "plan_pro_watchlist_limit": 50,
        "plan_sniper_price_ton": 7.0,
        "plan_sniper_daily_nft_checks": 1000,
        "plan_sniper_watchlist_limit": 300,
        "plan_pro_duration_days": 30,
        "plan_sniper_duration_days": 30,
    }
    base.update(kw)
    return Settings(**base)


def test_plan_limits_free_pro_sniper() -> None:
    s = _settings()
    free = get_plan_limits("free", settings=s)
    pro = get_plan_limits("pro", settings=s)
    sniper = get_plan_limits("sniper", settings=s)
    assert free["checks_per_day"] == 3
    assert free["max_gifts"] == 3
    assert pro["checks_per_day"] == 100
    assert pro["max_gifts"] == 50
    assert sniper["checks_per_day"] == 1000
    assert sniper["max_gifts"] == 300


def test_plan_prices_from_settings() -> None:
    s = _settings(plan_pro_price_ton=2.5, plan_sniper_price_ton=7.25)
    assert plan_price_ton("pro", s) == 2.5
    assert plan_price_ton("sniper", s) == 7.25


def test_normalize_plan_aliases() -> None:
    assert normalize_plan_for_limits("starter") == "pro"
    assert normalize_plan_for_limits("trader") == "sniper"


def test_env_example_has_no_real_keys() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / ".env.example").read_text(encoding="utf-8")
    assert "PASTE_" in text or "HERE" in text or "localhost" in text
    assert "eyJ" not in text  # no JWT-like blobs in example
    assert "PLAN_PRO_PRICE_TON=" in text
    assert "PLAN_FREE_DAILY_NFT_CHECKS=" in text


def test_upgrade_carousel_shows_three_plans() -> None:
    s = _settings()
    assert len(PLAN_ORDER) == 3
    for key in PLAN_ORDER:
        body = localized_carousel_body(key, s, "ru")
        assert key in ("free", "pro", "sniper")
        assert len(body) > 20


def test_upgrade_carousel_prices_match_settings() -> None:
    s = _settings(plan_pro_price_ton=2.0, plan_sniper_price_ton=7.0)
    pro_body = localized_carousel_body("pro", s, "ru")
    sniper_body = localized_carousel_body("sniper", s, "ru")
    assert "2 TON" in pro_body or "2.0 TON" in pro_body
    assert "7 TON" in sniper_body or "7.0 TON" in sniper_body


def test_current_plan_shown_in_carousel_ru() -> None:
    from app.bot.handlers.ton_upgrade import _carousel_keyboard

    kb = _carousel_keyboard("free", current_user_plan="free", lang="ru")
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert "Текущий план" in labels


def test_paid_plan_shows_renew_ru() -> None:
    from app.bot.handlers.ton_upgrade import _carousel_keyboard

    kb = _carousel_keyboard("pro", current_user_plan="pro", lang="ru")
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Продлить" in x for x in labels)


@pytest.mark.asyncio
async def test_market_check_limit_blocks_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    deliver = AsyncMock()

    class _UR:
        def __init__(self, _s: object) -> None:
            pass

        async def get_or_create(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="en", is_blocked=False)

    monkeypatch.setattr(analysis_mod, "SessionLocal", lambda: _DummySessionCM())
    monkeypatch.setattr(analysis_mod, "UserRepository", _UR)
    monkeypatch.setattr(analysis_mod.gift_flow, "deliver_nft_check_tonapi_only", deliver)
    monkeypatch.setattr(nft_check_limits, "assert_nft_daily_check_allowed", AsyncMock(return_value=False))
    msg = MagicMock()
    msg.from_user = MagicMock(id=1, username="u")
    msg.answer = AsyncMock()
    await analysis_mod.execute_check_payload(msg, "EQtestnftaddr_______________________________")
    deliver.assert_not_awaited()


class _DummySessionCM:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_a: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_check_success_records_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_mod, "SessionLocal", lambda: _DummySessionCM())
    monkeypatch.setattr(nft_check_limits, "SessionLocal", lambda: _DummySessionCM())

    class UR:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="en", is_blocked=False)

    class NCR:
        async def increment(self, *_a: object, **_kw: object) -> int:
            return 1

    monkeypatch.setattr(analysis_mod, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(nft_check_limits, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(nft_check_limits, "UserNftCheckDayRepository", lambda _s: NCR())
    monkeypatch.setattr(nft_check_limits, "assert_nft_daily_check_allowed", AsyncMock(return_value=True))
    rec = AsyncMock()
    monkeypatch.setattr(nft_check_limits, "record_successful_nft_check", rec)
    monkeypatch.setattr(
        analysis_mod.gift_flow,
        "deliver_nft_check_tonapi_only",
        AsyncMock(return_value=("done", True)),
    )
    msg = MagicMock()
    msg.from_user = MagicMock(id=1, username="u")
    msg.answer = AsyncMock()
    await analysis_mod.execute_check_payload(msg, "EQtestnftaddr_______________________________")
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_tonapi_failure_does_not_record_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_mod, "SessionLocal", lambda: _DummySessionCM())
    monkeypatch.setattr(nft_check_limits, "SessionLocal", lambda: _DummySessionCM())

    class UR:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", role="user", language_code="en", is_blocked=False)

    monkeypatch.setattr(analysis_mod, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(nft_check_limits, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(nft_check_limits, "assert_nft_daily_check_allowed", AsyncMock(return_value=True))
    rec = AsyncMock()
    monkeypatch.setattr(nft_check_limits, "record_successful_nft_check", rec)
    monkeypatch.setattr(
        analysis_mod.gift_flow,
        "deliver_nft_check_tonapi_only",
        AsyncMock(return_value=("done", False)),
    )
    msg = MagicMock()
    msg.from_user = MagicMock(id=1, username="u")
    msg.answer = AsyncMock()
    await analysis_mod.execute_check_payload(msg, "EQtestnftaddr_______________________________")
    rec.assert_not_awaited()


def test_market_check_limit_message_has_upgrade_button(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.bot.upgrade_inline import daily_check_limit_keyboard, format_daily_checks_limit_message

    body = format_daily_checks_limit_message(3, lang="ru", settings=_settings())
    assert "🚫" in body
    assert "Pro" in body
    kb = daily_check_limit_keyboard(lang="ru")
    flat = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Upgrade" in x for x in flat)
    assert len(flat) >= 2


def test_watchlist_limit_message_has_upgrade_button() -> None:
    from app.bot.upgrade_inline import format_watchlist_limit_message, upgrade_inline_keyboard_open

    body = format_watchlist_limit_message("Free", 3, lang="ru", settings=_settings())
    assert "🚫" in body
    kb = upgrade_inline_keyboard_open(lang="ru")
    flat = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Upgrade" in x for x in flat)


def test_no_seed_private_key_request_in_payment_texts() -> None:
    low = t("payment.note_no_wallet", "en").lower()
    assert "seed" in low or "private key" in low


def test_no_collections_json_in_limit_texts() -> None:
    s = _settings()
    for key in PLAN_ORDER:
        assert "collections.json" not in localized_carousel_body(key, s, "ru").lower()
        assert "collections.json" not in carousel_body(key, s).lower()


def test_carousel_body_reads_plan_limits_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(
        plan_free_daily_nft_checks=7,
        plan_free_watchlist_limit=11,
        plan_pro_daily_nft_checks=99,
        plan_pro_watchlist_limit=88,
    )
    free = carousel_body("free", s)
    assert "7" in free
    assert "11" in free
    pro = carousel_body("pro", s)
    assert "99" in pro
    assert "88" in pro

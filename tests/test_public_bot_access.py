"""PUBLIC_BOT_ACCESS: slash commands bypass closed-beta gate; admin and Free limits unchanged."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext

from app.bot.handlers import admin as admin_handlers
from app.bot.handlers import passive_gift
from app.bot.handlers import start as start_handlers
from app.bot.messages import build_commands_text
from app.bot.middlewares import AccessControlMiddleware
from app.bot.mvp_setup import MVP_COMMANDS
from app.services.beta_access import is_beta_access_allowed, should_show_beta_gate
from app.services.gift_analysis_flow import _map_nft_full_market_error
from app.services.gift_intake import GiftIdentity
from app.services import nft_check_limits as nft_limits_pkg
from app.services.real_market_collection_scan import TargetNftInfo
from app.services.universal_nft_resolver import ResolvedNft


def _settings(**kw):
    base = {
        "beta_mode": True,
        "beta_require_invite": True,
        "beta_support_username": "@s",
        "admin_telegram_ids": "",
        "public_bot_access": False,
        "plan_free_daily_nft_checks": 3,
        "plan_pro_daily_nft_checks": 100,
        "plan_sniper_daily_nft_checks": 1000,
        "rate_limit_commands_per_minute": 20,
        "rate_limit_heavy_commands_per_hour": 20,
    }
    base.update(kw)
    return type("S", (), base)()


def _free_user():
    return type("U", (), {"role": "user", "plan": "free", "entitlement_status": "", "beta_invite_redeemed": False})()


def test_is_beta_access_allowed_public_flag():
    u = _free_user()
    assert is_beta_access_allowed(u, _settings(public_bot_access=True), telegram_id=900_001) is True
    assert should_show_beta_gate(u, _settings(public_bot_access=True), telegram_id=900_001) is False


def test_is_beta_access_allowed_without_public_still_gated():
    u = _free_user()
    assert is_beta_access_allowed(u, _settings(public_bot_access=False), telegram_id=900_002) is False


def test_mvp_commands_list_has_no_admin_slash_names():
    names = {c.command.lower() for c in MVP_COMMANDS}
    assert "admin_beta_health" not in names
    assert "owner_setup_check" not in names


def test_build_commands_text_for_user_excludes_admin_block():
    text = build_commands_text(is_admin=False)
    low = text.lower()
    assert "admin (кратко)" not in low
    assert "admin_beta" not in low
    assert "owner_setup_check" not in low


class _Ctx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    def add(self, *_a, **_k) -> None:
        return None


async def _next(*_args, **_kwargs):
    return "ok"


@pytest.mark.asyncio
async def test_middleware_allows_slash_start_when_public_bot_access(monkeypatch):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "is_blocked": False, "role": "user", "plan": "free"})()

        async def get_or_create_with_created(self, *a, **k):
            u = await self.get_or_create(*a, **k)
            return u, False

        async def touch_activity(self, *_):
            return None

    class _Inv:
        def __init__(self, _s):
            pass

        async def has_user_redemption(self, *_):
            return False

    class _Billing:
        def __init__(self, _s):
            pass

        async def get_entitlement(self, *_):
            return None

    settings = _settings(public_bot_access=True)
    monkeypatch.setattr("app.bot.middlewares.get_settings", lambda: settings)
    monkeypatch.setattr("app.bot.middlewares.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.middlewares.UserRepository", _Users)
    monkeypatch.setattr("app.bot.middlewares.BetaInviteRepository", _Inv)
    monkeypatch.setattr("app.bot.middlewares.BillingRepository", _Billing)

    class _Msg:
        text = "/start"
        from_user = type("U", (), {"id": 111, "username": "pub"})()
        answers: list[str] = []

        async def answer(self, text: str):
            self.answers.append(text)

    middleware = AccessControlMiddleware()
    result = await middleware(_next, _Msg(), {})
    assert result == "ok"


@pytest.mark.asyncio
async def test_middleware_plain_nft_url_not_slash_passes_to_handler(monkeypatch):
    """Non-slash messages skip AccessControlMiddleware beta gate (NFT links are not blocked here)."""

    class _Msg:
        text = "https://tonviewer.com/nft/EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl"
        from_user = type("U", (), {"id": 222, "username": "u"})()

    middleware = AccessControlMiddleware()
    result = await middleware(_next, _Msg(), {})
    assert result == "ok"


@pytest.mark.asyncio
async def test_passive_nft_link_sends_preview_with_market_button(monkeypatch: pytest.MonkeyPatch):
    addr = "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl"
    url = f"https://tonviewer.com/nft/{addr}"

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("DbU", (), {"id": 501, "language_code": "ru"})()

        async def get_or_create_with_created(self, *a, **k):
            u = await self.get_or_create(*a, **k)
            return u, False

    async def _resolve_identity(_user, _text, _settings):
        ident = GiftIdentity(
            collection="Col",
            number=None,
            nft_address=addr,
            collection_address=None,
            normalized_collection="col",
            canonical_key="k",
        )
        return None, ident

    target = TargetNftInfo(
        name="NFT",
        number=1,
        address=addr,
        collection_name="Col",
        collection_address="CA",
        model="m",
        backdrop="b",
        symbol="s",
    )
    resolved = ResolvedNft(
        original_payload=url,
        nft_address=addr,
        collection_address="CA",
        nft_name="NFT",
        collection_name="Col",
        item_number=1,
        image_url=None,
        traits={"model": "m", "backdrop": "b", "symbol": "s"},
        sale_price_ton=None,
        for_sale=False,
        source="tonapi",
        learned=False,
        target=target,
        nft_raw={},
        resolver_trace=None,
    )

    async def _resolve_uni(_text, _user, _settings, _client, learn=True):
        return resolved, None

    class _TonClient:
        def __init__(self, _settings):
            pass

    class _Msg:
        def __init__(self):
            self.text = url
            self.from_user = type("U", (), {"id": 333, "username": "nftu"})()
            self.chat = type("C", (), {"id": 9})()
            self.bot = MagicMock()
            self.bot.edit_message_text = AsyncMock()
            self.answers: list[tuple[str, dict]] = []

        async def answer(self, text: str = "", **kwargs):
            self.answers.append((text, kwargs))
            return type("R", (), {"message_id": 42})()

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Ctx())
    monkeypatch.setattr(passive_gift, "UserRepository", _Users)
    monkeypatch.setattr(passive_gift, "resolve_gift_identity", _resolve_identity)
    monkeypatch.setattr(passive_gift, "resolve_universal_nft", _resolve_uni)
    monkeypatch.setattr(passive_gift, "TonAPICollectionClient", _TonClient)
    monkeypatch.setattr(passive_gift, "extract_nft_preview_media", lambda *_a, **_k: passive_gift.PreviewMedia(url="", kind="none", mime_type=None, source_field="t"))
    monkeypatch.setattr(passive_gift.runtime_state, "nft_action_session_put", lambda *_a, **_k: "sid99")

    m = _Msg()
    fsm = MagicMock(spec=FSMContext)
    fsm.clear = AsyncMock()
    fsm.get_state = AsyncMock(return_value=None)
    await passive_gift.passive_gift_text(m, fsm)

    flat = "\n".join(t for t, _ in m.answers)
    assert "NFT" in flat or "Коллекция" in flat
    last_markup = m.answers[-1][1].get("reply_markup")
    assert last_markup is not None
    labels = [b.text for row in last_markup.inline_keyboard for b in row]
    assert "🔎 Проверить рынок" in labels


@pytest.mark.asyncio
async def test_passive_market_check_callback_runs_execute(monkeypatch: pytest.MonkeyPatch):
    called = {"n": 0}

    async def _exec(_message, payload, *, telegram_id=None, username=None):
        called["n"] += 1
        assert telegram_id == 444

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("DbU", (), {"id": 88, "language_code": "ru"})()

    class _Query:
        def __init__(self):
            self.data = "gift:check:sidm"
            self.from_user = type("U", (), {"id": 444, "username": "chk"})()
            self.message = type("M", (), {"chat": type("C", (), {"id": 1})(), "bot": type("B", (), {})()})()

        async def answer(self, *_a, **_k):
            return None

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Ctx())
    monkeypatch.setattr(passive_gift, "UserRepository", _Users)
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ" + "a" * 46},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    fsm = MagicMock(spec=FSMContext)
    fsm.clear = AsyncMock()
    await passive_gift.passive_gift_callback(_Query(), fsm)
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_start_upgrade_callback_reaches_upgrade_carousel(monkeypatch: pytest.MonkeyPatch):
    sent = {"n": 0}

    async def _send_upgrade(message, **kwargs):
        sent["n"] += 1
        assert kwargs.get("start_plan_key") == "pro"

    class _Q:
        data = start_handlers.CB_START_UPGRADE
        message = type("M", (), {})()
        from_user = type("U", (), {"id": 1, "username": "u"})()

        async def answer(self, **_k):
            return None

    monkeypatch.setattr(start_handlers, "send_upgrade_carousel_message", _send_upgrade)
    fsm = MagicMock(spec=FSMContext)
    fsm.clear = AsyncMock()
    await start_handlers.start_upgrade_callback(_Q(), fsm)
    assert sent["n"] == 1


@pytest.mark.asyncio
async def test_start_mylist_callback_reaches_watchlist(monkeypatch: pytest.MonkeyPatch):
    sent = {"n": 0}

    async def _send_wl(message, **_kwargs):
        sent["n"] += 1

    class _Q:
        data = start_handlers.CB_START_MYLIST
        message = type("M", (), {})()
        from_user = type("U", (), {"id": 2, "username": "wl"})()

        async def answer(self, **_k):
            return None

    monkeypatch.setattr(start_handlers, "send_watchlist_message", _send_wl)
    fsm = MagicMock(spec=FSMContext)
    fsm.clear = AsyncMock()
    await start_handlers.start_my_list_callback(_Q(), fsm)
    assert sent["n"] == 1


@pytest.mark.asyncio
async def test_admin_beta_health_rejects_plain_user(monkeypatch: pytest.MonkeyPatch):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"role": "user"})()

    class _Msg:
        text = "/admin_beta_health"
        from_user = type("U", (), {"id": 777001, "username": "nobody"})()
        out: list[str] = []

        async def answer(self, t: str, **kwargs):
            self.out.append(t)

    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.get_settings", lambda: type("S", (), {"admin_telegram_ids": ""})())
    msg = _Msg()
    await admin_handlers.admin_beta_health_handler(msg)
    assert any("только admin" in x for x in msg.out)


@pytest.mark.asyncio
async def test_daily_nft_check_limit_still_blocks_free_user(monkeypatch: pytest.MonkeyPatch):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 12, "role": "user", "plan": "free", "language_code": "ru"})()

    class _DayRepo:
        def __init__(self, _s):
            pass

        async def get_count(self, _uid):
            return 99

    class _Msg:
        out: list[str] = []

        async def answer(self, text: str, **kwargs):
            self.out.append(text)

    monkeypatch.setattr("app.services.nft_check_limits.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.services.nft_check_limits.UserRepository", _Users)
    monkeypatch.setattr("app.services.nft_check_limits.UserNftCheckDayRepository", _DayRepo)
    monkeypatch.setattr("app.services.nft_check_limits.checks_per_day_limit", lambda *a, **k: 3)
    monkeypatch.setattr("app.services.nft_check_limits.get_bonus_checks", AsyncMock(return_value=0))

    ok = await nft_limits_pkg.assert_nft_daily_check_allowed(_Msg(), 1, "x")
    assert ok is False


def test_user_facing_limit_and_mapped_errors_avoid_internal_paths():
    from app.bot.upgrade_inline import format_daily_checks_limit_message

    body = format_daily_checks_limit_message(3, lang="ru", settings=_settings(public_bot_access=True))
    low = body.lower()
    assert "mock" not in low
    assert "legacy" not in low
    assert "collections.json" not in low

    mapped = _map_nft_full_market_error("failed to read collections.json from disk")
    ml = mapped.lower()
    assert "collections.json" not in ml
    assert "mock" not in ml
    assert "legacy" not in ml

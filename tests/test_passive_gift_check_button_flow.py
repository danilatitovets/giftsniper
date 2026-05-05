from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from sqlalchemy import BigInteger

from app.bot.handlers import passive_gift
from app.db.models import User
from app.services import gift_analysis_flow
from app.services.real_market_collection_scan import FullMarketNftReport, SellPricePlan, TargetNftInfo, TraitComps


class _Bot:
    async def edit_message_text(self, *_a, **_k):
        return None


class _Msg:
    def __init__(self, *, bot_user_id: int = 8201077261):
        self.from_user = type("U", (), {"id": bot_user_id, "username": "bot"})()
        self.chat = type("C", (), {"id": 1})()
        self.bot = _Bot()
        self.out: list[str] = []

    async def answer(self, text: str = "", **_kwargs):
        self.out.append(text)
        return type("R", (), {"message_id": 1})()

    async def edit_reply_markup(self, **_kwargs):
        return None


class _Query:
    def __init__(self, data: str, *, user_id: int, username: str | None = "u", bot_user_id: int = 8201077261):
        self.data = data
        self.from_user = type("U", (), {"id": user_id, "username": username})()
        self.message = _Msg(bot_user_id=bot_user_id)
        self.answers: list[str] = []

    async def answer(self, text: str = "", **_kwargs):
        self.answers.append(text)


class _Sess:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _fsm_ctx() -> FSMContext:
    m = MagicMock(spec=FSMContext)
    m.clear = AsyncMock()
    return m


def _fake_users_cls(db_user_id: int = 77):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_a, **_k):
            return type("DbU", (), {"id": db_user_id, "language_code": "ru"})()

    return _Users


@pytest.mark.asyncio
async def test_check_button_routes_to_tonapi_check_flow(monkeypatch: pytest.MonkeyPatch):
    called = {"n": 0}

    async def _exec(_message, payload, *, telegram_id=None, username=None):
        called["n"] += 1
        assert payload == "EQ" + "a" * 46
        assert telegram_id == 1234
        assert username == "human"

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ" + "a" * 46},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s1", user_id=1234, username="human")
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_check_button_passes_original_payload(monkeypatch: pytest.MonkeyPatch):
    payload = "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl"
    got: dict[str, str] = {}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        got["payload"] = payload

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": payload},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s2", user_id=1234)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert got["payload"] == payload


@pytest.mark.asyncio
async def test_check_button_uses_query_from_user(monkeypatch: pytest.MonkeyPatch):
    got: dict[str, int] = {}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        got["telegram_id"] = int(telegram_id)

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ" + "a" * 46},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s3", user_id=2222, bot_user_id=8201077261)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert got["telegram_id"] == 2222


@pytest.mark.asyncio
async def test_passive_gift_check_callback_uses_query_from_user_not_bot_user(
    monkeypatch: pytest.MonkeyPatch,
):
    got: dict[str, int] = {}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        got["telegram_id"] = int(telegram_id)

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ" + "a" * 46},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s4", user_id=4040, bot_user_id=8201077261)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert got["telegram_id"] == 4040


@pytest.mark.asyncio
async def test_check_button_does_not_create_user_for_bot_id(monkeypatch: pytest.MonkeyPatch):
    created_ids: list[int] = []
    check_ids: list[int] = []

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, telegram_id, _username):
            created_ids.append(int(telegram_id))
            return type("DbU", (), {"id": 77, "language_code": "ru"})()

    async def _exec(_message, payload, *, telegram_id=None, username=None, **_kw):
        check_ids.append(int(telegram_id))
        assert username == "human"
        assert payload == "EQ" + "a" * 46

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _Users)
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ" + "a" * 46},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:sell_price:s5", user_id=3333, username="human", bot_user_id=8201077261)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert created_ids == [3333]
    assert check_ids == [3333]


def test_user_telegram_id_accepts_large_id():
    assert isinstance(User.__table__.c.telegram_id.type, BigInteger)


@pytest.mark.asyncio
async def test_tonapi_404_from_check_button_returns_friendly_message(monkeypatch: pytest.MonkeyPatch):
    class _Tonapi:
        configured = True

        def __init__(self, _settings):
            pass

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_a, **_k):
            return type("DbU", (), {"id": 1, "language_code": "ru"})()

    async def _resolve(*_a, **_k):
        return None, "❌ Не нашёл NFT через TonAPI.\n\nПроверь адрес или пришли ссылку на NFT / Telegram Gift."

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)
    monkeypatch.setattr(gift_analysis_flow, "TonAPICollectionClient", _Tonapi)
    monkeypatch.setattr(gift_analysis_flow, "resolve_universal_nft", _resolve)

    msg = _Msg()
    route, ok = await gift_analysis_flow.deliver_nft_check_tonapi_only(
        msg,
        telegram_id=1111,
        username="u",
        payload="EQ" + "a" * 46,
        settings=gift_analysis_flow.Settings(
            BOT_TOKEN="x",
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            TONAPI_ENABLED=True,
            TONAPI_API_KEY="k",
            FULL_MARKET_SCAN_ENABLED=True,
            PRODUCTION_MODE=True,
        ),
    )
    assert route == "done"
    assert ok is False
    assert any("Не нашёл NFT через TonAPI" in x for x in msg.out)


@pytest.mark.asyncio
async def test_tonapi_404_from_check_button_does_not_crash(monkeypatch: pytest.MonkeyPatch):
    class _Tonapi:
        configured = True

        def __init__(self, _settings):
            pass

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_a, **_k):
            return type("DbU", (), {"id": 1, "language_code": "ru"})()

    async def _resolve(*_a, **_k):
        return None, "❌ Не нашёл NFT через TonAPI.\n\nПроверь адрес или пришли ссылку на NFT / Telegram Gift."

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)
    monkeypatch.setattr(gift_analysis_flow, "TonAPICollectionClient", _Tonapi)
    monkeypatch.setattr(gift_analysis_flow, "resolve_universal_nft", _resolve)

    msg = _Msg()
    await gift_analysis_flow.deliver_nft_check_tonapi_only(
        msg,
        telegram_id=1111,
        username="u",
        payload="EQ" + "a" * 46,
        settings=gift_analysis_flow.Settings(
            BOT_TOKEN="x",
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            TONAPI_ENABLED=True,
            TONAPI_API_KEY="k",
            FULL_MARKET_SCAN_ENABLED=True,
            PRODUCTION_MODE=True,
        ),
    )
    assert True


@pytest.mark.asyncio
async def test_tonapi_404_from_check_button_message_has_no_mock_words(
    monkeypatch: pytest.MonkeyPatch,
):
    class _Tonapi:
        configured = True

        def __init__(self, _settings):
            pass

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_a, **_k):
            return type("DbU", (), {"id": 1, "language_code": "ru"})()

    async def _resolve(*_a, **_k):
        return None, "❌ Не нашёл NFT через TonAPI.\n\nПроверь адрес или пришли ссылку на NFT / Telegram Gift."

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)
    monkeypatch.setattr(gift_analysis_flow, "TonAPICollectionClient", _Tonapi)
    monkeypatch.setattr(gift_analysis_flow, "resolve_universal_nft", _resolve)

    msg = _Msg()
    await gift_analysis_flow.deliver_nft_check_tonapi_only(
        msg,
        telegram_id=1111,
        username="u",
        payload="EQ" + "a" * 46,
        settings=gift_analysis_flow.Settings(
            BOT_TOKEN="x",
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            TONAPI_ENABLED=True,
            TONAPI_API_KEY="k",
            FULL_MARKET_SCAN_ENABLED=True,
            PRODUCTION_MODE=True,
        ),
    )
    blob = "\n".join(msg.out).lower()
    assert "mock" not in blob
    assert "legacy" not in blob


@pytest.mark.asyncio
async def test_check_command_and_check_button_same_resolution_for_nft_like_payload(
    monkeypatch: pytest.MonkeyPatch,
):
    payload = "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl"
    seen: list[str] = []

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        seen.append(payload)

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": payload},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s7", user_id=999, username="human")
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    await _exec(q.message, payload=payload, telegram_id=999, username="human")

    assert seen == [payload, payload]


@pytest.mark.asyncio
async def test_nft_like_payload_never_goes_legacy_in_production_from_button(
    monkeypatch: pytest.MonkeyPatch,
):
    called = {"n": 0}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        called["n"] += 1

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ" + "a" * 46},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s8", user_id=4444)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_add_button_requires_resolved_nft(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(passive_gift.runtime_state, "nft_action_session_get", lambda _uid, _sid: None)

    q = _Query("gift:add:missing", user_id=12)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert q.message.out
    joined = "\n".join(q.message.out).lower()
    assert "устарел" in joined or "карточк" in joined


@pytest.mark.asyncio
async def test_legacy_listing_price_callback_routes_to_same_check_as_market(monkeypatch: pytest.MonkeyPatch):
    """Старая кнопка listing_price / sell_price теперь ведёт в тот же full-market check, что и «Проверить рынок»."""
    got: dict[str, str] = {}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        got["payload"] = payload or ""

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ_CURRENT_LISTING"},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:sell_price:s9", user_id=13)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert got["payload"] == "EQ_CURRENT_LISTING"


@pytest.mark.asyncio
async def test_callback_buttons_use_resolved_token(monkeypatch: pytest.MonkeyPatch):
    got: dict[str, str] = {}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        got["payload"] = payload

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ_RESOLVED_TOKEN_ADDRESS"},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:tok_cb", user_id=9090)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert got["payload"] == "EQ_RESOLVED_TOKEN_ADDRESS"


@pytest.mark.asyncio
async def test_token_cannot_be_used_by_other_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda uid, _sid: {"nft_address": "EQ_ONLY_FOR_OWNER"} if uid == 1 else None,
    )

    q = _Query("gift:check:tok_owner", user_id=2)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert q.answers
    assert "Сессия истекла" in q.answers[-1]


@pytest.mark.asyncio
async def test_token_expired_friendly_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(passive_gift.runtime_state, "nft_action_session_get", lambda _uid, _sid: None)

    q = _Query("gift:check:tok_expired", user_id=123)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert q.answers
    assert "Сессия истекла (15 мин). Пришли ссылку снова." in q.answers[-1]


@pytest.mark.asyncio
async def test_expired_token_friendly(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(passive_gift.runtime_state, "nft_action_session_get", lambda _uid, _sid: None)
    q = _Query("gift:check:expired", user_id=321)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert q.answers
    assert "Сессия истекла" in q.answers[-1]


@pytest.mark.asyncio
async def test_market_scan_starts_only_after_check_button(monkeypatch: pytest.MonkeyPatch):
    called = {"n": 0}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        called["n"] += 1
        assert payload == "EQ_RESOLVED_ONLY_ON_CLICK"

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ_RESOLVED_ONLY_ON_CLICK"},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s-click", user_id=501)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_resolved_session_callback_uses_nft_address(monkeypatch: pytest.MonkeyPatch):
    got: dict[str, str] = {}

    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        got["payload"] = payload

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ_FROM_RESOLVED_TOKEN"},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s-addr", user_id=777)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert got["payload"] == "EQ_FROM_RESOLVED_TOKEN"


@pytest.mark.asyncio
async def test_no_mock_no_legacy_in_passive_flow(monkeypatch: pytest.MonkeyPatch):
    async def _exec(_message, payload=None, *, telegram_id=None, username=None, **_kwargs):
        assert payload.startswith("EQ")

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ_NO_LEGACY_PATH"},
    )
    monkeypatch.setattr("app.bot.handlers.analysis.execute_check_payload", _exec)

    q = _Query("gift:check:s-legacy", user_id=888)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert q.answers and "Проверяю" in q.answers[-1]


@pytest.mark.asyncio
async def test_close_button_removes_keyboard(monkeypatch: pytest.MonkeyPatch):
    called = {"n": 0}

    class _MsgWithEdit(_Msg):
        async def edit_reply_markup(self, **_kwargs):
            called["n"] += 1
            return None

    q = _Query("gift:close:tok", user_id=1)
    q.message = _MsgWithEdit()
    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(passive_gift.runtime_state, "pending_gift_cancel", lambda *_a, **_k: None)

    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_deal_button_sets_pending_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _fake_users_cls())
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "nft_action_session_get",
        lambda _uid, _sid: {"nft_address": "EQ_DEAL_ADDR", "collection_address": "EQ_COLL"},
    )
    got: dict[str, str] = {}
    monkeypatch.setattr(
        passive_gift.runtime_state,
        "pending_deal_put",
        lambda user_id, *, nft_address, ttl_seconds=None: got.update({"nft": nft_address}),
    )
    q = _Query("gift:deal_check:tok-deal", user_id=42)
    await passive_gift.passive_gift_callback(q, _fsm_ctx())
    assert got["nft"] == "EQ_DEAL_ADDR"
    assert any("Укажи цену сделки" in x for x in q.message.out)


@pytest.mark.asyncio
async def test_progress_message_is_edited_not_duplicated(monkeypatch: pytest.MonkeyPatch):
    class _BotRec:
        def __init__(self):
            self.edits: list[str] = []

        async def edit_message_text(self, text: str, **_kwargs):
            self.edits.append(text)
            return None

    class _MsgRec(_Msg):
        def __init__(self):
            super().__init__()
            self.bot = _BotRec()
            self.answers: list[str] = []

        async def answer(self, text: str = "", **_kwargs):
            self.answers.append(text)
            return type("R", (), {"message_id": 10})()

    class _Tonapi:
        configured = True
        def __init__(self, _settings):
            pass

    class _Users:
        def __init__(self, _s):
            pass
        async def get_or_create(self, *_a, **_k):
            return type("DbU", (), {"id": 1, "language_code": "ru"})()

    async def _resolve(*_a, **_k):
        tgt = TargetNftInfo(
            name="NFT #1", number=1, address="EQ_A", collection_name="Pretty Posy",
            collection_address="EQ_C", model=None, backdrop=None, symbol=None, image_url=None
        )
        r = type("R", (), {"target": tgt, "image_url": None})()
        return r, None

    async def _flow(*_a, **_k):
        on_progress = _k["on_progress"]
        await on_progress("Pretty Posy", 10, 3, "scan", 1000, None, None)
        report = FullMarketNftReport(
            target=TargetNftInfo(
                name="NFT #1", number=1, address="EQ_A", collection_name="Pretty Posy",
                collection_address="EQ_C", model=None, backdrop=None, symbol=None, image_url=None
            ),
            loaded_count=10, listings_count=3, collection_floor=1.0, collection_median=2.0,
            same_model=TraitComps("model", None, 0, None, None),
            same_backdrop=TraitComps("backdrop", None, 0, None, None),
            same_symbol=TraitComps("symbol", None, 0, None, None),
            close_comps=[],
            sell_plan=SellPricePlan(1, 2, 3, 1, "low", "few"),
            is_partial_scan=False,
            source_label="TonAPI",
        )
        return report, None

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)
    monkeypatch.setattr(gift_analysis_flow, "TonAPICollectionClient", _Tonapi)
    monkeypatch.setattr(gift_analysis_flow, "resolve_universal_nft", _resolve)
    monkeypatch.setattr(gift_analysis_flow, "run_full_market_analysis_flow", _flow)

    msg = _MsgRec()
    route, ok = await gift_analysis_flow.deliver_nft_check_tonapi_only(
        msg,
        telegram_id=1,
        username="u",
        payload="EQ" + "a" * 46,
        settings=gift_analysis_flow.Settings(
            BOT_TOKEN="x",
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            TONAPI_ENABLED=True,
            TONAPI_API_KEY="k",
            FULL_MARKET_SCAN_ENABLED=True,
            PRODUCTION_MODE=True,
        ),
    )
    assert route == "done" and ok is True
    assert len(msg.answers) == 1
    assert "Анализирую рынок" in msg.answers[0]
    assert all("Собираю цены из открытых объявлений" not in t for t in msg.answers[1:])
    assert msg.bot.edits
    assert any("Проверка NFT" in t for t in msg.bot.edits)
    assert all("<b>" not in t for t in msg.bot.edits if "Анализирую рынок" in t)

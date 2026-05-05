"""UX «Мой список»: добавление из callback без инструкции /add."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, User

import app.services.watchlist_add_flow as waf
from app.bot.handlers import analysis
from app.bot.handlers import gifts as gifts_mod
from app.bot.keyboards import CB_START_MYLIST, start_hub_inline_keyboard
from app.config import get_settings
from app.i18n import t
from app.services import runtime_state
from app.services.watchlist_add_flow import (
    MyListAddOutcome,
    MyListAddResult,
    add_to_my_list,
    gift_identity_from_action_session,
    snapshot_to_action_session,
)


@pytest.mark.asyncio
async def test_add_button_adds_resolved_nft_immediately() -> None:
    settings = get_settings()
    gift_repo = MagicMock()
    user = SimpleNamespace(id=1, plan="free", role="user", is_blocked=False)
    gift_obj = MagicMock(collection="Pool Floats", number=123, id=1, title="Pool Float #123")
    gift_repo.get_by_nft_address = AsyncMock(return_value=None)
    gift_repo.count_by_user = AsyncMock(return_value=0)
    gift_repo.add_or_update_gift_from_identity = AsyncMock(return_value=(gift_obj, "created"))
    gift_repo.update_gift_visuals = AsyncMock(return_value=gift_obj)
    gift_repo.get_by_id = AsyncMock(return_value=gift_obj)
    sp = {
        "nft_address": "EQf_tg_gift_______________________8SLj_JAAJ6KYUn",
        "collection_name": "Pool Floats",
        "nft_name": "Pool Float #162345",
        "collection_address": "EQcoll",
    }
    out = await add_to_my_list(
        gift_repo=gift_repo,
        user=user,
        settings=settings,
        nft_address=sp["nft_address"],
        action_session=sp,
    )
    assert out.result == MyListAddResult.CREATED
    assert "162345" in out.display_name or "Pool Float" in out.display_name


@pytest.mark.asyncio
async def test_add_button_does_not_send_slash_add_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    called_uid: list[int] = []

    def _get(uid: int, sid: str):
        called_uid.append(uid)
        return "rep", "EQtestaddr___________________________", {"nft_name": "X #1", "collection_name": "C"}

    monkeypatch.setattr(runtime_state, "nft_check_sidebar_get", _get)

    gift_obj = MagicMock(collection="C", number=1, id=9, title="X #1")

    async def _add(**kwargs: object) -> MyListAddOutcome:
        return MyListAddOutcome(
            MyListAddResult.CREATED,
            gift_obj,
            display_name="X #1",
            collection_display="C",
        )

    monkeypatch.setattr(analysis, "add_to_my_list", _add)

    class CM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(analysis, "SessionLocal", lambda: CM())
    monkeypatch.setattr(analysis.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(plan="free", language_code="ru")))

    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    cq = MagicMock(spec=CallbackQuery)
    cq.data = "watch:add:abc123"
    cq.message = msg
    cq.from_user = User(id=424242, is_bot=False, first_name="u")
    cq.answer = AsyncMock()

    await analysis.nft_check_watch_add_callback(cq)
    assert called_uid == [424242]
    text = msg.answer.await_args.args[0]
    assert "/add" not in text


@pytest.mark.asyncio
async def test_add_button_uses_query_from_user_not_bot_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def _get(uid: int, sid: str):
        seen.append(uid)
        return "r", "EQx", {"nft_name": "N", "collection_name": "Col"}

    monkeypatch.setattr(runtime_state, "nft_check_sidebar_get", _get)

    gift_obj = MagicMock(collection="Col", number=1, id=1, title="N")

    async def _add(**kwargs: object) -> MyListAddOutcome:
        return MyListAddOutcome(MyListAddResult.CREATED, gift_obj, display_name="N", collection_display="Col")

    monkeypatch.setattr(analysis, "add_to_my_list", _add)

    class CM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(analysis, "SessionLocal", lambda: CM())
    monkeypatch.setattr(analysis.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(plan="free", language_code="en")))

    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    cq = MagicMock(spec=CallbackQuery)
    cq.data = "watch:add:s"
    cq.message = msg
    cq.from_user = User(id=777001, is_bot=False, first_name="human")
    cq.answer = AsyncMock()

    await analysis.nft_check_watch_add_callback(cq)
    assert seen == [777001]


@pytest.mark.asyncio
async def test_add_button_handles_getgems_gift_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()

    async def boom(*a: object, **k: object) -> object:
        raise AssertionError("resolve_from_nft_address must not run for resolved gift ref session")

    monkeypatch.setattr(waf, "resolve_from_nft_address", boom)
    gift_repo = MagicMock()
    user = SimpleNamespace(id=1, plan="free", role="user", is_blocked=False)
    gift_obj = MagicMock(collection="Pool Floats", number=162345, id=1, title="Pool Float #162345")
    gift_repo.get_by_nft_address = AsyncMock(return_value=None)
    gift_repo.count_by_user = AsyncMock(return_value=0)
    gift_repo.add_or_update_gift_from_identity = AsyncMock(return_value=(gift_obj, "created"))
    gift_repo.update_gift_visuals = AsyncMock(return_value=gift_obj)
    gift_repo.get_by_id = AsyncMock(return_value=gift_obj)
    sp = {
        "nft_address": "EQf_tg_gift_______________________8SLj_JAAJ6KYUn",
        "collection_name": "Pool Floats",
        "nft_name": "Pool Float #162345",
        "address_kind": "getgems_gift_ref",
        "resolved_source": "getgems_web",
    }
    out = await add_to_my_list(
        gift_repo=gift_repo,
        user=user,
        settings=settings,
        nft_address=sp["nft_address"],
        action_session=sp,
    )
    assert out.result == MyListAddResult.CREATED


@pytest.mark.asyncio
async def test_add_button_duplicate_shows_already_added() -> None:
    settings = get_settings()
    gift_repo = MagicMock()
    user = SimpleNamespace(id=1, plan="free", role="user", is_blocked=False)
    gift_obj = MagicMock(collection="C", number=5, id=3, title="C #5")
    gift_repo.get_by_nft_address = AsyncMock(return_value=None)
    gift_repo.count_by_user = AsyncMock(return_value=0)
    gift_repo.add_or_update_gift_from_identity = AsyncMock(return_value=(gift_obj, "updated"))
    gift_repo.update_gift_visuals = AsyncMock(return_value=gift_obj)
    gift_repo.get_by_id = AsyncMock(return_value=gift_obj)
    sp = {"nft_address": "EQdup", "collection_name": "C", "nft_name": "C #5"}
    out = await add_to_my_list(
        gift_repo=gift_repo,
        user=user,
        settings=settings,
        nft_address="EQdup",
        action_session=sp,
    )
    assert out.result == MyListAddResult.UPDATED


@pytest.mark.asyncio
async def test_add_button_expired_session_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime_state, "nft_check_sidebar_get", lambda *a: (None, None, None))

    class CM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(analysis, "SessionLocal", lambda: CM())
    monkeypatch.setattr(analysis.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(language_code="ru")))
    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    cq = MagicMock(spec=CallbackQuery)
    cq.data = "watch:add:gone"
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    await analysis.nft_check_watch_add_callback(cq)
    text = msg.answer.await_args.args[0]
    assert "устарел" in text.lower() or "expired" in text.lower()


@pytest.mark.asyncio
async def test_add_button_limit_shows_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    gift_repo = MagicMock()
    user = SimpleNamespace(id=1, plan="free", role="user", is_blocked=False)
    gift_repo.get_by_nft_address = AsyncMock(return_value=None)
    gift_repo.count_by_user = AsyncMock(return_value=0)

    monkeypatch.setattr(waf, "check_usage_limit", lambda *a, **k: (False, 3))
    monkeypatch.setattr(waf, "get_plan_limits", lambda _p: {"max_gifts": 3})
    out = await add_to_my_list(
        gift_repo=gift_repo,
        user=user,
        settings=settings,
        nft_address="EQnew",
        action_session={"nft_address": "EQnew", "collection_name": "C", "nft_name": "C #1"},
    )
    assert out.result == MyListAddResult.LIMIT
    assert out.max_gifts == 3


def test_start_menu_has_my_list_button() -> None:
    flat = [b.callback_data for row in start_hub_inline_keyboard(lang="ru").inline_keyboard for b in row]
    assert CB_START_MYLIST in flat


def test_watchlist_word_not_in_user_facing_add_flow() -> None:
    keys = (
        "mylist.added_title",
        "mylist.added_hint",
        "mylist.already_title",
        "watchlist.empty",
        "limit.watchlist_block",
    )
    for key in keys:
        low = t(key, "ru").lower()
        assert "watchlist" not in low
        assert "ватчлист" not in low


def test_my_list_empty_state() -> None:
    body = t("watchlist.empty", "ru")
    assert "Мой список" in body


@pytest.mark.asyncio
async def test_watchlist_command_alias_still_works_if_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_send = AsyncMock()
    monkeypatch.setattr(gifts_mod, "send_watchlist_message", mock_send)
    msg = MagicMock(spec=Message)
    state = MagicMock()
    state.clear = AsyncMock()
    await gifts_mod.mylist_handler(msg, state)
    await gifts_mod.watchlist_handler(msg, state)
    assert mock_send.await_count == 2
    assert state.clear.await_count == 2


def test_gift_identity_from_session_includes_metadata_extra() -> None:
    settings = get_settings()
    ident = gift_identity_from_action_session(
        {
            "nft_address": "EQg",
            "collection_name": "Z",
            "nft_name": "Z #9",
            "address_kind": "getgems_gift_ref",
            "resolved_source": "getgems_web",
        },
        settings,
    )
    assert ident.metadata_extra and ident.metadata_extra.get("address_kind") == "getgems_gift_ref"


def test_snapshot_to_action_session_merges_address() -> None:
    s = snapshot_to_action_session({"nft_name": "A", "collection_name": "B"}, nft_address="EQz")
    assert s is not None
    assert s["nft_address"] == "EQz"
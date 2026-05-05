"""Inline /start hub: edit-in-place, no reply keyboard for the four hub buttons."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, User

from app.bot.handlers import start as start_mod
from app.bot.keyboards import (
    CB_START_BACK,
    CB_START_CHECK,
    CB_START_FEATURES,
    CB_START_HELP,
    CB_START_MYLIST,
    CB_START_UPGRADE,
    start_hub_inline_keyboard,
)
from app.bot.states import CheckNftFlow
from app.i18n import t


def test_start_uses_inline_keyboard_not_reply_keyboard() -> None:
    kb = start_hub_inline_keyboard(lang="ru")
    assert isinstance(kb, InlineKeyboardMarkup)
    assert not isinstance(kb, ReplyKeyboardMarkup)


def test_start_has_four_inline_buttons() -> None:
    kb = start_hub_inline_keyboard(lang="ru")
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert flat == [CB_START_CHECK, CB_START_MYLIST, CB_START_UPGRADE, CB_START_HELP]


@pytest.mark.asyncio
async def test_waiting_input_prefers_preview_card_over_full_report(monkeypatch: pytest.MonkeyPatch) -> None:
    state = MagicMock()
    state.clear = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.text = "https://tonviewer.com/nft/EQaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    msg.from_user = User(id=1, is_bot=False, first_name="t")

    preview = AsyncMock(return_value=True)
    exec_check = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.passive_gift.try_send_nft_preview_card", preview)
    monkeypatch.setattr(start_mod, "execute_check_payload", exec_check)

    await start_mod.nft_check_waiting_handler(msg, state)
    preview.assert_awaited_once()
    exec_check.assert_not_awaited()
    state.clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_features_edits_same_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(language_code="ru")))

    msg = MagicMock(spec=Message)
    msg.photo = None
    msg.edit_text = AsyncMock()
    msg.edit_caption = AsyncMock()
    msg.answer = AsyncMock()

    cq = MagicMock(spec=CallbackQuery)
    cq.data = CB_START_FEATURES
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    await start_mod.start_features_callback(cq, state)
    msg.edit_text.assert_awaited_once()
    msg.answer.assert_not_awaited()
    args, kwargs = msg.edit_text.await_args
    assert t("start.hub_features", "ru") in args[0] or args[0] == t("start.hub_features", "ru")


@pytest.mark.asyncio
async def test_start_help_edits_same_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(language_code="ru")))

    msg = MagicMock(spec=Message)
    msg.photo = None
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()

    cq = MagicMock(spec=CallbackQuery)
    cq.data = CB_START_HELP
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    await start_mod.start_help_callback(cq, state)
    msg.edit_text.assert_awaited_once()
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_back_returns_to_start_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(language_code="ru", role="user")))

    msg = MagicMock(spec=Message)
    msg.photo = None
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()
    msg.answer_photo = AsyncMock()

    cq = MagicMock(spec=CallbackQuery)
    cq.data = CB_START_BACK
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    await start_mod.start_back_callback(cq, state)
    msg.edit_text.assert_awaited_once()
    args, _ = msg.edit_text.await_args
    assert args[0] == t("start.main", "ru")


@pytest.mark.asyncio
async def test_start_check_edits_to_waiting_input_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(language_code="ru")))

    msg = MagicMock(spec=Message)
    msg.photo = None
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()

    cq = MagicMock(spec=CallbackQuery)
    cq.data = CB_START_CHECK
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await start_mod.start_check_callback(cq, state)
    state.set_state.assert_awaited_once_with(CheckNftFlow.waiting_input)
    msg.edit_text.assert_awaited_once()
    args, _ = msg.edit_text.await_args
    assert args[0] == t("start.hub_check_prompt", "ru")


@pytest.mark.asyncio
async def test_start_check_enters_existing_waiting_input_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(language_code="ru")))

    msg = MagicMock(spec=Message)
    msg.photo = None
    msg.edit_text = AsyncMock()

    cq = MagicMock(spec=CallbackQuery)
    cq.data = CB_START_CHECK
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await start_mod.start_check_callback(cq, state)
    state.set_state.assert_awaited_once_with(CheckNftFlow.waiting_input)
    state.update_data.assert_awaited()
    call_kw = state.update_data.await_args.kwargs
    assert call_kw.get("nft_check_restore_body") is None


def test_start_message_contains_tivonix_footer() -> None:
    assert "Powered by Tivonix" in t("start.main", "ru")
    assert "tivonix.tech" in t("start.main", "ru")


def test_start_no_mock_legacy_collections_json() -> None:
    body = t("start.main", "ru").lower()
    assert "mock" not in body
    assert "legacy" not in body
    assert "collections.json" not in body


@pytest.mark.asyncio
async def test_start_photo_uses_inline_keyboard_under_caption(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePath:
        def exists(self) -> bool:
            return True

        def __str__(self) -> str:
            return "hero.png"

    monkeypatch.setattr(start_mod, "_HERO_IMAGE_PATH", FakePath())
    monkeypatch.setattr(start_mod, "FSInputFile", lambda p: p)

    msg = MagicMock(spec=Message)
    msg.answer_photo = AsyncMock()

    await start_mod._send_start_main_with_hero(
        msg,
        text=t("start.main", "ru"),
        lang="ru",
        is_admin=False,
    )
    msg.answer_photo.assert_awaited_once()
    kb = msg.answer_photo.await_args.kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert CB_START_CHECK in flat and CB_START_BACK not in flat


@pytest.mark.asyncio
async def test_start_upgrade_passes_edit_message_to_carousel(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_send = AsyncMock()
    monkeypatch.setattr(start_mod, "send_upgrade_carousel_message", fake_send)

    msg = MagicMock(spec=Message)
    msg.photo = None
    cq = MagicMock(spec=CallbackQuery)
    cq.data = CB_START_UPGRADE
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    await start_mod.start_upgrade_callback(cq, state)
    fake_send.assert_awaited_once_with(msg, start_plan_key="pro", edit_message=msg)


@pytest.mark.asyncio
async def test_start_features_edits_caption_when_photo_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=MagicMock(language_code="ru")))

    msg = MagicMock(spec=Message)
    msg.photo = [MagicMock()]
    msg.edit_text = AsyncMock()
    msg.edit_caption = AsyncMock()
    msg.answer = AsyncMock()

    cq = MagicMock(spec=CallbackQuery)
    cq.data = CB_START_FEATURES
    cq.message = msg
    cq.from_user = User(id=1, is_bot=False, first_name="t")
    cq.answer = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    await start_mod.start_features_callback(cq, state)
    msg.edit_caption.assert_awaited_once()
    msg.edit_text.assert_not_awaited()

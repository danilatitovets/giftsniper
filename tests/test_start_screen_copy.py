from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, User

from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers import start as start_mod
from app.bot.keyboards import MENU_BTN_WATCHLIST, main_menu_keyboard, start_hub_inline_keyboard
from app.bot.states import CheckNftFlow
from app.i18n import t


def test_start_message_explains_link_or_address() -> None:
    body = t("start.main", "ru").lower()
    assert "ссылк" in body
    assert "getgems" in body
    assert "1️⃣" in t("start.main", "ru")


def test_start_message_does_not_promise_name_number_always_works() -> None:
    body = t("start.main", "ru").lower()
    assert "всегда работает" not in body
    assert "гарантия сделки" not in body


def test_start_message_has_safety_text() -> None:
    body = t("start.main", "ru").lower()
    assert "не покупаю" in body
    assert "не продаю" in body
    assert "seed" in body
    assert "private key" in body
    assert "доступ к кошельку" in body


def test_start_buttons_include_check_mylist_upgrade_help() -> None:
    kb = start_hub_inline_keyboard(lang="ru")
    assert isinstance(kb, InlineKeyboardMarkup)
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "🔎 Проверить NFT" in texts
    assert "🚀 Upgrade" in texts
    assert MENU_BTN_WATCHLIST in texts
    assert "❓ Помощь" in texts


def test_reply_menu_buttons_include_check_upgrade_mylist_help() -> None:
    kb = main_menu_keyboard(lang="ru", is_admin=False)
    rows = kb.keyboard
    assert len(rows) == 2
    assert rows[0][0].text == "🔎 Проверить NFT"
    assert rows[0][1].text == "🚀 Upgrade"
    flat = [b.text for row in rows for b in row]
    assert MENU_BTN_WATCHLIST in flat
    assert "❓ Помощь" in flat


@pytest.mark.asyncio
async def test_check_nft_button_enters_waiting_input_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    user_obj = MagicMock(language_code="ru")
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=user_obj))

    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1001, is_bot=False, first_name="u")
    msg.answer = AsyncMock()

    await start_mod.nft_check_menu_handler(msg, state)
    state.set_state.assert_awaited_once_with(CheckNftFlow.waiting_input)
    text = msg.answer.await_args.args[0]
    assert "Пришли ссылку на конкретный NFT" in text


@pytest.mark.asyncio
async def test_upgrade_button_opens_upgrade_carousel(monkeypatch: pytest.MonkeyPatch) -> None:
    state = MagicMock()
    state.clear = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    fake_send = AsyncMock()
    monkeypatch.setattr(start_mod, "send_upgrade_carousel_message", fake_send)
    await start_mod.menu_upgrade_handler(msg, state)
    fake_send.assert_awaited_once_with(msg, start_plan_key="pro")


@pytest.mark.asyncio
async def test_features_button_shows_features_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    user_obj = MagicMock(language_code="ru")
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=user_obj))
    state = MagicMock()
    state.clear = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1002, is_bot=False, first_name="u")
    msg.answer = AsyncMock()
    await start_mod.menu_features_handler(msg, state)
    assert "Возможности GiftSniper" in msg.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_help_button_shows_how_to_use_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    user_obj = MagicMock(language_code="ru")
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=user_obj))
    state = MagicMock()
    state.clear = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1003, is_bot=False, first_name="u")
    msg.answer = AsyncMock()
    await start_mod.menu_help_handler(msg, state)
    assert "Как пользоваться" in msg.answer.await_args.args[0]


def test_start_message_no_mock_legacy_collections_json() -> None:
    body = t("start.main", "ru").lower()
    assert "mock" not in body
    assert "legacy" not in body
    assert "collections.json" not in body


@pytest.mark.asyncio
async def test_start_photo_fallback_to_text_if_media_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePath:
        def exists(self) -> bool:
            return True

        def __str__(self) -> str:
            return str(Path("hero.png"))

    monkeypatch.setattr(start_mod, "_HERO_IMAGE_PATH", FakePath())
    monkeypatch.setattr(start_mod, "FSInputFile", lambda p: p)

    msg = MagicMock(spec=Message)
    msg.answer_photo = AsyncMock(side_effect=RuntimeError("telegram failed"))
    msg.answer = AsyncMock()

    await start_mod._send_start_main_with_hero(
        msg,
        text=t("start.main", "ru"),
        lang="ru",
        is_admin=False,
    )
    msg.answer.assert_awaited_once()
    rw = msg.answer.await_args.kwargs.get("reply_markup")
    assert isinstance(rw, InlineKeyboardMarkup)

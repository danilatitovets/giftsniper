"""MVP Telegram: команды меню, read-only тексты, /check через TonAPI."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import InlineKeyboardMarkup, Message, User

from app.bot.handlers import analysis
from app.bot.handlers.start import help_handler
from app.bot.keyboards import (
    CB_NFT_CHECK_BACK,
    CB_NFT_CHECK_CANCEL,
    CB_START_CHECK,
    MENU_BTN_HELP,
    MENU_BTN_UPGRADE,
    MENU_BTN_WATCHLIST,
    main_menu_keyboard,
    nft_check_prompt_inline_keyboard,
)
from app.bot.mvp_setup import MVP_COMMANDS, MVP_HELP, setup_mvp_bot_commands
from app.i18n import t as i18n_t


def test_bot_commands_mvp_list():
    names = tuple(c.command for c in MVP_COMMANDS)
    assert names == ("start", "check", "watch", "watchlist", "mylist", "settings", "help", "upgrade", "billing", "ref")


@pytest.mark.asyncio
async def test_setup_mvp_bot_commands_registers_only_mvp():
    bot = MagicMock()
    bot.set_my_commands = AsyncMock()
    await setup_mvp_bot_commands(bot)
    bot.set_my_commands.assert_awaited_once()
    args, kwargs = bot.set_my_commands.await_args
    cmds = [c.command for c in args[0]]
    assert cmds == ["start", "check", "watch", "watchlist", "mylist", "settings", "help", "upgrade", "billing", "ref"]


def test_help_has_only_mvp_commands():
    low = MVP_HELP.lower()
    for bad in ("buy", "sell", "wallet", "connect", "trade", "autobuy"):
        assert bad not in low


def test_commands_do_not_include_trading():
    blob = " ".join(f"{c.command} {c.description}" for c in MVP_COMMANDS).lower()
    for bad in ("buy", "sell", "wallet", "connect", "trade", "autobuy"):
        assert bad not in blob


def test_reply_menu_has_mvp_buttons():
    kb = main_menu_keyboard(lang="ru", is_admin=False)
    rows = kb.keyboard
    assert len(rows) == 2
    assert rows[0][0].text == "🔎 Проверить NFT"
    assert rows[0][1].text == "🚀 Upgrade"
    flat = [b.text for row in rows for b in row]
    assert MENU_BTN_WATCHLIST in flat
    assert "❓ Помощь" in flat


def test_start_text_explains_bot():
    text_body = i18n_t("start.main", "ru")
    low = text_body.lower()
    assert "giftsniper" in low
    assert "проверить" in low or "nft" in low
    assert "активные объявления" in low or "реальному рынку" in low
    assert "не покупаю" in low and "не продаю" in low
    assert "seed" in low
    assert "private key" in low


def test_start_main_lists_three_numbered_steps():
    body = i18n_t("start.main", "ru")
    assert "1️⃣" in body and "2️⃣" in body and "3️⃣" in body
    assert "getgems" in body.lower()


def test_help_read_only_safety():
    low = MVP_HELP.lower()
    assert "не покупает" in low
    assert "не прода" in low
    assert "кошел" in low


def test_read_only_texts():
    low_w = i18n_t("start.main", "ru").lower()
    low_h = MVP_HELP.lower()
    assert "рынк" in low_w
    assert "не покупаю" in low_w
    assert "tonapi" in low_h
    assert "не покупает" in low_h


@pytest.mark.asyncio
async def test_check_still_works_tonapi_route(monkeypatch):
    async def fake_deliver(message, *, telegram_id, username, payload, settings):
        await message.answer(f"tonapi_ok:{payload}")
        return ("done", True)

    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", fake_deliver)

    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    u = MagicMock(language_code="en")
    monkeypatch.setattr(analysis, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(analysis.UserRepository, "get_or_create", AsyncMock(return_value=u))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1, is_bot=False, first_name="t")
    msg.text = "/check Ice Cream #217467"
    msg.answer = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    await analysis.check_handler(msg, state)
    state.clear.assert_awaited_once()
    msg.answer.assert_awaited()
    first = msg.answer.await_args.args[0]
    assert first == "tonapi_ok:Ice Cream #217467"


@pytest.mark.asyncio
async def test_help_handler_sends_mvp_help(monkeypatch):
    from app.bot.handlers import start as start_mod

    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    u = MagicMock(language_code="ru")
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=u))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1, is_bot=False, first_name="t")
    msg.answer = AsyncMock()
    await help_handler(msg)
    msg.answer.assert_awaited_once_with(i18n_t("help.main", "ru"))


@pytest.mark.asyncio
async def test_start_handler_sends_mvp_welcome_only(monkeypatch):
    from app.bot.handlers import start as start_mod

    class FakeCM:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    fake_hero = MagicMock()
    fake_hero.exists = MagicMock(return_value=False)
    monkeypatch.setattr(start_mod, "_HERO_IMAGE_PATH", fake_hero)

    user_obj = MagicMock()
    user_obj.plan = "pro"
    user_obj.role = "user"
    user_obj.language_code = "ru"
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=user_obj))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1, is_bot=False, first_name="t")
    msg.text = "/start"
    msg.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    await start_mod.start_handler(msg, state, user_created_this_request=False)
    assert msg.answer.await_args.args[0] == i18n_t("start.main", "ru")
    kb = msg.answer.await_args.kwargs["reply_markup"]
    assert isinstance(kb, InlineKeyboardMarkup)
    flat_cb = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert CB_START_CHECK in flat_cb
    flat_txt = [b.text for row in kb.inline_keyboard for b in row]
    assert MENU_BTN_WATCHLIST in flat_txt
    assert MENU_BTN_HELP in flat_txt
    assert MENU_BTN_UPGRADE in flat_txt


def test_nft_check_prompt_inline_has_back_cancel_only():
    kb = nft_check_prompt_inline_keyboard(lang="ru")
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert CB_NFT_CHECK_CANCEL in data
    assert CB_NFT_CHECK_BACK in data
    assert len(data) == 2

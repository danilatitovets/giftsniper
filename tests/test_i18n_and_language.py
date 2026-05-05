"""i18n, выбор языка, миграция language_code."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, User

from app.bot.handlers import language as language_mod
from app.bot.handlers import start as start_mod
from app.bot.handlers import settings as settings_mod
from app.bot.keyboards import CB_SETTINGS_LANGUAGE, settings_stub_inline_keyboard
from app.bot.handlers import analysis as analysis_mod
from app.i18n import normalize_lang, safety_text_present, t


def test_migration_user_language_file_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    p = root / "alembic" / "versions" / "0032_user_language_code.py"
    assert p.is_file()
    body = p.read_text(encoding="utf-8")
    assert "language_code" in body
    assert "users" in body
    assert "add_column" in body


def test_i18n_fallback_to_english_for_missing_key() -> None:
    assert t("this.key.does.not.exist.anywhere", "ru") == "this.key.does.not.exist.anywhere"


def test_unknown_language_code_normalizes_to_en() -> None:
    assert normalize_lang("xx-Latn") == "en"


def test_bot_safety_text_translated() -> None:
    assert safety_text_present(t("start.main", "en"))
    assert safety_text_present(t("start.main", "ru"))
    assert safety_text_present(t("help.main", "en"))


@pytest.mark.asyncio
async def test_first_start_shows_language_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    user_obj = MagicMock(plan="free", role="user", language_code=None)
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=user_obj))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=101, is_bot=False, first_name="t")
    msg.text = "/start"
    msg.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    await start_mod.start_handler(msg, state, user_created_this_request=False)
    text = msg.answer.await_args.args[0]
    assert "Welcome to GiftSniper" in text
    assert "Choose your language" in text
    kb = msg.answer.await_args.kwargs.get("reply_markup")
    assert kb is not None
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "lang:set:en" in datas
    assert "lang:set:ru" in datas


@pytest.mark.asyncio
async def test_new_user_forces_language_selector_even_with_language_code(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    # Даже если по какой-то причине код языка уже заполнен,
    # для нового пользователя сначала показываем селектор.
    user_obj = MagicMock(plan="free", role="user", language_code="ru")
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=user_obj))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=102, is_bot=False, first_name="t")
    msg.text = "/start"
    msg.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    await start_mod.start_handler(msg, state, user_created_this_request=True)
    text = msg.answer.await_args.args[0]
    assert "Choose your language" in text


@pytest.mark.asyncio
async def test_language_selection_saves_preference(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    saved: dict[str, object] = {}

    class UR:
        def __init__(self, _s: object) -> None:
            pass

        async def set_language_code(self, tid: int, code: str, *, username: str | None = None) -> MagicMock:
            saved["tid"] = tid
            saved["code"] = code
            return MagicMock(role="user", plan="free")

    monkeypatch.setattr(language_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(language_mod, "UserRepository", UR)

    q = MagicMock(spec=CallbackQuery)
    q.from_user = User(id=202, is_bot=False, first_name="u", username="nu")
    q.data = "lang:set:ru"
    q.answer = AsyncMock()
    m = MagicMock()
    m.edit_text = AsyncMock()
    m.answer = AsyncMock()
    q.message = m

    await language_mod.language_set_callback(q)
    assert saved.get("code") == "ru"
    assert saved.get("tid") == 202


@pytest.mark.asyncio
async def test_start_uses_saved_language(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    user_obj = MagicMock(plan="free", role="user", language_code="ru")
    monkeypatch.setattr(start_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(start_mod.UserRepository, "get_or_create", AsyncMock(return_value=user_obj))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=303, is_bot=False, first_name="t")
    msg.text = "/start"
    msg.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    await start_mod.start_handler(msg, state, user_created_this_request=False)
    text = msg.answer.await_args.args[0]
    assert "GiftSniper" in text
    assert "реальному рынку" in text


def test_settings_stub_has_language_callback() -> None:
    kb = settings_stub_inline_keyboard(lang="en")
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert CB_SETTINGS_LANGUAGE in flat


@pytest.mark.asyncio
async def test_change_language_from_settings_opens_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    q = MagicMock(spec=CallbackQuery)
    q.from_user = User(id=1, is_bot=False, first_name="x")
    q.answer = AsyncMock()
    m = MagicMock()
    m.edit_text = AsyncMock()
    m.answer = AsyncMock()
    q.message = m
    q.data = CB_SETTINGS_LANGUAGE
    await language_mod.settings_language_open(q)
    m.edit_text.assert_awaited()
    args = m.edit_text.await_args.args
    assert "Welcome to GiftSniper" in args[0]


@pytest.mark.asyncio
async def test_existing_check_not_broken(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_deliver(message: object, *, telegram_id: int, username: str | None, payload: str, settings: object):
        await message.answer(f"tonapi_ok:{payload}")
        return ("done", True)

    monkeypatch.setattr(analysis_mod.gift_flow, "deliver_nft_check_tonapi_only", fake_deliver)

    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    u = MagicMock(language_code="en")
    monkeypatch.setattr(analysis_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(analysis_mod.UserRepository, "get_or_create", AsyncMock(return_value=u))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1, is_bot=False, first_name="t")
    msg.text = "/check Ice Cream #217467"
    msg.answer = AsyncMock()
    await analysis_mod.check_handler(msg, AsyncMock())
    msg.answer.assert_awaited()
    assert "tonapi_ok:Ice Cream #217467" in msg.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_settings_screen_has_language_button_label(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    u = MagicMock(language_code="ru")
    monkeypatch.setattr(settings_mod, "SessionLocal", lambda: FakeCM())
    monkeypatch.setattr(settings_mod.UserRepository, "get_or_create", AsyncMock(return_value=u))

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1, is_bot=False, first_name="t")
    msg.answer = AsyncMock()
    await settings_mod.send_mvp_settings_screen(msg)
    kb = msg.answer.await_args.kwargs["reply_markup"]
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Язык" in x or "Language" in x for x in texts)


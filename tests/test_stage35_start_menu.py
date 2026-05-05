"""Stage 35: /start structure and main menu keyboard (MVP)."""

from app.bot.keyboards import MENU_BTN_WATCHLIST, main_menu_keyboard, nft_check_prompt_inline_keyboard
from app.bot.messages import WELCOME_TEXT


def test_welcome_has_disclaimer_and_no_profit_guarantee():
    assert "GiftSniper" in WELCOME_TEXT
    assert "Не финансовый совет" in WELCOME_TEXT


def test_main_menu_has_mvp_buttons():
    kb = main_menu_keyboard(lang="ru", is_admin=False)
    rows = kb.keyboard
    assert len(rows) == 2
    assert rows[0][0].text == "🔎 Проверить NFT"
    assert rows[0][1].text == "🚀 Upgrade"
    flat = [b.text for row in rows for b in row]
    assert MENU_BTN_WATCHLIST in flat
    assert "❓ Помощь" in flat


def test_main_menu_admin_same_as_user_keyboard():
    """Админ-кнопки убраны из reply-меню; админские команды вводятся вручную."""
    kb_user = main_menu_keyboard(lang="ru", is_admin=False)
    kb_admin = main_menu_keyboard(lang="ru", is_admin=True)
    assert kb_user.keyboard == kb_admin.keyboard


def test_nft_check_prompt_inline_actions():
    kb = nft_check_prompt_inline_keyboard(lang="ru")
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "check_nft:cancel" in data
    assert "check_nft:back" in data
    assert "check_nft:demo" not in data

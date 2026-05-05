"""Inline-кнопки и короткие тексты для Upgrade / лимитов (без импорта handlers)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import normalize_lang, t

CB_UPGRADE_OPEN = "upgrade:open"
CB_UPGRADE_PREV = "upgrade:prev"
CB_UPGRADE_NEXT = "upgrade:next"
CB_UPGRADE_BUY = "upgrade:buy"
CB_UPGRADE_BACK = "upgrade:back"
CB_PAY_CHECK = "payment:check"
CB_PAY_REFRESH = "payment:refresh"
CB_PAY_CANCEL = "payment:cancel"


def upgrade_inline_keyboard_open(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("upgrade.billing_upgrade", lg), callback_data=CB_UPGRADE_OPEN)]
        ]
    )


def daily_check_limit_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    """Лимит рыночных проверок: Upgrade + Назад (тот же callback, что и у карусели)."""
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("upgrade.billing_upgrade", lg), callback_data=CB_UPGRADE_OPEN)],
            [InlineKeyboardButton(text=t("upgrade.back_button", lg), callback_data=CB_UPGRADE_BACK)],
        ]
    )


def format_daily_checks_limit_message(limit: int, *, lang: str | None = None, settings: object | None = None) -> str:
    from app.config import get_settings

    lg = normalize_lang(lang)
    s = settings or get_settings()
    return t(
        "limit.market_checks_body",
        lg,
        limit=limit,
        free_checks=int(s.plan_free_daily_nft_checks),
        pro_checks=int(s.plan_pro_daily_nft_checks),
        sniper_checks=int(s.plan_sniper_daily_nft_checks),
    )


def format_watchlist_limit_message(
    plan_label: str,
    max_allowed: int,
    *,
    cur: int | None = None,
    lang: str | None = None,
    settings: object | None = None,
) -> str:
    from app.config import get_settings

    lg = normalize_lang(lang)
    s = settings or get_settings()
    body = t(
        "limit.watchlist_block",
        lg,
        plan=plan_label,
        max=max_allowed,
        free_wl=int(s.plan_free_watchlist_limit),
        pro_wl=int(s.plan_pro_watchlist_limit),
        sniper_wl=int(s.plan_sniper_watchlist_limit),
    )
    if cur is not None:
        body += t("limit.watchlist_suffix", lg, cur=cur, max=max_allowed)
    return body

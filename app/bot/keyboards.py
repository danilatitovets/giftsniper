from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.bot.upgrade_inline import CB_UPGRADE_OPEN
from app.i18n import SUPPORTED_LANGUAGE_CODES, main_menu_labels_union, normalize_lang, t

# Совместимость: старые обработчики / тесты могли ссылаться на константу
NFT_CHECK_MENU_BUTTON = "🔎 Проверить NFT"

CB_EMPTY_WL_CHECK = "ux_empty_wl:check"
CB_EMPTY_WL_WATCH = "ux_empty_wl:watch"
CB_EMPTY_WL_BACK = "ux_empty_wl:back"
CB_SETTINGS_STUB_CHECK = "ux_settings:check"
CB_SETTINGS_STUB_WATCHLIST = "ux_settings:watchlist"
CB_SETTINGS_STUB_BACK = "ux_settings:back"
CB_SETTINGS_LANGUAGE = "ux_settings:language"
CB_NFT_CHECK_BACK = "check_nft:back"
CB_NFT_CHECK_CANCEL = "check_nft:cancel"
CB_START_CHECK = "start:check"
CB_START_UPGRADE = "start:upgrade"
CB_START_FEATURES = "start:features"
CB_START_HELP = "start:help"
CB_START_BACK = "start:back"
CB_START_MYLIST = "start:mylist"
CB_START_REFERRAL = "start:referral"
CB_REF_REFRESH = "ref:refresh"
CB_UX_CLOSE_MESSAGE = "ux:close_message"


def main_menu_keyboard(*, lang: str | None = None, is_admin: bool = False) -> ReplyKeyboardMarkup:
    _ = is_admin
    lg = normalize_lang(lang)
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text=t("start.check_button", lg)),
            KeyboardButton(text=t("start.upgrade_button", lg)),
        ],
        [
            KeyboardButton(text=t("start.watchlist_button", lg)),
            KeyboardButton(text=t("start.help_button", lg)),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def start_info_inline_keyboard(*, lang: str | None = None, with_upgrade: bool = True) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    rows: list[list[InlineKeyboardButton]] = [[
        InlineKeyboardButton(text=t("start.check_button", lg), callback_data=CB_START_CHECK),
    ]]
    if with_upgrade:
        rows.append([InlineKeyboardButton(text=t("start.upgrade_button", lg), callback_data=CB_START_UPGRADE)])
    rows.append([InlineKeyboardButton(text=t("start.back_button", lg), callback_data=CB_START_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def start_hub_inline_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    """Главный экран /start: четыре inline-кнопки (не ReplyKeyboard)."""
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("start.check_button", lg), callback_data=CB_START_CHECK),
                InlineKeyboardButton(text=t("start.watchlist_button", lg), callback_data=CB_START_MYLIST),
            ],
            [
                InlineKeyboardButton(text=t("start.upgrade_button", lg), callback_data=CB_START_UPGRADE),
                InlineKeyboardButton(text=t("start.help_button", lg), callback_data=CB_START_HELP),
            ],
        ]
    )


def start_hub_back_only_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("start.back_button", lg), callback_data=CB_START_BACK)]]
    )


def start_hub_features_nav_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("start.check_button", lg), callback_data=CB_START_CHECK),
                InlineKeyboardButton(text=t("start.watchlist_button", lg), callback_data=CB_START_MYLIST),
            ],
            [
                InlineKeyboardButton(text=t("start.upgrade_button", lg), callback_data=CB_START_UPGRADE),
            ],
            [InlineKeyboardButton(text=t("start.back_button", lg), callback_data=CB_START_BACK)],
        ]
    )


def start_hub_help_nav_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("start.check_button", lg), callback_data=CB_START_CHECK)],
            [InlineKeyboardButton(text=t("start.features_button", lg), callback_data=CB_START_FEATURES)],
            [InlineKeyboardButton(text=t("start.referral_button", lg), callback_data=CB_START_REFERRAL)],
            [InlineKeyboardButton(text=t("start.back_button", lg), callback_data=CB_START_BACK)],
        ]
    )


def referral_program_inline_keyboard(*, lang: str | None, ref_link: str, share_url: str) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("referral.share_button", lg), url=share_url)],
            [InlineKeyboardButton(text=t("referral.refresh_button", lg), callback_data=CB_REF_REFRESH)],
        ]
    )


def main_menu_keyboard_legacy(*, lang: str | None = None, is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Legacy menu preserved for compatibility in older tests/flows."""
    _ = is_admin
    lg = normalize_lang(lang)
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=t("start.check_button", lg))],
        [
            KeyboardButton(text=t("start.watchlist_button", lg)),
            KeyboardButton(text=t("start.settings_button", lg)),
        ],
        [KeyboardButton(text=t("start.help_button", lg))],
        [KeyboardButton(text=t("start.upgrade_button", lg))],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def serialize_inline_keyboard(kb: InlineKeyboardMarkup | None) -> list[list[dict[str, str]]] | None:
    """Снимок inline-клавиатуры для FSM (только callback-кнопки)."""
    if kb is None or not kb.inline_keyboard:
        return None
    out: list[list[dict[str, str]]] = []
    for row in kb.inline_keyboard:
        r2: list[dict[str, str]] = []
        for b in row:
            if b.callback_data:
                r2.append({"text": b.text, "callback_data": b.callback_data})
        if r2:
            out.append(r2)
    return out or None


def deserialize_inline_keyboard(data: list[list[dict[str, str]]] | None) -> InlineKeyboardMarkup | None:
    if not data:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for row in data:
        rows.append(
            [InlineKeyboardButton(text=x["text"], callback_data=x["callback_data"]) for x in row]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nft_check_prompt_inline_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("nft.btn_back", lg), callback_data=CB_NFT_CHECK_BACK),
                InlineKeyboardButton(text=t("nft.btn_cancel", lg), callback_data=CB_NFT_CHECK_CANCEL),
            ],
        ]
    )


def empty_watchlist_inline_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("start.check_button", lg), callback_data=CB_EMPTY_WL_CHECK)],
            [
                InlineKeyboardButton(
                    text=t("start.watchlist_button", lg),
                    callback_data=CB_EMPTY_WL_WATCH,
                ),
                InlineKeyboardButton(text=t("nft.btn_back", lg), callback_data=CB_EMPTY_WL_BACK),
            ],
        ]
    )


def settings_stub_inline_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("start.check_button", lg), callback_data=CB_SETTINGS_STUB_CHECK)],
            [
                InlineKeyboardButton(
                    text=t("start.watchlist_button", lg),
                    callback_data=CB_SETTINGS_STUB_WATCHLIST,
                ),
                InlineKeyboardButton(text=t("nft.btn_back", lg), callback_data=CB_SETTINGS_STUB_BACK),
            ],
            [
                InlineKeyboardButton(
                    text=t("settings.language_button", lg),
                    callback_data=CB_SETTINGS_LANGUAGE,
                ),
            ],
            [InlineKeyboardButton(text=t("start.upgrade_button", lg), callback_data=CB_UPGRADE_OPEN)],
        ]
    )


def my_list_after_add_inline_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("mylist.btn_open_list", lg), callback_data=CB_START_MYLIST),
                InlineKeyboardButton(text=t("mylist.btn_check_market", lg), callback_data=CB_START_CHECK),
            ],
            [InlineKeyboardButton(text=t("mylist.btn_close", lg), callback_data=CB_UX_CLOSE_MESSAGE)],
        ]
    )


def my_list_limit_inline_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("start.upgrade_button", lg), callback_data=CB_UPGRADE_OPEN)],
            [InlineKeyboardButton(text=t("mylist.btn_open_list", lg), callback_data=CB_START_MYLIST)],
        ]
    )


def my_list_session_expired_inline_keyboard(*, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("start.check_button", lg), callback_data=CB_START_CHECK)]]
    )


MAIN_MENU_ALL_LABELS: frozenset[str] = main_menu_labels_union()


def _labels_for(key: str) -> frozenset[str]:
    return frozenset(t(key, lg) for lg in SUPPORTED_LANGUAGE_CODES)


WATCHLIST_MENU_LABELS: frozenset[str] = _labels_for("start.watchlist_button")
SETTINGS_MENU_LABELS: frozenset[str] = _labels_for("start.settings_button")
HELP_MENU_LABELS: frozenset[str] = _labels_for("start.help_button")
UPGRADE_MENU_LABELS: frozenset[str] = _labels_for("start.upgrade_button")
NFT_CHECK_MENU_LABELS: frozenset[str] = _labels_for("start.check_button")
FEATURES_MENU_LABELS: frozenset[str] = _labels_for("start.features_button")

# Экспорт для обратной совместимости имён кнопок (русский вариант как в legacy)
MENU_BTN_CHECK = t("start.check_button", "ru")
MENU_BTN_WATCHLIST = t("start.watchlist_button", "ru")
MENU_BTN_SETTINGS = t("start.settings_button", "ru")
MENU_BTN_HELP = t("start.help_button", "ru")
MENU_BTN_UPGRADE = t("start.upgrade_button", "ru")
MENU_BTN_FEATURES = t("start.features_button", "ru")

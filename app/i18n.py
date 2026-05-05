"""Простой i18n: ключи вида ``start.main``, fallback на English.

Строки кэшируются на весь жизненный цикл процесса (см. ``lru_cache`` ниже). После правок в этом файле
нужен полный перезапуск бота; для локальной разработки удобно ``python -m app.main --reload``.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

# Коды языков MVP (совпадают с callback lang:set:xx)
SUPPORTED_LANGUAGE_CODES: tuple[str, ...] = ("en", "ru", "es", "tr", "pt", "fr", "de", "ar", "hi", "id")

LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"title": "English", "flag": "🇬🇧"},
    "ru": {"title": "Русский", "flag": "🇷🇺"},
    "es": {"title": "Español", "flag": "🇪🇸"},
    "tr": {"title": "Türkçe", "flag": "🇹🇷"},
    "pt": {"title": "Português", "flag": "🇵🇹"},
    "fr": {"title": "Français", "flag": "🇫🇷"},
    "de": {"title": "Deutsch", "flag": "🇩🇪"},
    "ar": {"title": "العربية", "flag": "🇸🇦"},
    "hi": {"title": "हिन्दी", "flag": "🇮🇳"},
    "id": {"title": "Bahasa Indonesia", "flag": "🇮🇩"},
}


def normalize_lang(code: str | None) -> str:
    if not code:
        return "en"
    c = str(code).strip().lower().replace("-", "_")
    if "_" in c:
        c = c.split("_", 1)[0]
    if c in SUPPORTED_LANGUAGE_CODES:
        return c
    return "en"


def text_lang_from_user(user: Any) -> str:
    """Язык UI: пока пользователь не выбрал язык — английский для /help и т.д."""
    lc = getattr(user, "language_code", None)
    if lc is None or not str(lc).strip():
        return "en"
    return normalize_lang(str(lc))


def _fmt(template: str, kwargs: dict[str, Any]) -> str:
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError, IndexError):
        return template


@lru_cache(maxsize=1)
def _strings_en() -> dict[str, str]:
    return {
        "onboarding.choose_language": (
            "👋 Welcome to GiftSniper\n\n"
            "I help you check NFT / Telegram Gifts using real market listings from TonAPI.\n\n"
            "Choose your language to continue:"
        ),
        "start.main": (
            "🎯 GiftSniper\n\n"
            "I help you estimate a fair listing price for an NFT / Telegram Gift from real market data.\n\n"
            "✨ After a check you will see:\n"
            "🎁 NFT preview;\n"
            "🧬 traits;\n"
            "💎 current listing;\n"
            "🔎 analysis of similar NFTs;\n"
            "💰 price guide: quick / normal / high.\n\n"
            "📌 How to check:\n"
            "1️⃣ Open the NFT on Getgems, Fragment, or Tonviewer.\n"
            "2️⃣ Copy the link to that exact NFT.\n"
            "3️⃣ Send it here in the chat.\n\n"
            "🔐 Safety:\n"
            "I do not buy or sell NFTs.\n"
            "I never ask for a seed phrase, private key, or wallet access.\n\n"
            "Powered by Tivonix · tivonix.tech"
        ),
        "start.hub_check_prompt": (
            "🔎 NFT check\n\n"
            "Send a link to a specific NFT from Getgems, Fragment, or Tonviewer.\n\n"
            "Best: a link to the NFT itself, not the collection page.\n\n"
            "Then I will show the NFT card and action buttons."
        ),
        "start.hub_features": (
            "📊 GiftSniper features\n\n"
            "• finds an NFT by link;\n"
            "• shows preview, traits, and current listing;\n"
            "• scans active collection listings;\n"
            "• compares similar NFTs;\n"
            "• filters overpriced outliers;\n"
            "• estimates price: quick / normal / high;\n"
            "• shows estimate confidence.\n\n"
            "Important: the estimate is based on active listings; it is not a guarantee of a sale."
        ),
        "start.hub_help": (
            "❓ How to use\n\n"
            "1. Open the NFT on Getgems, Fragment, or Tonviewer.\n"
            "2. Copy the link to that exact NFT.\n"
            "3. Send the link to this chat.\n"
            "4. The bot shows the NFT card.\n"
            "5. Tap “🔎 Check market” for a price estimate.\n\n"
            "🔐 I never ask for a seed phrase, private key, or wallet access."
        ),
        "start.check_button": "🔎 Check NFT",
        "start.watchlist_button": "📋 My list",
        "start.settings_button": "⚙️ Settings",
        "start.features_button": "📊 Features",
        "start.help_button": "❓ Help",
        "start.upgrade_button": "🚀 Upgrade",
        "start.back_button": "⬅️ Back",
        "start.features_text": (
            "📊 GiftSniper features\n\n"
            "• finds an NFT by link;\n"
            "• shows preview, traits, and current listing;\n"
            "• scans active collection listings;\n"
            "• compares similar NFTs;\n"
            "• filters overpriced outliers;\n"
            "• estimates price: quick / normal / high;\n"
            "• shows estimate confidence.\n\n"
            "Important: the estimate is based on active listings; it is not a guarantee of a sale."
        ),
        "start.help_short_text": (
            "❓ How to use\n\n"
            "1. Open the NFT on Getgems, Fragment, or Tonviewer.\n"
            "2. Copy the link to that exact NFT.\n"
            "3. Send the link to this chat.\n"
            "4. The bot shows the NFT card.\n"
            "5. Tap “🔎 Check market” for a price estimate.\n\n"
            "🔐 I never ask for a seed phrase, private key, or wallet access."
        ),
        "help.main": (
            "❓ How to use GiftSniper\n\n"
            "Main flow:\n"
            "Send a link to an exact NFT (Getgems / Fragment / Tonviewer) or NFT address.\n\n"
            "You get an NFT preview (animation, video, or image) and a TonAPI market readout.\n\n"
            "Name like Ice Cream #217467 may work if collection is already in local index.\n\n"
            "Commands:\n"
            "/check — check an NFT\n"
            "/watch — add to watchlist\n"
            "/watchlist — my watchlist\n"
            "/settings — settings\n"
            "/upgrade — plans & TON payment\n"
            "/billing — subscription & limits\n"
            "/ref — invite friends & bonus NFT checks\n"
            "/help — help\n\n"
            "Important:\n"
            "GiftSniper shows a market estimate from active TonAPI listings.\n"
            "This is not a guarantee of sale or financial advice.\n\n"
            "The bot does not buy, sell, or ask for wallet access."
        ),
        "start.referral_button": "👥 Invite friends",
        "referral.program_body": (
            "👥 Referral program\n\n"
            "Your link:\n"
            "{link}\n\n"
            "How it works:\n"
            "+{per} bonus NFT checks per invited friend.\n"
            "Every {every_n} friends: +{milestone} extra.\n\n"
            "Invited friends: {invited}\n"
            "Bonus checks available: {bonus}"
        ),
        "referral.share_text": "Check your Telegram Gift / NFT price with this bot",
        "referral.share_button": "📤 Share link",
        "referral.refresh_button": "🔄 Refresh",
        "referral.bonus_check_used": "Bonus NFT check used. Remaining: {remaining}",
        "settings.main": (
            "⚙️ Settings\n\n"
            "NFT checks use TonAPI (read-only).\n\n"
            "Soon: listing alerts and scan frequency.\n\n"
            "For now:\n"
            "• /check — check an NFT\n"
            "• /watch — add to watchlist\n"
            "• /watchlist — watchlist"
        ),
        "settings.language_button": "🌐 Language",
        "settings.language_confirm": "Language updated to: {title}",
        "settings.open_menu": "OK. Use the menu buttons below.",
        "upgrade.carousel_free": (
            "🌱 Free\n\n"
            "0 TON\n"
            "{checks} market checks / day\n"
            "{wl} NFT in watchlist\n"
            "Preview is free\n\n"
            "Scan: cache first, basic/fast when needed."
        ),
        "upgrade.carousel_pro": (
            "🚀 Pro\n\n"
            "{price} TON / month ({days} days)\n"
            "{checks} market checks / day\n"
            "{wl} NFT in watchlist\n"
            "Full / auto market scan\n"
            "Basic alerts\n"
            "Higher limits than Free"
        ),
        "upgrade.carousel_sniper": (
            "🎯 Sniper\n\n"
            "{price} TON / month ({days} days)\n"
            "{checks} market checks / day\n"
            "{wl} NFT in watchlist\n"
            "Max / full market scan\n"
            "Smart alerts\n"
            "Highest limits in MVP"
        ),
        "upgrade.nav_current_free": "Current plan",
        "upgrade.nav_current_plan": "Current plan",
        "upgrade.nav_go_pro": "Go to Pro →",
        "upgrade.pay_pro": "Pay Pro",
        "upgrade.pay_sniper": "Pay Sniper",
        "upgrade.pay_buy_short": "💎 Buy",
        "upgrade.pay_renew_short": "💎 Renew",
        "upgrade.nav_sniper_right": "Sniper ➡️",
        "upgrade.nav_back_pro": "⬅️ Pro",
        "upgrade.back_button": "⬅️ Back",
        "upgrade.billing_upgrade": "🚀 Upgrade",
        "upgrade.billing_renew": "🔄 Renew",
        "upgrade.billing_back": "🔙 Back",
        "billing.title": "💳 My subscription",
        "billing.limits_section": "Limits:",
        "billing.plan": "Plan: {plan}",
        "billing.active_until": "Active until: {date}",
        "billing.limits_checks": "• Checks today: {used} / {max}",
        "billing.limits_watchlist": "• My list: {used} / {max}",
        "billing.payment_note": "Payment: TON",
        "billing.no_autorenew": "No auto-renewal.",
        "payment.instruction_title": "💎 Pay for {plan}",
        "payment.send_amount": "Send exactly: {amount} TON",
        "payment.to_address": "To address:",
        "payment.comment_line": "Transfer comment:",
        "payment.notes_header": "Important:",
        "payment.note_comment": "• comment is required;",
        "payment.note_ton_only": "• send TON only;",
        "payment.note_activate": "• subscription activates after the transaction is confirmed;",
        "payment.note_no_wallet": "• the bot never asks for a seed phrase, private key, or wallet access.",
        "payment.after_pay_hint": 'After paying, tap "Check payment".',
        "payment.btn_check": "✅ Check payment",
        "payment.btn_refresh": "🔄 Refresh invoice",
        "payment.btn_cancel": "❌ Cancel",
        "payment.not_found": (
            "⏳ Payment not found yet.\n\n"
            "Check:\n"
            "• amount sent in TON;\n"
            "• comment matches exactly;\n"
            "• wait 1–2 minutes after transfer.\n\n"
            "Tap “Check payment” again."
        ),
        "payment.found_header": "✅ Payment received. Plan activated.\n\n",
        "payment.found_until": "Plan {plan} active until {date}.\n\n",
        "payment.found_features": (
            "Now available:\n"
            "• up to {checks} NFT checks per day\n"
            "• up to {wl} NFT in watchlist\n"
            "• cheap listing alerts (per your settings)\n"
        ),
        "payment.already_confirmed": "✅ This payment was already confirmed.\nPlan {plan} active until {date}.",
        "payment.invoice_expired": "⏳ This invoice expired.\nCreate a new one via 🚀 Upgrade.",
        "payment.cancelled": "Invoice cancelled. Create a new one via Upgrade if needed.",
        "payment.cannot_create": "Could not create invoice. Try again later.",
        "payment.payment_disabled": "TON payments are disabled.",
        "payment.receiver_not_configured": "Receiver address is not configured.",
        "payment.tx_already_used": "This transaction was already recorded.",
        "payment.invoice_invalid": "This invoice is no longer valid. Create a new one via Upgrade.",
        "payment.user_error": "User error.",
        "payment.invoice_not_found": "Invoice not found.",
        "payment.invoice_error": "Invoice error.",
        "payment.invoice_unavailable": "Invoice unavailable.",
        "payment.refresh_ok": "Updated",
        "payment.cancel_toast": "Cancelled",
        "limit.market_checks_body": (
            "🚫 Daily market check limit reached\n\n"
            "On your plan you have: {limit} market checks per day.\n\n"
            "Free: {free_checks} checks / day\n"
            "Pro: {pro_checks} checks / day\n"
            "Sniper: {sniper_checks} checks / day\n\n"
            "NFT preview stays free.\n"
            "Upgrade to Pro or Sniper for more checks."
        ),
        "limit.watchlist_block": (
            "🚫 Watchlist limit\n\n"
            "On your plan you can track up to {max} NFT in the watchlist.\n"
            "Upgrade to Pro or Sniper to add more.\n\n"
            "Free: {free_wl} NFT\n"
            "Pro: {pro_wl} NFT\n"
            "Sniper: {sniper_wl} NFT"
        ),
        "limit.watchlist_suffix": "\n\nYou have: {cur} / {max}.",
        "notifications.btn": "🔔 Notifications",
        "notifications.status_on": "Notifications: on",
        "notifications.status_off": "Notifications: off",
        "notifications.enabled_title": "🔔 Notifications on",
        "notifications.enabled_body": (
            "I'll watch the market for this NFT and message you if the price estimate changes meaningfully."
        ),
        "notifications.disabled_title": "🔕 Notifications off",
        "notifications.disabled_body": "I won't send market updates for this NFT anymore.",
        "notifications.free_gate": (
            "🔔 Notifications are available on Pro and Sniper\n\n"
            "I can watch the market for your NFT and notify you when the price estimate changes a lot.\n\n"
            "Pro: at most one check every 6 hours\n"
            "Sniper: at most one check every hour\n"
        ),
        "notifications.push_up": (
            "🔔 Market moved up\n\n<b>{name}</b>\n\n"
            "Price estimate went up:\n"
            "Was: ~{was} TON\n"
            "Now: ~{now} TON\n"
            "Change: +{pct}%\n\n"
            "This isn't a sale guarantee — it's based on active listings."
        ),
        "notifications.push_down": (
            "⚠️ Market moved down\n\n<b>{name}</b>\n\n"
            "Price estimate went down:\n"
            "Was: ~{was} TON\n"
            "Now: ~{now} TON\n"
            "Change: -{pct}%\n\n"
            "It may be better not to list far above the market right now."
        ),
        "notifications.btn_check_now": "🔎 Check now",
        "notifications.btn_turn_off": "🔕 Turn off notifications",
        "notifications.toast_off": "Notifications turned off",
        "check.waiting_input": (
            "Send a link to the exact NFT on Getgems / Fragment / Tonviewer or NFT address.\n\n"
            "Best option is a link to the NFT itself, not a collection."
        ),
        "check.need_payload": "Send text: link, NFT address, or “Collection #number”. Example: /check Ice Cream #217467",
        "check.wait_market_caption": (
            "Collecting <b>active listing prices</b> from the market.\n"
            "This step can take up to a couple of minutes for large collections — nothing is wrong."
        ),
        "nft.btn_back": "🔙 Back",
        "nft.btn_cancel": "❌ Cancel",
        "nft.btn_demo": "🎁 Example",
        "watchlist.empty": (
            "📋 My list is empty\n\n"
            "Add an NFT: send a link to the NFT, then tap the add button on the card.\n\n"
            "You can also use /watch or /add with an address or link."
        ),
        "mylist.btn_open_list": "📋 My list",
        "mylist.btn_check_market": "🔎 Check market",
        "mylist.btn_close": "❌ Close",
        "mylist.added_title": "✅ Added to my list",
        "mylist.added_hint": "You can open it anytime from «📋 My list».",
        "mylist.already_title": "ℹ️ This NFT is already in your list.",
        "mylist.already_hint": "",
        "mylist.line_gift": "🎁 {name}",
        "mylist.line_collection": "Collection: {collection}",
        "mylist.session_expired": (
            "⚠️ This card has expired.\n\n"
            "Send the NFT link again — I will open the card."
        ),
        "mylist.header": "📋 My list\n",
        "mylist.list_hint": "Each row: 🔎 Check — run a fresh market report for that NFT.",
        "mylist.btn_row_market": "🔎 Check",
        "mylist.btn_add_from_check": "✅ Add to list",
        "progress.collection_fallback": "Collection",
        "progress.simple_title_named": "⏳ Analyzing the market\n\n",
        "progress.simple_title_plain": "⏳ Analyzing the market\n\n",
        "progress.simple_collection_named": "Collection: {coll}\n\n",
        "progress.simple_intro": (
            "I'm looking at open listings for this collection via TonAPI.\n\n"
        ),
        "progress.simple_checked": "Already reviewed: {loaded} NFT\n",
        "progress.simple_checked_approx": "Already reviewed: {loaded} of ~{total} NFT\n",
        "progress.simple_listings": "Listings found: {listings}\n\n",
        "progress.simple_slow": "This can take 1–2 minutes for large collections.\n",
        "progress.simple_wallet": "No wallet or seed phrase needed.",
        "progress.start": (
            "⏳ Analyzing the market\n\n"
            "I'm checking real listings for sale and looking for similar NFTs.\n\n"
            "Reviewed: {loaded} NFT\n"
            "Listings found: {listings}\n\n"
            "Large collections can take 1–2 minutes.\n"
            "🔒 No wallet or seed phrase needed."
        ),
        "progress.scan_head": "⏳ Checking collection market\n\n“{coll}”\n\n",
        "progress.scan_hint": (
            "\nNo wallet/seed needed.\n"
            "This message will be updated as data loads."
        ),
        "progress.ratelimit_user": (
            "⏳ Short pause\n\n"
            "<b>“{coll}”</b>\n"
            "• NFT already in sample: <b>{loaded}</b>\n"
            "• With a sale price: <b>{listings}</b>\n\n"
            "Continuing — no action needed from you."
        ),
        "progress.ratelimit_user_plain": (
            "⏳ Short pause\n\n"
            "• NFT already in sample: <b>{loaded}</b>\n"
            "• With a sale price: <b>{listings}</b>\n\n"
            "Continuing — no action needed from you."
        ),
        "progress.ratelimit_title": "⏳ Short pause\n\n",
        "progress.ratelimit_body": "The service briefly limited speed — continuing.\n\n",
        "progress.ratelimit_stats": "“{coll}”\n• In sample: {loaded} NFT\n• Listed with price: {listings}\n",
        "progress.page_limit": "• Page limit: {limit}\n",
        "progress.page_note": "\n{note}\n",
        "progress.ratelimit_footer": "\nFull collection scan",
        "progress.scan_title": "⏳ Scanning collection (detailed)\n\n",
        "progress.scan_loaded_approx": "Loaded: {loaded} of ~{total} NFT\n",
        "progress.scan_loaded": "Loaded: {loaded} NFT\n",
        "progress.scan_listings": "Active listings: {listings}\n",
        "progress.scan_mode": "Mode: full scan\n",
        "progress.scan_page_limit": "Page limit: {limit}\n",
        "progress.scan_note": "{note}\n",
        "progress.scan_source": "Source: public listings",
        "progress.default": (
            "⏳ “{coll}”\n\n"
            "• NFT in sample: {loaded}\n"
            "• Listed with price: {listings}\n\n"
            "Next — finding similar by model, backdrop, and symbol…"
        ),
        "upgrade.ok_menu": "OK. Menu buttons are at the bottom again.",
        "upgrade.unavailable": "Unavailable",
        "nft.flow_cancelled": "Cancelled",
        "nft.flow_back_ok": "OK. Pick an action with the buttons below.",
        "nft.flow_check_closed": "Done.",
        "nft.flow_cancel_hint": 'OK. Tap “Check NFT” again or use /check …',
        "nft.flow_demo_toast": "Starting example…",
        "nft.demo_intro": (
            "Try like this:\n\n"
            "Ice Cream #217467\n\n"
            "Or tap below to run the sample check."
        ),
        "watch.add_hint": (
            "➕ Add to watchlist\n\n"
            "1) Send a link to a specific NFT (or NFT address / Ice Cream #217467).\n"
            "2) Wait for the NFT card with action buttons.\n"
            "3) Tap “✅ Add to list”.\n\n"
            "Direct command also works:\n"
            "/watch Ice Cream #217467"
        ),
    }


def _strings_ru() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "onboarding.choose_language": (
            "👋 Welcome to GiftSniper\n\n"
            "I help you check NFT / Telegram Gifts using real market listings from TonAPI.\n\n"
            "Choose your language to continue:"
        ),
        "start.main": (
            "🎯 GiftSniper\n\n"
            "Я помогаю понять, за сколько можно выставить NFT / Telegram Gift по реальному рынку.\n\n"
            "✨ После проверки ты увидишь:\n"
            "🎁 превью NFT;\n"
            "🧬 трейты;\n"
            "💎 текущий листинг;\n"
            "🔎 анализ похожих NFT;\n"
            "💰 ориентир цены: быстро / нормально / дорого.\n\n"
            "📌 Как проверить:\n"
            "1️⃣ Открой NFT на Getgems / Fragment / Tonviewer.\n"
            "2️⃣ Скопируй ссылку на конкретный NFT.\n"
            "3️⃣ Пришли её сюда в чат.\n\n"
            "🔐 Безопасность:\n"
            "Я не покупаю и не продаю NFT.\n"
            "Я никогда не прошу seed-фразу, private key или доступ к кошельку.\n\n"
            "Powered by Tivonix · tivonix.tech"
        ),
        "start.hub_check_prompt": (
            "🔎 Проверка NFT\n\n"
            "Пришли ссылку на конкретный NFT с Getgems / Fragment / Tonviewer.\n\n"
            "Лучше всего — ссылка на сам NFT, не на коллекцию.\n\n"
            "После этого я покажу карточку NFT и кнопки действий."
        ),
        "start.hub_features": (
            "📊 Возможности GiftSniper\n\n"
            "• находит NFT по ссылке;\n"
            "• показывает превью, трейты и текущий листинг;\n"
            "• сканирует активные объявления коллекции;\n"
            "• сравнивает похожие NFT;\n"
            "• отсекает завышенные выбросы;\n"
            "• считает цену: быстро / нормально / дорого;\n"
            "• показывает уверенность оценки.\n\n"
            "Важно: оценка строится по активным листингам, это не гарантия сделки."
        ),
        "start.hub_help": (
            "❓ Как пользоваться\n\n"
            "1. Открой NFT на Getgems / Fragment / Tonviewer.\n"
            "2. Скопируй ссылку на конкретный NFT.\n"
            "3. Отправь ссылку в этот чат.\n"
            "4. Бот покажет карточку NFT.\n"
            "5. Нажми «🔎 Проверить рынок», чтобы получить оценку цены.\n\n"
            "🔐 Я никогда не прошу seed-фразу, private key или доступ к кошельку."
        ),
        "start.check_button": "🔎 Проверить NFT",
        "start.watchlist_button": "📋 Мой список",
        "start.settings_button": "⚙️ Настройки",
        "start.features_button": "📊 Возможности",
        "start.help_button": "❓ Помощь",
        "start.upgrade_button": "🚀 Upgrade",
        "start.back_button": "⬅️ Назад",
        "start.features_text": (
            "📊 Возможности GiftSniper\n\n"
            "• находит NFT по ссылке;\n"
            "• показывает превью, трейты и текущий листинг;\n"
            "• сканирует активные объявления коллекции;\n"
            "• сравнивает похожие NFT;\n"
            "• отсекает завышенные выбросы;\n"
            "• считает цену: быстро / нормально / дорого;\n"
            "• показывает уверенность оценки.\n\n"
            "Важно: оценка строится по активным листингам, это не гарантия сделки."
        ),
        "start.help_short_text": (
            "❓ Как пользоваться\n\n"
            "1. Открой NFT на Getgems / Fragment / Tonviewer.\n"
            "2. Скопируй ссылку на конкретный NFT.\n"
            "3. Отправь ссылку в этот чат.\n"
            "4. Бот покажет карточку NFT.\n"
            "5. Нажми «🔎 Проверить рынок», чтобы получить оценку цены.\n\n"
            "🔐 Я никогда не прошу seed-фразу, private key или доступ к кошельку."
        ),
        "help.main": (
            "❓ Как пользоваться GiftSniper\n\n"
            "Главный сценарий:\n"
            "Пришли ссылку на конкретный NFT (Getgems / Fragment / Tonviewer) или NFT address.\n\n"
            "Покажу превью NFT (анимация, видео или картинка) и рыночный ориентир через TonAPI.\n\n"
            "Формат Ice Cream #217467 может сработать, если коллекция уже есть в локальном индексе.\n\n"
            "Команды:\n"
            "/check — проверить NFT\n"
            "/watch — добавить в отслеживание\n"
            "/watchlist — мои отслеживания\n"
            "/settings — настройки\n"
            "/upgrade — тарифы и оплата TON\n"
            "/billing — подписка и лимиты\n"
            "/ref — пригласить друзей и бонусные проверки NFT\n"
            "/help — помощь\n\n"
            "Важно:\n"
            "GiftSniper показывает рыночный ориентир по активным листингам TonAPI.\n"
            "Это не гарантия продажи и не финансовый совет.\n\n"
            "Бот не покупает, не продаёт и не просит доступ к кошельку."
        ),
        "start.referral_button": "👥 Пригласить друзей",
        "referral.program_body": (
            "👥 Приглашай друзей\n\n"
            "Твоя ссылка:\n"
            "{link}\n\n"
            "Как работает:\n"
            "За каждого друга: +{per} проверки NFT.\n"
            "За каждые {every_n} друзей: ещё +{milestone} проверок.\n\n"
            "Приглашено друзей: {invited}\n"
            "Бонусные проверки: {bonus}"
        ),
        "referral.share_text": "Проверь цену своего Telegram Gift через бота",
        "referral.share_button": "📤 Поделиться ссылкой",
        "referral.refresh_button": "🔄 Обновить",
        "referral.bonus_check_used": "Использована бонусная проверка NFT. Осталось: {remaining}",
        "settings.main": (
            "⚙️ Настройки\n\n"
            "Сейчас доступны базовые проверки NFT через TonAPI.\n\n"
            "Скоро здесь появятся:\n"
            "• уведомления о дешёвых листингах;\n"
            "• настройка минимальной скидки;\n"
            "• частота проверки рынка.\n\n"
            "Пока можешь использовать:\n"
            "• /check — проверить NFT\n"
            "• /watch — добавить в отслеживание\n"
            "• /watchlist — мои отслеживания"
        ),
        "settings.language_button": "🌐 Язык",
        "settings.language_confirm": "Язык обновлён: {title}",
        "settings.open_menu": "Ок. Кнопки меню снова внизу чата.",
        "upgrade.carousel_free": (
            "🌱 Free\n\n"
            "0 TON\n"
            "{checks} проверок рынка / день\n"
            "{wl} NFT в «Мой список»\n"
            "Preview бесплатно\n\n"
            "Скан: сначала кэш, при необходимости базовый/быстрый."
        ),
        "upgrade.carousel_pro": (
            "🚀 Pro\n\n"
            "{price} TON / месяц ({days} дней)\n"
            "{checks} проверок рынка / день\n"
            "{wl} NFT в «Мой список»\n"
            "Full / auto market scan\n"
            "Basic alerts\n"
            "Выше лимиты, чем на Free"
        ),
        "upgrade.carousel_sniper": (
            "🎯 Sniper\n\n"
            "{price} TON / месяц ({days} дней)\n"
            "{checks} проверок рынка / день\n"
            "{wl} NFT в «Мой список»\n"
            "Max / full market scan\n"
            "Smart alerts\n"
            "Максимальные лимиты в MVP"
        ),
        "upgrade.nav_current_free": "Текущий тариф",
        "upgrade.nav_current_plan": "Текущий план",
        "upgrade.nav_go_pro": "Перейти на Pro →",
        "upgrade.pay_pro": "Оплатить Pro",
        "upgrade.pay_sniper": "Оплатить Sniper",
        "upgrade.pay_buy_short": "💎 Купить",
        "upgrade.pay_renew_short": "💎 Продлить",
        "upgrade.nav_sniper_right": "Sniper ➡️",
        "upgrade.nav_back_pro": "⬅️ Pro",
        "upgrade.back_button": "⬅️ Назад",
        "upgrade.billing_upgrade": "🚀 Upgrade",
        "upgrade.billing_renew": "🔄 Продлить",
        "upgrade.billing_back": "🔙 Назад",
        "billing.title": "💳 Моя подписка",
        "billing.limits_section": "Лимиты:",
        "billing.plan": "Тариф: {plan}",
        "billing.active_until": "Активен до: {date}",
        "billing.limits_checks": "• Проверки сегодня: {used} / {max}",
        "billing.limits_watchlist": "• Мой список: {used} / {max}",
        "billing.payment_note": "Оплата: TON",
        "billing.no_autorenew": "Автопродления нет.",
        "payment.instruction_title": "💎 Оплата тарифа {plan}",
        "payment.send_amount": "Отправь ровно: {amount} TON",
        "payment.to_address": "На адрес:",
        "payment.comment_line": "Комментарий к переводу:",
        "payment.notes_header": "Важно:",
        "payment.note_comment": "• комментарий обязателен;",
        "payment.note_ton_only": "• отправляй только TON;",
        "payment.note_activate": "• подписка активируется после подтверждения транзакции;",
        "payment.note_no_wallet": "• бот не просит seed, private key или доступ к кошельку.",
        "payment.after_pay_hint": "После оплаты нажми «Проверить оплату».",
        "payment.btn_check": "✅ Проверить оплату",
        "payment.btn_refresh": "🔄 Обновить счёт",
        "payment.btn_cancel": "❌ Отмена",
        "payment.not_found": (
            "⏳ Оплата пока не найдена.\n\n"
            "Проверь:\n"
            "• сумма отправлена в TON;\n"
            "• комментарий указан точно;\n"
            "• прошло 1–2 минуты после перевода.\n\n"
            "Попробуй нажать «Проверить оплату» ещё раз."
        ),
        "payment.found_header": "✅ Оплата найдена. План активирован.\n\n",
        "payment.found_until": "Тариф {plan} активен до {date}.\n\n",
        "payment.found_features": (
            "Теперь доступно:\n"
            "• до {checks} проверок NFT в день\n"
            "• до {wl} NFT в watchlist\n"
            "• уведомления о дешёвых листингах (по настройкам)\n"
        ),
        "payment.already_confirmed": "✅ Оплата уже была подтверждена ранее.\nТариф {plan} активен до {date}.",
        "payment.invoice_expired": "⏳ Счёт истёк.\nСоздай новый через 🚀 Upgrade.",
        "payment.cancelled": "Счёт отменён. При необходимости создай новый через Upgrade.",
        "payment.cannot_create": "Не удалось создать счёт. Попробуй позже.",
        "payment.payment_disabled": "Оплата TON выключена.",
        "payment.receiver_not_configured": "Адрес получателя не настроен.",
        "payment.tx_already_used": "Эта транзакция уже была учтена.",
        "payment.invoice_invalid": "Этот счёт больше не действителен. Создай новый через Upgrade.",
        "payment.user_error": "Ошибка пользователя.",
        "payment.invoice_not_found": "Счёт не найден.",
        "payment.invoice_error": "Ошибка счёта.",
        "payment.invoice_unavailable": "Счёт недоступен.",
        "payment.refresh_ok": "Обновлено",
        "payment.cancel_toast": "Отменено",
        "limit.market_checks_body": (
            "🚫 Лимит проверок на сегодня закончился\n\n"
            "На твоём плане доступно: {limit} рыночных проверок в день.\n\n"
            "Free: {free_checks} проверки / день\n"
            "Pro: {pro_checks} проверок / день\n"
            "Sniper: {sniper_checks} проверок / день\n\n"
            "Preview NFT остаётся доступным бесплатно.\n"
            "Для большего количества проверок подключи Pro или Sniper."
        ),
        "limit.watchlist_block": (
            "🚫 Лимит списка отслеживания\n\n"
            "На твоём плане доступно: {max} NFT в «Мой список».\n"
            "Чтобы добавить больше NFT, подключи Pro или Sniper.\n\n"
            "Free: {free_wl} NFT\n"
            "Pro: {pro_wl} NFT\n"
            "Sniper: {sniper_wl} NFT"
        ),
        "limit.watchlist_suffix": "\n\nСейчас в списке: {cur} / {max}.",
        "notifications.btn": "🔔 Уведомления",
        "notifications.status_on": "Уведомления: включены",
        "notifications.status_off": "Уведомления: выключены",
        "notifications.enabled_title": "🔔 Уведомления включены",
        "notifications.enabled_body": (
            "Я буду следить за рынком этого NFT и сообщу, если цена заметно изменится."
        ),
        "notifications.disabled_title": "🔕 Уведомления выключены",
        "notifications.disabled_body": "Я больше не буду присылать сигналы по этому NFT.",
        "notifications.free_gate": (
            "🔔 Уведомления доступны в Pro и Sniper\n\n"
            "Я могу следить за рынком NFT и прислать сигнал, когда цена заметно изменится.\n\n"
            "Pro: проверка каждые 6 часов\n"
            "Sniper: проверка каждый час\n"
        ),
        "notifications.push_up": (
            "🔔 Рынок вырос\n\n<b>{name}</b>\n\n"
            "Ориентир цены вырос:\n"
            "Было: ~{was} TON\n"
            "Сейчас: ~{now} TON\n"
            "Изменение: +{pct}%\n\n"
            "Это не гарантия продажи, а оценка по активным листингам."
        ),
        "notifications.push_down": (
            "⚠️ Рынок просел\n\n<b>{name}</b>\n\n"
            "Ориентир цены снизился:\n"
            "Было: ~{was} TON\n"
            "Сейчас: ~{now} TON\n"
            "Изменение: -{pct}%\n\n"
            "Возможно, сейчас лучше не выставлять слишком дорого."
        ),
        "notifications.btn_check_now": "🔎 Проверить сейчас",
        "notifications.btn_turn_off": "🔕 Выключить уведомления",
        "notifications.toast_off": "Уведомления выключены",
        "check.waiting_input": (
            "Пришли ссылку на конкретный NFT с Getgems / Fragment / Tonviewer или NFT address.\n\n"
            "Лучше всего — ссылка на сам NFT, не на коллекцию."
        ),
        "check.need_payload": "Нужен текст: ссылка, NFT address или «Коллекция #номер». Пример: /check Ice Cream #217467",
        "check.wait_market_caption": (
            "Собираю <b>цены из открытых объявлений</b> (кто и за сколько продаёт).\n"
            "Для больших коллекций это может занять 1–2 минуты — так и должно быть, без сбоев."
        ),
        "nft.btn_back": "🔙 Назад",
        "nft.btn_cancel": "❌ Отмена",
        "nft.btn_demo": "🎁 Пример",
        "watchlist.empty": (
            "📋 Мой список пока пуст\n\n"
            "Добавь NFT: пришли ссылку на NFT, затем нажми «✅ Добавить в список».\n\n"
            "Также можно: /watch или /add с адресом или ссылкой."
        ),
        "mylist.btn_open_list": "📋 Мой список",
        "mylist.btn_check_market": "🔎 Проверить рынок",
        "mylist.btn_close": "❌ Закрыть",
        "mylist.added_title": "✅ Добавлено в мой список",
        "mylist.added_hint": "Теперь ты можешь быстро открыть его из раздела «📋 Мой список».",
        "mylist.already_title": "ℹ️ Этот NFT уже есть в твоём списке.",
        "mylist.already_hint": "",
        "mylist.line_gift": "🎁 {name}",
        "mylist.line_collection": "Коллекция: {collection}",
        "mylist.session_expired": (
            "⚠️ Эта карточка устарела.\n\n"
            "Пришли ссылку на NFT ещё раз — я снова открою карточку."
        ),
        "mylist.header": "📋 Мой список\n",
        "mylist.list_hint": "В каждой строке кнопка «🔎 Проверить» — заново собрать рыночный отчёт по этому NFT.",
        "mylist.btn_row_market": "🔎 Проверить",
        "mylist.btn_add_from_check": "✅ Добавить в список",
        "progress.collection_fallback": "Коллекция",
        "progress.simple_title_named": "⏳ Анализирую рынок\n\n",
        "progress.simple_title_plain": "⏳ Анализирую рынок\n\n",
        "progress.simple_collection_named": "Коллекция: {coll}\n\n",
        "progress.simple_intro": (
            "Смотрю открытые объявления этой коллекции через TonAPI.\n\n"
        ),
        "progress.simple_checked": "Уже проверено: {loaded} NFT\n",
        "progress.simple_checked_approx": "Уже проверено: {loaded} из ~{total} NFT\n",
        "progress.simple_listings": "Найдено объявлений: {listings}\n\n",
        "progress.simple_slow": "Это может занять 1–2 минуты для больших коллекций.\n",
        "progress.simple_wallet": "Кошелёк и seed не нужны.",
        "progress.start": (
            "⏳ Анализирую рынок\n\n"
            "Я проверяю реальные объявления о продаже и ищу похожие NFT.\n\n"
            "Проверено: {loaded} NFT\n"
            "Найдено объявлений: {listings}\n\n"
            "Большие коллекции могут считаться 1–2 минуты.\n"
            "🔒 Кошелёк и seed-фраза не нужны."
        ),
        "progress.scan_head": "⏳ Считаю рынок по коллекции\n\n«{coll}»\n\n",
        "progress.scan_hint": (
            "\nКошелёк и seed не нужны.\n"
            "Сообщение будет обновляться по мере загрузки."
        ),
        "progress.ratelimit_user": (
            "⏳ Нужна короткая пауза\n\n"
            "<b>«{coll}»</b>\n"
            "• Уже в выборке: <b>{loaded}</b> NFT\n"
            "• С ценой в продаже: <b>{listings}</b>\n\n"
            "Продолжаю — от вас ничего не требуется."
        ),
        "progress.ratelimit_user_plain": (
            "⏳ Нужна короткая пауза\n\n"
            "• Уже в выборке: <b>{loaded}</b> NFT\n"
            "• С ценой в продаже: <b>{listings}</b>\n\n"
            "Продолжаю — от вас ничего не требуется."
        ),
        "progress.ratelimit_title": "⏳ Короткая пауза\n\n",
        "progress.ratelimit_body": "Сервис на секунду ограничил скорость — продолжаю.\n\n",
        "progress.ratelimit_stats": "«{coll}»\n• Уже в выборке: {loaded} NFT\n• С ценой в продаже: {listings}\n",
        "progress.page_limit": "• Лимит страницы: {limit}\n",
        "progress.page_note": "\n{note}\n",
        "progress.ratelimit_footer": "\nПолный скан коллекции",
        "progress.scan_title": "⏳ Сканирую коллекцию (подробный режим)\n\n",
        "progress.scan_loaded_approx": "Загружено: {loaded} из ~{total} NFT\n",
        "progress.scan_loaded": "Загружено: {loaded} NFT\n",
        "progress.scan_listings": "Активных листингов: {listings}\n",
        "progress.scan_mode": "Режим: полный скан\n",
        "progress.scan_page_limit": "Лимит страницы: {limit}\n",
        "progress.scan_note": "{note}\n",
        "progress.scan_source": "Источник: открытые объявления",
        "progress.default": (
            "⏳ «{coll}»\n\n"
            "• Всего NFT в выборке: {loaded}\n"
            "• Выставлено с ценой: {listings}\n\n"
            "Дальше — ищу похожие по модели, фону и символу…"
        ),
        "upgrade.ok_menu": "Ок. Кнопки меню снова внизу чата.",
        "upgrade.unavailable": "Недоступно",
        "nft.flow_cancelled": "Отменено",
        "nft.flow_back_ok": "Ок. Выбери действие кнопками внизу чата.",
        "nft.flow_check_closed": "Готово.",
        "nft.flow_cancel_hint": "Ок, отменил. Снова: кнопка «🔎 Проверить NFT» или /check …",
        "nft.flow_demo_toast": "Запускаю пример…",
        "nft.demo_intro": (
            "Попробуй так:\n\n"
            "Ice Cream #217467\n\n"
            "Или просто нажми, чтобы я запустил пример проверки."
        ),
        "watch.add_hint": (
            "➕ Добавить в отслеживание\n\n"
            "1) Сначала пришли ссылку на конкретный NFT (или NFT address / Ice Cream #217467).\n"
            "2) Дождись карточки NFT с кнопками действий.\n"
            "3) Нажми кнопку «✅ Добавить в список».\n\n"
            "Можно и командой напрямую:\n"
            "/watch Ice Cream #217467"
        ),
    }


def _strings_es() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "Te ayudo a entender por cuánto puedes listar tu NFT / Telegram Gift según listados reales.\n\n"
            "Qué hago:\n"
            "• encuentro NFT por dirección, enlace o nombre;\n"
            "• reviso listados activos vía TonAPI;\n"
            "• comparo con NFT similares en la misma colección;\n"
            "• muestro guía de precio: rápido / normal / alto;\n"
            "• explico la confianza.\n\n"
            "Envía un NFT o elige una acción abajo 👇\n\n"
            "Seguridad:\n"
            "No compro ni vendo NFT.\n"
            "Nunca pido frase semilla, clave privada ni acceso a la billetera."
        ),
        "help.main": (
            "❓ Cómo usar GiftSniper\n\n"
            "1️⃣ Nombre: Ice Cream #217467\n"
            "2️⃣ Enlace: https://...\n"
            "3️⃣ Dirección NFT: EQ...\n\n"
            "Comandos: /check /watch /watchlist /settings /upgrade /billing /help\n\n"
            "El bot no compra ni vende NFT ni pide acceso a tu billetera."
        ),
        "settings.main": (
            "⚙️ Ajustes\n\n"
            "Comprobaciones NFT con TonAPI (solo lectura).\n"
            "• /check • /watch • /watchlist\n\n"
            "Usa el botón de idioma para cambiar el idioma."
        ),
        "settings.language_button": "🌐 Idioma",
        "settings.language_confirm": "Idioma actualizado: {title}",
    }


def _strings_tr() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "NFT / Telegram Gift için gerçek piyasa listelerine göre fiyat rehberi sunarım.\n\n"
            "Güvenlik: NFT alım-satımı yapmam; seed, private key veya cüzdan erişimi istemem."
        ),
        "help.main": (
            "❓ GiftSniper kullanımı\n\n"
            "1️⃣ İsim  2️⃣ Link  3️⃣ NFT adresi\n\n"
            "/check /watch /watchlist /settings /upgrade /billing /help\n\n"
            "Bot NFT alıp satmaz ve cüzdan erişimi istemez."
        ),
        "settings.language_button": "🌐 Dil",
        "settings.language_confirm": "Dil güncellendi: {title}",
    }


def _strings_pt() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "Ajudo a estimar o preço do seu NFT / Telegram Gift com listagens reais (TonAPI).\n\n"
            "Segurança: não compro/vendo NFT; nunca peço seed, chave privada ou acesso à carteira."
        ),
        "help.main": (
            "❓ Como usar\n\n"
            "1️⃣ Nome  2️⃣ Link  3️⃣ Endereço NFT\n\n"
            "/check /watch /watchlist /settings /upgrade /billing /help\n\n"
            "O bot não negocia NFTs nem pede acesso à carteira."
        ),
        "settings.language_button": "🌐 Idioma",
        "settings.language_confirm": "Idioma atualizado: {title}",
    }


def _strings_fr() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "J’estime le prix de votre NFT / Telegram Gift à partir des annonces TonAPI.\n\n"
            "Sécurité : pas d’achat/vente ; jamais de seed, clé privée ou accès au portefeuille."
        ),
        "settings.language_button": "🌐 Langue",
        "settings.language_confirm": "Langue mise à jour : {title}",
    }


def _strings_de() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "Ich helfe dir, einen Marktpreis für dein NFT / Telegram Gift anhand echter TonAPI-Inserate einzuschätzen.\n\n"
            "Sicherheit: kein Kauf/Verkauf; nie Seed, Private Key oder Wallet-Zugriff."
        ),
        "settings.language_button": "🌐 Sprache",
        "settings.language_confirm": "Sprache aktualisiert: {title}",
    }


def _strings_ar() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "أساعدك بتقدير سعر NFT / هدية تيليجرام بناءً على قوائم TonAPI.\n\n"
            "الأمان: لا أشتري أو أبيع NFT؛ لا أطلب عبارة استرداد أو مفتاح خاص أو وصول للمحفظة."
        ),
        "settings.language_button": "🌐 اللغة",
        "settings.language_confirm": "تم تحديث اللغة: {title}",
    }


def _strings_hi() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "TonAPI लिस्टिंग के आधार पर NFT / Telegram Gift का मूल्य अनुमान।\n\n"
            "सुरक्षा: खरीद/बिक्री नहीं; seed, private key या wallet access नहीं मांगता।"
        ),
        "settings.language_button": "🌐 भाषा",
        "settings.language_confirm": "भाषा अपडेट: {title}",
    }


def _strings_id() -> dict[str, str]:
    e = _strings_en()
    return {
        **e,
        "start.main": (
            "🎯 GiftSniper\n\n"
            "Membantu perkiraan harga NFT / Telegram Gift dari listing TonAPI.\n\n"
            "Keamanan: tidak jual/beli NFT; tidak minta seed, private key, atau akses dompet."
        ),
        "settings.language_button": "🌐 Bahasa",
        "settings.language_confirm": "Bahasa diperbarui: {title}",
    }


@lru_cache(maxsize=1)
def _all_bundles() -> dict[str, dict[str, str]]:
    return {
        "en": _strings_en(),
        "ru": _strings_ru(),
        "es": _strings_es(),
        "tr": _strings_tr(),
        "pt": _strings_pt(),
        "fr": _strings_fr(),
        "de": _strings_de(),
        "ar": _strings_ar(),
        "hi": _strings_hi(),
        "id": _strings_id(),
    }


def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    lg = normalize_lang(lang)
    bundles = _all_bundles()
    raw = bundles.get(lg, {}).get(key) or bundles["en"].get(key) or key
    if kwargs:
        return _fmt(raw, kwargs)
    return raw


def main_menu_labels_union() -> frozenset[str]:
    """Все варианты подписей главного меню (любой поддерживаемый язык) — для фильтров aiogram."""
    bundles = _all_bundles()
    keys = (
        "start.check_button",
        "start.watchlist_button",
        "start.help_button",
        "start.upgrade_button",
    )
    out: set[str] = set()
    for b in bundles.values():
        for k in keys:
            if k in b:
                out.add(b[k])
    return frozenset(out)


def nft_check_prompt_button_labels() -> frozenset[str]:
    """Тексты кнопки «Проверить NFT» на всех языках (reply + inline)."""
    return frozenset(t("start.check_button", lg) for lg in SUPPORTED_LANGUAGE_CODES)


def language_selector_keyboard() -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, code in enumerate(SUPPORTED_LANGUAGE_CODES):
        meta = LANGUAGES[code]
        row.append(
            InlineKeyboardButton(
                text=f"{meta['flag']} {meta['title']}",
                callback_data=f"lang:set:{code}",
            )
        )
        if len(row) == 2 or i == len(SUPPORTED_LANGUAGE_CODES) - 1:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def localized_carousel_body(plan_key: str, settings: Any, lang: str) -> str:
    """Текст карусели тарифов (цены и лимиты из settings)."""
    from app.services.plan_catalog import plan_duration_days, plan_price_ton

    lg = normalize_lang(lang)
    if plan_key == "free":
        return t(
            "upgrade.carousel_free",
            lg,
            checks=int(settings.plan_free_daily_nft_checks),
            wl=int(settings.plan_free_watchlist_limit),
        )
    if plan_key == "pro":
        return t(
            "upgrade.carousel_pro",
            lg,
            checks=int(settings.plan_pro_daily_nft_checks),
            wl=int(settings.plan_pro_watchlist_limit),
            price=plan_price_ton("pro", settings),
            days=plan_duration_days("pro", settings),
        )
    return t(
        "upgrade.carousel_sniper",
        lg,
        checks=int(settings.plan_sniper_daily_nft_checks),
        wl=int(settings.plan_sniper_watchlist_limit),
        price=plan_price_ton("sniper", settings),
        days=plan_duration_days("sniper", settings),
    )


_SAFETY_PAT_EN = re.compile(
    r"do not buy|never ask|seed|private key|wallet access|не покупаю|не продаю|не прошу|seed|private key|кошельк",
    re.IGNORECASE,
)


def safety_text_present(text: str) -> bool:
    """Проверка тестов: в тексте есть смысл read-only / без seed."""
    return bool(_SAFETY_PAT_EN.search(text or ""))

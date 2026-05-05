from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

# Статические флаги по плану (лимиты checks / watchlist — из Settings, см. get_plan_limits).
PLAN_LIMITS = {
    "free": {
        "max_universe_collections": 2,
        "manual_market_data": True,
        "alerts": False,
        "smart_alerts": False,
        "scan_universe": False,
        "capital_plan": False,
        "incidents": False,
    },
    "pro": {
        "max_universe_collections": 20,
        "manual_market_data": True,
        "alerts": True,
        "smart_alerts": False,
        "scan_universe": True,
        "capital_plan": True,
        "incidents": True,
    },
    "sniper": {
        "max_universe_collections": 100,
        "manual_market_data": True,
        "alerts": True,
        "smart_alerts": True,
        "scan_universe": True,
        "capital_plan": True,
        "incidents": True,
        "high_scheduler_frequency": True,
    },
}

# Совместимость: старые имена планов маппятся на MVP-тарифы.
_PLAN_ALIASES = {"starter": "pro", "trader": "sniper"}


def normalize_plan_for_limits(plan: str | None) -> str:
    p = (plan or "free").strip().lower()
    p = _PLAN_ALIASES.get(p, p)
    if p not in PLAN_LIMITS:
        return "free"
    return p


def get_plan_limits(plan: str | None, *, settings: "Settings | None" = None) -> dict:
    from app.config import get_settings

    settings = settings or get_settings()
    key = normalize_plan_for_limits(plan)
    base = dict(PLAN_LIMITS[key])
    if key == "free":
        base["checks_per_day"] = int(settings.plan_free_daily_nft_checks)
        base["max_gifts"] = int(settings.plan_free_watchlist_limit)
    elif key == "pro":
        base["checks_per_day"] = int(settings.plan_pro_daily_nft_checks)
        base["max_gifts"] = int(settings.plan_pro_watchlist_limit)
    elif key == "sniper":
        base["checks_per_day"] = int(settings.plan_sniper_daily_nft_checks)
        base["max_gifts"] = int(settings.plan_sniper_watchlist_limit)
    else:
        base["checks_per_day"] = int(settings.plan_free_daily_nft_checks)
        base["max_gifts"] = int(settings.plan_free_watchlist_limit)
    return base


def _effective_plan_for_user(user) -> str:
    return (getattr(user, "effective_plan", None) or getattr(user, "plan", "free") or "free").lower()


def can_use_feature(user, feature_name: str) -> bool:
    role = (getattr(user, "role", "") or "").lower()
    if getattr(user, "is_blocked", False):
        return False
    if role in {"admin", "owner"}:
        return True
    limits = get_plan_limits(_effective_plan_for_user(user))
    value = limits.get(feature_name, False)
    return bool(value)


DEFAULT_PAYWALL_FOOTER = (
    "\n\nНа Free доступны: /check, /deal, /add, /lite_plan <бюджет>, ручные market-данные.\n"
    "Апгрейд без давления: /upgrade"
)

PAYWALL_MESSAGES: dict[str, str] = {
    "capital_plan": (
        "🔒 Полный план капитала сканирует universe и несколько коллекций — это в Pro/Starter+.\n\n"
        "На Free можно собрать облегчённый план только по watchlist:\n"
        "→ /lite_plan <budget_ton>\n\n"
        "Пример: /lite_plan 300"
    ),
    "scan_universe": (
        "🔒 Скан universe (несколько коллекций, сравнение режимов) — в Pro/Sniper.\n\n"
        "На Free: добавь подарки в watchlist и используй /deals или /lite_plan.\n"
        "Ручные цены: /market_data, /market_set_sale"
    ),
    "smart_alerts": (
        "🔒 Smart alerts с привязкой к universe — в Sniper.\n\n"
        "На Free базовые уведомления недоступны; смотри /home и /deals."
    ),
    "alerts": (
        "🔒 Alerts на этом плане выключены.\n\n"
        "Апгрейд откроет правила цен: /upgrade"
    ),
    "incidents": (
        "🔒 Инциденты и расширенная аналитика алертов — в Pro/Sniper.\n\n"
        "На Free следи за сделками через /portfolio и журнал: /trades"
    ),
}


def paywall_message_for(feature_name: str, user) -> str:
    plan = normalize_plan_for_limits(_effective_plan_for_user(user)).capitalize()
    core = PAYWALL_MESSAGES.get(
        feature_name,
        "🔒 Эта функция недоступна на текущем плане.\n\n"
        f"Твой план: {plan}.\n"
        "Разбор одной сделки и watchlist на Free всё ещё доступны.",
    )
    return core + DEFAULT_PAYWALL_FOOTER


def assert_feature_allowed(user, feature_name: str) -> None:
    if can_use_feature(user, feature_name):
        return
    raise PermissionError(paywall_message_for(feature_name, user))


def check_usage_limit(user, usage_type: str, current_count: int, *, settings: "Settings | None" = None) -> tuple[bool, int]:
    role = (getattr(user, "role", "") or "").lower()
    if getattr(user, "is_blocked", False):
        return False, 0
    if role in {"admin", "owner"}:
        return True, 10**9
    limits = get_plan_limits(_effective_plan_for_user(user), settings=settings)
    max_allowed = int(limits.get(usage_type, 0))
    return current_count < max_allowed, max_allowed


def checks_per_day_limit(user, *, settings: "Settings | None" = None) -> int:
    limits = get_plan_limits(_effective_plan_for_user(user), settings=settings)
    return int(limits.get("checks_per_day", 999999))

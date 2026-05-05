"""Каталог тарифов Free / Pro / Sniper — тексты для карусели (цены из Settings)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

PLAN_ORDER = ("free", "pro", "sniper")


@dataclass(frozen=True)
class SellablePlan:
    plan_id: str
    title: str
    description: str
    price_ton: Decimal
    duration_days: int
    checks_per_day: int
    watchlist_limit: int
    features: tuple[str, ...]


def plan_title(key: str) -> str:
    return {"free": "Free", "pro": "🚀 Pro", "sniper": "🎯 Sniper"}.get(key, key)


def carousel_body(key: str, settings: "Settings") -> str:
    fc = int(settings.plan_free_daily_nft_checks)
    fw = int(settings.plan_free_watchlist_limit)
    pc = int(settings.plan_pro_daily_nft_checks)
    pw = int(settings.plan_pro_watchlist_limit)
    sc = int(settings.plan_sniper_daily_nft_checks)
    sw = int(settings.plan_sniper_watchlist_limit)
    if key == "free":
        return (
            "🌱 Free\n\n"
            "Старт без оплаты: рыночные проверки NFT и небольшой watchlist.\n\n"
            "Что входит:\n"
            f"• {fc} рыночных проверок в день\n"
            f"• до {fw} NFT в «Мой список»\n"
            "• preview по ссылке бесплатно; кэш / базовый скан рынка\n\n"
            "Цена: бесплатно"
        )
    if key == "pro":
        return (
            "🚀 Pro\n\n"
            "Для активных пользователей, которые регулярно проверяют NFT.\n\n"
            "Что входит:\n"
            f"• {pc} рыночных проверок в день\n"
            f"• {pw} NFT в «Мой список»\n"
            "• full / auto market scan (в рамках TonAPI)\n"
            "• базовые alerts\n"
            "• confidence и похожие листинги\n\n"
            f"Цена: {settings.plan_pro_price_ton:g} TON / {settings.plan_pro_duration_days} дней"
        )
    return (
        "🎯 Sniper\n\n"
        "Для активного мониторинга рынка.\n\n"
        "Что входит:\n"
        f"• {sc} рыночных проверок в день\n"
        f"• {sw} NFT в «Мой список»\n"
        "• max / full market scan (в рамках TonAPI)\n"
        "• smart alerts\n"
        "• расширенные лимиты и частота мониторинга\n\n"
        f"Цена: {settings.plan_sniper_price_ton:g} TON / {settings.plan_sniper_duration_days} дней"
    )


def plan_price_ton(key: str, settings: "Settings") -> float:
    if key == "pro":
        return float(settings.plan_pro_price_ton)
    if key == "sniper":
        return float(settings.plan_sniper_price_ton)
    return 0.0


def plan_duration_days(key: str, settings: "Settings") -> int:
    if key == "pro":
        return int(settings.plan_pro_duration_days)
    if key == "sniper":
        return int(settings.plan_sniper_duration_days)
    return 0


def ton_to_nano(ton: float) -> int:
    return int(round(float(ton) * 1_000_000_000))


def ton_decimal_to_nano(ton: Decimal) -> int:
    return int((ton * Decimal("1000000000")).to_integral_value())


def generate_invoice_comment(plan_key: str, short_id: str) -> str:
    p = plan_key.upper()
    if p == "SNIPER":
        p = "SNIPER"
    elif p == "PRO":
        p = "PRO"
    else:
        p = "FREE"
    return f"GS-{p}-{short_id}"


def get_sellable_plan(plan_key: str, settings: "Settings") -> SellablePlan | None:
    key = (plan_key or "").strip().lower()
    if key == "pro":
        price = Decimal(str(settings.plan_pro_price_ton or 0))
        days = int(settings.plan_pro_duration_days or 0)
        if price <= 0 or days <= 0:
            return None
        return SellablePlan(
            plan_id="pro",
            title="Pro",
            description="Больше проверок и расширенный анализ рынка",
            price_ton=price,
            duration_days=days,
            checks_per_day=int(settings.plan_pro_daily_nft_checks),
            watchlist_limit=int(settings.plan_pro_watchlist_limit),
            features=("more_analysis", "alerts", "smart_alerts"),
        )
    if key == "sniper":
        price = Decimal(str(settings.plan_sniper_price_ton or 0))
        days = int(settings.plan_sniper_duration_days or 0)
        if price <= 0 or days <= 0:
            return None
        return SellablePlan(
            plan_id="sniper",
            title="Sniper",
            description="Максимальные лимиты и расширенные сигналы",
            price_ton=price,
            duration_days=days,
            checks_per_day=int(settings.plan_sniper_daily_nft_checks),
            watchlist_limit=int(settings.plan_sniper_watchlist_limit),
            features=("more_analysis", "alerts", "smart_alerts", "high_scheduler_frequency"),
        )
    return None

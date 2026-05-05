"""Stage 37 — decide whether trading prices / verdicts may be shown."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.schemas.market import MarketDataQuality


@dataclass(frozen=True)
class MarketDataValidity:
    pricing_allowed: bool
    trading_verdict_allowed: bool
    source_type: str  # real | manual | mock | unavailable | mixed
    has_floor: bool
    has_listings: bool
    has_recent_sales: bool
    has_trait_sales: bool
    has_real_market_data: bool
    has_manual_market_data: bool
    has_only_mock_data: bool
    reason_code: str
    user_message_ru: str
    confidence_cap: int | None


def _only_mock_sources(quality: MarketDataQuality) -> bool:
    used = [s.lower() for s in (quality.sources_used or [])]
    return bool(used) and all(s == "mock" for s in used)


def _has_real_adapter(quality: MarketDataQuality) -> bool:
    real = {"getgems", "tonnel", "fragment"}
    return bool(real.intersection({s.lower() for s in quality.sources_used or []}))


def _has_manual(quality: MarketDataQuality) -> bool:
    return "manual" in {s.lower() for s in quality.sources_used or []}


def evaluate_market_data_validity(
    *,
    settings: Settings,
    quality: MarketDataQuality,
    stats: dict[str, Any],
    has_floor: bool,
    listings_count: int,
    sales_count: int,
    max_trait_sales: int,
) -> MarketDataValidity:
    has_manual = _has_manual(quality) or bool(stats.get("manual_floor"))
    has_real = _has_real_adapter(quality) or bool(stats.get("real_floor"))
    has_listings = listings_count > 0
    has_recent_sales = sales_count > 0 or int(stats.get("real_sales_count") or 0) > 0
    has_trait_sales = max_trait_sales > 0
    only_mock = quality.is_mock_data and _only_mock_sources(quality)
    has_only_mock = only_mock and not has_manual

    production = bool(settings.production_mode)
    block_mock = bool(settings.block_trading_verdict_on_mock) and not bool(settings.allow_mock_in_production)

    if has_real and has_manual:
        src_type = "mixed"
    elif has_real:
        src_type = "real"
    elif has_manual:
        src_type = "manual"
    elif has_only_mock or (quality.is_mock_data and not has_real and not has_manual):
        src_type = "mock"
    else:
        src_type = "unavailable"

    pricing_allowed = True
    reason = "ok"
    msg = ""
    cap: int | None = None

    if production and block_mock and has_only_mock:
        pricing_allowed = False
        reason = "mock_blocked_production"
        msg = (
            "Недостаточно реальных рыночных данных. Я не называю цену покупки/продажи, чтобы не ввести в заблуждение.\n"
            "Добавьте ручные данные (/market_quick или /market_set_*) или подключите реальный источник (Getgems/Tonnel/Fragment).\n"
            "Проверка: /sources"
        )
    elif bool(settings.require_real_or_manual_for_trading) and not has_real and not has_manual:
        if not has_floor and not has_listings and not has_recent_sales:
            pricing_allowed = False
            reason = "no_market_signals"
            msg = (
                "Рыночные цены недоступны: нет floor, листингов и недавних продаж из реальных или ручных источников.\n"
                "TonAPI даёт метаданные, но не заменяет рынок.\n"
                "Быстрый ввод: /market_quick <коллекция> | floor=… | sale=… | listing=…"
            )

    trading_verdict_allowed = pricing_allowed
    if pricing_allowed and sales_count < int(settings.min_real_sales_for_strong_buy):
        cap = int(settings.min_real_market_confidence_for_buy)

    if pricing_allowed and not msg:
        if src_type == "mock" and not production:
            msg = "Тестовый mock-расчёт: не использовать для реальной покупки."
        elif src_type == "manual":
            msg = "Цены основаны на ручных рыночных данных — перепроверьте перед сделкой."
        elif src_type == "real":
            msg = "Цены основаны на данных маркетплейсов (real)."

    return MarketDataValidity(
        pricing_allowed=pricing_allowed,
        trading_verdict_allowed=trading_verdict_allowed,
        source_type=src_type,
        has_floor=has_floor,
        has_listings=has_listings,
        has_recent_sales=has_recent_sales,
        has_trait_sales=has_trait_sales,
        has_real_market_data=has_real,
        has_manual_market_data=has_manual,
        has_only_mock_data=has_only_mock,
        reason_code=reason,
        user_message_ru=msg or "Данные достаточны для оценки модели.",
        confidence_cap=cap,
    )


def filter_mock_listings_for_production(settings: Settings, listings: list[Any]) -> list[Any]:
    """Strip mock-sourced candidates when production blocks mock trading."""
    if not settings.production_mode or settings.allow_mock_in_production or not settings.block_trading_verdict_on_mock:
        return listings
    out = []
    for item in listings:
        src = (getattr(item, "source", None) or "").lower()
        if src != "mock":
            out.append(item)
    return out

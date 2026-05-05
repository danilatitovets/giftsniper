from __future__ import annotations

from typing import Any

from app.schemas.gift import GiftCard
from app.schemas.market import MarketDataQuality
from app.utils.text import clamp_reason_lines

_DECISION_TYPE_RU: dict[str, str] = {
    "STRONG_BUY": "Сильная покупка",
    "BUY_IF_UNDER": "Покупка ниже лимита",
    "SPECULATIVE_BUY": "Спекулятивная покупка",
    "HOLD": "Удержание",
    "LIST_NOW": "Листинг сейчас",
    "LIST_HIGH": "Листинг выше рынка",
    "QUICK_SELL": "Быстрая продажа",
    "AVOID": "Не входить",
    "NEED_MORE_DATA": "Мало данных",
}

_CAP_REASON_RU: dict[str, str] = {
    "confidence capped: mock data": "уверенность ограничена — тестовые (mock) данные",
    "confidence capped: manual floor only": "уверенность ограничена — только ручной floor",
    "confidence capped: manual floor + trait floors": "уверенность ограничена — ручные floor и по атрибутам",
    "confidence capped: manual floor + trait floors + sales": "уверенность ограничена — ручные данные и продажи",
    "confidence capped: no real sales": "уверенность ограничена — нет реальных продаж",
    "confidence capped: real floor only": "уверенность ограничена — только реальный floor",
    "confidence capped: old floor data": "уверенность ограничена — устаревший floor",
}


def _ru_cap_reason(cap: str) -> str:
    return _CAP_REASON_RU.get(cap, cap)


def _fmt_ton(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}"


def _verdict_label(recommendation: str, confidence: int) -> str:
    if confidence < 50 and recommendation in {"BUY_FOR_FLIP", "LIST_HIGHER"}:
        return "🟡 Данных мало — осторожно, без жёсткого «покупать»"
    if recommendation in {"BUY_FOR_FLIP", "LIST_HIGHER"}:
        return "🟢 Можно смотреть к покупке"
    if recommendation in {"BUY_ONLY_CHEAP", "HOLD"}:
        return "🟡 Только если дешевле"
    return "🔴 Не покупать сейчас"


def _brain_verdict_line(estimate: Any, confidence: int) -> str:
    dt = getattr(estimate, "decision_type", None)
    summary = (getattr(estimate, "decision_summary", None) or "").strip()
    mb = getattr(estimate, "buy_zone_max_ton", None)
    name = _DECISION_TYPE_RU.get(dt or "", "")
    if confidence < 50 and dt in {"STRONG_BUY", "BUY_IF_UNDER"}:
        return f"Вердикт: 🟡 Мало данных для агрессивного входа — {summary}".strip()
    emoji = "🟡"
    if dt in {"STRONG_BUY", "BUY_IF_UNDER", "LIST_NOW", "LIST_HIGH"}:
        emoji = "🟢" if confidence >= 50 else "🟡"
    if dt in {"AVOID", "QUICK_SELL"}:
        emoji = "🔴"
    if dt in {"SPECULATIVE_BUY", "NEED_MORE_DATA", "HOLD"}:
        emoji = "🟡"
    tail = f" (ориентир макс. ~{mb:.0f} TON)" if mb is not None and dt == "BUY_IF_UNDER" else ""
    if summary:
        label = name or "оценка"
        return f"Вердикт: {emoji} {label}{tail} — {summary}"
    vl = _verdict_label(getattr(estimate, "recommendation", ""), confidence)
    if name:
        return f"Вердикт: {emoji} {name}"
    return f"Вердикт: {vl}"


def _risk_band_ru(risk_score: int | None) -> str:
    if risk_score is None:
        return "неизвестно"
    if risk_score <= 40:
        return "низкий"
    if risk_score <= 70:
        return "средний"
    return "высокий"


def _market_mode_label(quality: MarketDataQuality | None, stats: dict | None) -> str:
    if quality and quality.is_mock_data:
        return "mock"
    if stats and (stats.get("manual_floor") or stats.get("manual_sales_count")):
        parts = []
        if stats.get("real_listings_count") or stats.get("real_sales_count"):
            parts.append("real")
        parts.append("manual")
        return "+".join(parts) if parts else "manual"
    if stats and (stats.get("real_sales_count") or stats.get("real_floor")):
        return "real"
    return "manual" if quality and quality.is_partial_data else "mixed"


def _sales_hint(stats: dict | None) -> str:
    if not stats:
        return "no recent"
    n = int(stats.get("real_sales_count") or 0)
    if n <= 0:
        return "no recent"
    return f"{n} recent"


def _sales_hint_ru(stats: dict | None) -> str:
    if not stats:
        return "нет данных"
    n = int(stats.get("real_sales_count") or 0)
    if n <= 0:
        return "нет недавних продаж"
    return f"{n} недавних продаж"


def _freshness_hint(stats: dict | None) -> str:
    if not stats:
        return "unknown"
    labels = [stats.get("floor_freshness"), stats.get("sales_freshness"), stats.get("listings_freshness")]
    if "old" in labels:
        return "old"
    if "stale" in labels:
        return "stale"
    if "fresh" in labels:
        return "fresh"
    return "unknown"


def _freshness_hint_ru(stats: dict | None) -> str:
    h = _freshness_hint(stats)
    return {"old": "устарели", "stale": "не самые свежие", "fresh": "свежие", "unknown": "неизвестно"}.get(
        h, h
    )


def _market_mode_label_ru(quality: MarketDataQuality | None, stats: dict | None) -> str:
    raw = _market_mode_label(quality, stats)
    part_map = {"mock": "тест (mock)", "real": "живые котировки", "manual": "ручной ввод", "mixed": "смешанно"}
    return " · ".join(part_map.get(p.strip(), p.strip()) for p in raw.split("+"))


def format_source_quality_compact(quality: MarketDataQuality | None, stats: dict | None, estimate: Any = None) -> str:
    label = (getattr(estimate, "price_source_label", None) if estimate else None) or (stats or {}).get("price_source_label")
    if label:
        part_map = {
            "real": "real (маркетплейсы)",
            "manual": "manual (ручной ввод)",
            "mock": "тест (mock)",
            "unavailable": "недоступно",
            "mixed": "mixed (real+manual)",
        }
        mode = part_map.get(str(label), str(label))
    else:
        mode = _market_mode_label_ru(quality, stats)
    sales = _sales_hint_ru(stats)
    fresh = _freshness_hint_ru(stats)
    cap = (stats or {}).get("confidence_cap_reason") or ""
    cap_line = f"\n⚙️ {_ru_cap_reason(cap)}" if cap else ""
    return f"📡 Источник цены: {mode}\n📊 Продажи: {sales}\n🕐 Свежесть данных: {fresh}{cap_line}"


def format_gift_identity_card(gift: GiftCard, identity_hint: str | None = None) -> str:
    title = f"🎁 {gift.collection} #{gift.number}"
    lines = [title]
    if identity_hint:
        lines.append(identity_hint)
    return "\n".join(lines)


def format_gift_analysis_card(
    gift: GiftCard,
    estimate: Any,
    quality: MarketDataQuality | None,
    stats: dict | None,
    *,
    compact: bool,
    purchase_price: float | None = None,
) -> str:
    if getattr(estimate, "pricing_suppressed", False):
        msg = (getattr(estimate, "market_validity_message_ru", None) or "").strip()
        pq = format_source_quality_compact(quality, stats, estimate=estimate)
        hints = (
            "\n\nЧтобы получить расчёт сейчас, добавьте рынок вручную:\n"
            " /market_quick <коллекция> | floor=7.5 | sale=8 | listing=7.77 | num=57234\n"
            "Проверка источников: /sources"
        )
        return (
            f"🎁 {gift.collection} #{gift.number}\n"
            f"Рыночные цены недоступны.\n"
            f"Я не называю buy/list/sell, потому что нет real/manual market data.\n\n"
            f"{msg}\n{pq}{hints}\n"
        )
    conf = int(getattr(estimate, "confidence_score", 0) or 0)
    mock_banner = ""
    if stats and stats.get("dev_mock_labeled"):
        mock_banner = "⚠️ Тестовый mock расчёт — не использовать для реальной покупки.\nВ production такого быть не должно.\n\n"
    verdict_line = _brain_verdict_line(estimate, conf)
    risk = _risk_band_ru(getattr(estimate, "risk_score", None))
    liq = int(getattr(estimate, "liquidity_score", 0) or 0)
    header = f"🎁 {gift.collection} #{gift.number}\n"
    bmin = getattr(estimate, "buy_zone_min_ton", None)
    bmax = getattr(estimate, "buy_zone_max_ton", None)
    safe_b = getattr(estimate, "safe_buy_price_ton", None)
    agg_b = getattr(estimate, "aggressive_buy_price_ton", None)
    fair = float(getattr(estimate, "fair_price_ton", 0) or 0)
    nl = getattr(estimate, "normal_list_price_ton", None) or getattr(estimate, "list_price_ton", None)
    hl = getattr(estimate, "high_list_price_ton", None)
    qf = getattr(estimate, "quick_flip_list_price_ton", None)
    qs = getattr(estimate, "quick_sell_price_ton", None)
    st = getattr(estimate, "stop_price_ton", None)
    roi = float(getattr(estimate, "expected_roi_percent", 0) or 0)
    exp_p = float(getattr(estimate, "expected_profit_ton", 0) or 0)
    buy_zone_s = (
        f"{bmin:.0f}–{bmax:.0f} TON"
        if bmin is not None and bmax is not None
        else "—"
    )
    rarity_line = ""
    adj = getattr(estimate, "liquidity_adjusted_rarity_score", None)
    if adj is not None:
        rarity_line = f"\n· Редкость (с учётом ликвидности): {adj:.0f}/100"
    sales_n = int((stats or {}).get("real_sales_count") or 0)
    high_list = f" · верх диапазона ~{hl:.0f} TON" if hl else ""
    block = (
        f"{verdict_line}\n"
        f"────────────\n"
        f"💵 Цены (TON)\n"
        f"· Безопасная покупка: {_fmt_ton(safe_b)}\n"
        f"· Максимум для покупки: {_fmt_ton(bmax)}\n"
        f"· Агрессивная покупка: {_fmt_ton(agg_b)}\n"
        f"· Зона входа (классика): {buy_zone_s}\n"
        f"· Листинг: {_fmt_ton(qf)} – {_fmt_ton(nl)}{high_list}\n"
        f"· Быстрая продажа: {_fmt_ton(qs)} · Стоп: {_fmt_ton(st)}\n"
        f"────────────\n"
        f"📈 Сценарий (после комиссии в модели)\n"
        f"· Ожидаемо: {exp_p:+.1f} TON ({roi:+.0f}%)\n"
        f"· Справедливая цена: ~{fair:.0f} TON\n"
        f"────────────\n"
        f"🎯 Оценка модели\n"
        f"· Уверенность: {conf}/100\n"
        f"· Риск: {risk}\n"
        f"· Ликвидность: {liq}/100"
        f"{rarity_line}\n"
        f"· Продаж в выборке: {sales_n}\n"
    )
    buy_ref = purchase_price if purchase_price is not None else (bmax or fair or None)
    if buy_ref is None:
        buy_ref = 0.0
    why_lines = clamp_reason_lines(getattr(estimate, "reasons", []) or [])[:4]
    pq = format_source_quality_compact(quality, stats, estimate=estimate)
    max_ref = bmax if bmax is not None else buy_ref
    actions = (
        f"💡 Что делать дальше\n"
        f"· Покупать только ниже ~{max_ref:.0f} TON (макс. из модели), лучше ближе к «безопасной» цене.\n"
        f"· Если уже купил дороже — не усредняй без свежих продаж и данных.\n"
        f"· Листинг — ближе к нормальному; быстрая продажа, если рынок слабеет.\n"
        f"· Сравнить с ценой сделки: /deal {gift.collection} #{gift.number} | <цена TON>\n"
    )
    if conf < 50:
        actions += "\n⚠️ Уверенность низкая — это ориентир, не обещание прибыли.\n"
    body = (
        f"\n📝 Почему так (модель)\n{why_lines}\n\n"
        f"{actions}\n"
        f"{pq}\n"
        "⚠️ Оценки сценарные; рынок может измениться.\n"
    )
    if compact:
        return header + mock_banner + block + "\n" + pq + "\n"
    return header + mock_banner + block + body + "\n📖 Расширенный режим — см. блок выше.\n"


def format_gift_deal_card(
    gift: GiftCard,
    estimate: Any,
    quality: MarketDataQuality | None,
    stats: dict | None,
    buy_price: float,
) -> str:
    if getattr(estimate, "pricing_suppressed", False):
        pq = format_source_quality_compact(quality, stats, estimate=estimate)
        return (
            f"💰 Сделка · {gift.collection} #{gift.number}\n"
            f"Цена входа: {buy_price:.2f} TON\n"
            f"Вердикт: 🟡 Мало данных — NEED_MORE_DATA\n"
            "Я вижу цену входа, но не вижу реальный рынок. Нельзя честно сказать, за сколько продавать.\n"
            f"{pq}\n"
            "Добавьте /market_quick или подключите Getgems/Tonnel/Fragment.\n"
        )
    conf = int(getattr(estimate, "confidence_score", 0) or 0)
    verdict_line = _brain_verdict_line(estimate, conf)
    pq = format_source_quality_compact(quality, stats, estimate=estimate)
    fair = float(getattr(estimate, "fair_price_ton", 0) or 0)
    list_t = getattr(estimate, "normal_list_price_ton", None) or getattr(estimate, "list_price_ton", None)
    net = getattr(estimate, "expected_net_sale_ton", None)
    roi = float(getattr(estimate, "expected_roi_percent", 0) or 0)
    profit = float(getattr(estimate, "expected_profit_ton", 0) or 0)
    safe_b = getattr(estimate, "safe_buy_price_ton", None)
    max_b = getattr(estimate, "buy_zone_max_ton", None)
    qsell = getattr(estimate, "quick_sell_price_ton", None)
    stop = getattr(estimate, "stop_price_ton", None)
    overpay = ""
    if max_b is not None and buy_price > max_b:
        overpay = f"\n⚠️ Сделка слабая относительно плана — лучше брать дешевле ~{max_b:.1f} TON."
    elif safe_b is not None and buy_price <= safe_b:
        overpay = "\nЦена в safe-зоне относительно модели; исход не гарантирован."
    else:
        overpay = "\nЦена между safe и max buy — проверьте ликвидность и продажи по trait."
    return (
        f"💰 Сделка · {gift.collection} #{gift.number}\n"
        f"Цена покупки: {buy_price:.2f} TON\n"
        f"{verdict_line}\n"
        f"· Безопасная покупка: {safe_b} · Макс.: {max_b}\n"
        f"· Справедливая: ~{fair:.0f} TON · Цель листинга: {list_t} TON\n"
        f"· Быстрая продажа: {qsell} · Стоп: {stop}\n"
        f"Чистая продажа (оценка): {net} TON\n"
        f"Прибыль (сценарий): {profit:+.2f} TON · ROI: {roi:+.1f}%\n"
        f"Уверенность: {conf}/100\n"
        f"{pq}\n"
        f"{overpay}\n"
        "⚠️ Только аналитика, без гарантии прибыли.\n"
    )


def format_gift_watchlist_card(gift: GiftCard, gift_id: int, updated: bool) -> str:
    action = "обновил данные" if updated else "добавлен"
    return f"{'✅ Уже в watchlist,' if updated else '✅'} {action}: {gift.collection} #{gift.number} (id={gift_id})"


def format_gift_error_help(context: str = "check") -> str:
    base = (
        "Я не смог понять подарок. Пришли так:\n"
        f"- /{context} Ice Cream #217467\n"
        f"- /{context} <NFT address>\n"
        f"- /{context} <ссылка маркетплейса>\n"
    )
    return base


def format_unknown_gift_input_help(
    raw_input: str,
    warnings: list[str] | None = None,
    *,
    context: str = "check",
) -> str:
    w = warnings or []
    lines = [
        "Я не смог надёжно понять Gift.",
        "",
        "Примеры:",
        f"- /{context} Ice Cream #217467",
        f"- /{context} <NFT address>",
        f"- /{context} <ссылка Getgems / Fragment / Tonviewer>",
        "- /add <ссылка>",
        "- /deal <ссылка> | 180",
        "",
        "Если ссылка похожа на Fragment, Tonviewer или Getgems, но в ней недостаточно данных — пришли коллекцию + номер или NFT address.",
        "Обратная связь: /feedback",
    ]
    if w:
        lines.insert(1, "Заметки: " + "; ".join(w[:3]))
    _ = raw_input  # reserved for future: quote truncated snippet
    return "\n".join(lines)


def format_passive_gift_mini_card(resolved_title: str, check_hint: str, add_hint: str, deal_hint: str) -> str:
    return (
        f"Похоже, это Gift/NFT\n{resolved_title}\n\n"
        f"Что сделать?\n{check_hint}\n{add_hint}\n{deal_hint}\n\n"
        "Или нажми кнопку ниже."
    )

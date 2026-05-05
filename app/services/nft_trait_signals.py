"""Сигналы рынка по отдельным трейтам (TonAPI listings) для trait-aware pricing — без mock."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.services.nft_market_pricing_core import (
    OTHER_TRAIT_WEIGHT,
    canonical_trait_type_key,
    effective_target_traits,
    filter_outliers_enhanced,
    float_price_row,
    norm_trait_val,
    row_trait_val,
    trait_vals_match,
)

_TRAIT_LABEL_RU: dict[str, str] = {
    "model": "Model",
    "backdrop": "Backdrop",
    "symbol": "Symbol",
    "pattern": "Pattern",
    "class": "Class",
    "edition": "Edition",
    "breed": "Breed",
}


def trait_label_ru(trait_key: str) -> str:
    return _TRAIT_LABEL_RU.get(trait_key, trait_key.replace("_", " ").title())


def listing_median_ton(rows: Sequence[Any], *, exclude_address: str | None) -> float | None:
    ps: list[float] = []
    ex = (exclude_address or "").strip()
    for r in rows:
        if not getattr(r, "for_sale", False):
            continue
        fp = float_price_row(r)
        if fp is None or fp <= 0:
            continue
        if ex and str(getattr(r, "address", "") or "").strip() == ex:
            continue
        ps.append(fp)
    return float(statistics.median(ps)) if ps else None


def harmonize_collection_median(listing_median: float | None, reported_cm: float | None) -> float | None:
    """Если переданная медиана коллекции сильно выше реальных листингов — берём медиану листингов (TonAPI/кэш могут расходиться)."""
    if listing_median is None or listing_median <= 0:
        return reported_cm
    if reported_cm is None or reported_cm <= 0:
        return listing_median
    if reported_cm > listing_median * 2.75:
        return listing_median
    return reported_cm


def _support_level(n: int) -> str:
    if n <= 0:
        return "none"
    if n <= 2:
        return "low"
    if n <= 7:
        return "medium"
    return "high"


def _confidence_for_signal(support: str, listings: int) -> str:
    if support == "high" or listings >= 12:
        return "high"
    if support == "medium" or listings >= 5:
        return "medium"
    return "low"


def _price_signal(
    median_trait: float | None,
    coll_median: float | None,
    listings: int,
) -> str:
    if listings < 3 or median_trait is None or not coll_median or coll_median <= 0:
        return "unclear"
    if median_trait >= coll_median * 1.25:
        return "premium"
    if median_trait <= coll_median * 0.85:
        return "discount"
    return "near_market"


def _percentile_sorted(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * q
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    t = k - f
    return float(sorted_vals[f] * (1 - t) + sorted_vals[c] * t)


@dataclass
class TraitMarketSignal:
    trait_key: str
    trait_label: str
    trait_value: str
    listings_count: int
    floor_ton: float | None
    median_ton: float | None
    p25_ton: float | None
    p75_ton: float | None
    sample_prices: list[float] = field(default_factory=list)
    market_floor_ratio: float | None = None
    market_median_ratio: float | None = None
    support_level: str = "none"
    price_signal: str = "unclear"
    confidence: str = "low"
    weight: float = 0.25
    explanation: str = ""


def _rows_for_trait_value(
    rows: Sequence[Any],
    trait_key: str,
    trait_value: str,
    *,
    exclude_address: str | None,
) -> list[Any]:
    ex = (exclude_address or "").strip()
    out: list[Any] = []
    ck = trait_key
    for r in rows:
        if not getattr(r, "for_sale", False):
            continue
        if float_price_row(r) is None:
            continue
        addr = str(getattr(r, "address", "") or "").strip()
        if ex and addr == ex:
            continue
        if trait_vals_match(trait_value, row_trait_val(r, ck)):
            out.append(r)
    return out


def compute_trait_market_signals(
    target: Any,
    rows: Sequence[Any],
    *,
    collection_floor: float | None,
    collection_median: float | None,
    trait_weights: Mapping[str, float],
    exclude_address: str | None = None,
    sample_cap: int = 24,
) -> list[TraitMarketSignal]:
    et = effective_target_traits(target)
    cf = float(collection_floor) if collection_floor and collection_floor > 0 else None
    cm = float(collection_median) if collection_median and collection_median > 0 else None
    signals: list[TraitMarketSignal] = []
    for raw_k, raw_v in et.items():
        val = str(raw_v).strip()
        if not val:
            continue
        ck = canonical_trait_type_key(str(raw_k))
        matched = _rows_for_trait_value(rows, ck, val, exclude_address=exclude_address)
        prices_raw = sorted(p for p in (float_price_row(r) for r in matched) if p is not None and p > 0)
        fr0 = filter_outliers_enhanced(list(prices_raw))
        prices = fr0.used_prices if fr0.used_prices else list(prices_raw)
        n = len(prices)
        sup = _support_level(n)
        fl = min(prices) if prices else None
        med = float(statistics.median(prices)) if prices else None
        p25 = _percentile_sorted(prices, 0.25) if len(prices) >= 2 else (prices[0] if prices else None)
        p75 = _percentile_sorted(prices, 0.75) if len(prices) >= 2 else (prices[-1] if prices else None)
        mfr = (fl / cf) if (fl and cf) else None
        mmr = (med / cm) if (med and cm) else None
        ps = _price_signal(med, cm, n)
        conf = _confidence_for_signal(sup, n)
        wt = float(trait_weights.get(ck, OTHER_TRAIT_WEIGHT))
        expl_parts: list[str] = []
        if sup == "none":
            expl_parts.append("Нет листингов с ценой по этому значению трейта.")
        elif sup == "low":
            expl_parts.append("Очень мало похожих листингов — трейт учитывается осторожно.")
        elif ps == "premium":
            expl_parts.append("Похожие листинги обычно дороже середины коллекции.")
        elif ps == "discount":
            expl_parts.append("Похожие листинги обычно дешевле середины коллекции.")
        elif ps == "near_market":
            expl_parts.append("Цены близки к среднему рынку коллекции.")
        else:
            expl_parts.append("Мало данных, чтобы уверенно оценить влияние трейта.")
        signals.append(
            TraitMarketSignal(
                trait_key=ck,
                trait_label=trait_label_ru(ck),
                trait_value=val,
                listings_count=n,
                floor_ton=fl,
                median_ton=med,
                p25_ton=p25,
                p75_ton=p75,
                sample_prices=prices[:sample_cap],
                market_floor_ratio=mfr,
                market_median_ratio=mmr,
                support_level=sup,
                price_signal=ps,
                confidence=conf,
                weight=wt,
                explanation=" ".join(expl_parts),
            )
        )
    # Model, Symbol, Backdrop first for stable report order
    order = {"model": 0, "symbol": 1, "backdrop": 2}
    signals.sort(key=lambda s: (order.get(s.trait_key, 9), s.trait_key))
    return signals


def compute_trait_adjusted_median(
    collection_median: float | None,
    signals: Sequence[TraitMarketSignal],
    trait_weights: Mapping[str, float],
) -> float | None:
    """Взвешенный множитель к медиане коллекции по трейтам с support >= medium."""
    if not collection_median or collection_median <= 0:
        return None
    ratios: list[float] = []
    weights: list[float] = []
    for s in signals:
        if s.support_level not in ("medium", "high"):
            continue
        if s.median_ton is None or s.median_ton <= 0:
            continue
        sp = sorted(s.sample_prices)
        if len(sp) >= 3 and (max(sp) / min(sp)) > 22 and s.listings_count < 8:
            continue
        ratio = max(0.75, min(1.75, s.median_ton / collection_median))
        conf_m = {"high": 1.0, "medium": 0.85, "low": 0.4}.get(s.confidence, 0.5)
        wt = float(trait_weights.get(s.trait_key, OTHER_TRAIT_WEIGHT)) * conf_m
        if s.price_signal == "unclear":
            wt *= 0.25
        elif s.price_signal == "discount":
            wt *= 0.92
        ratios.append(ratio)
        weights.append(wt)
    if not ratios:
        return None
    num = sum(r * w for r, w in zip(ratios, weights))
    den = sum(weights)
    if den <= 0:
        return None
    return round(float(collection_median) * (num / den), 4)


def human_trait_impact_block(signals: Sequence[TraitMarketSignal]) -> str:
    """Короткий блок для отчёта (без технических имён групп)."""
    lines: list[str] = []
    for s in signals:
        lines.append(f"{s.trait_label} = {s.trait_value}")
        lines.append(s.explanation)
        lines.append("")
    return "\n".join(lines).strip()


def human_cohort_explanation_ru(
    *,
    group_key: str,
    n_used: int,
    has_trait_adjustment: bool,
) -> str:
    if group_key == "exact_primary_match" and n_used >= 5:
        return "Нашлось достаточно очень похожих NFT по ключевым трейтам — на них в первую очередь опираюсь."
    if group_key in ("exact_primary_match", "top2_primary_match") and n_used < 4:
        return (
            "Точных совпадений по всем ключевым трейтам мало. "
            "Добавил сравнение по отдельным трейтам и похожим листингам, чтобы не зависеть от одного узкого набора."
        )
    if group_key == "top1_primary_match":
        return "Опираюсь на листинги с совпадением по главному трейту и проверку остальных трейтов отдельно."
    if group_key == "weighted_close_comps":
        return "Много частичных совпадений: беру похожие по набору трейтов с весами, плюс сигналы по каждому трейту."
    if group_key == "collection_market":
        base = "База — общий рынок коллекции по активным листингам."
        if has_trait_adjustment:
            return base + " Цену подправил по трейтам, чтобы не ориентироваться только на общий floor."
        return base
    return "Сопоставил ваш NFT с рынком коллекции и трейтами."


def price_range_hint_ru(used_prices: Sequence[float]) -> str:
    if not used_prices:
        return ""
    u = sorted(float(p) for p in used_prices if p and p > 0)
    if not u:
        return ""
    lo = u[0]
    hi = u[-1]
    med = float(statistics.median(u))
    if len(u) >= 5:
        p25 = _percentile_sorted(u, 0.25) or lo
        p75 = _percentile_sorted(u, 0.75) or hi
        return (
            f"Ориентир по похожей выборке: дешёвый край около {_fmt_ton_us(p25)}–{_fmt_ton_us(lo)} TON, "
            f"середина около {_fmt_ton_us(med)} TON, верх около {_fmt_ton_us(p75)}–{_fmt_ton_us(hi)} TON."
        )
    return f"Диапазон цен в выборке: примерно от {_fmt_ton_us(lo)} до {_fmt_ton_us(hi)} TON (середина ~{_fmt_ton_us(med)})."


def _fmt_ton_us(x: float) -> str:
    s = f"{float(x):.3f}".rstrip("0").rstrip(".")
    return s


def listing_verdict_ru(
    *,
    for_sale: bool,
    sale_price_ton: float | None,
    quick: float | None,
    normal: float | None,
    high: float | None,
) -> str:
    if not for_sale or sale_price_ton is None or sale_price_ton <= 0:
        if normal is not None:
            return f"Лучший старт для листинга: около {_fmt_ton_us(normal)} TON (по активным объявлениям TonAPI)."
        return "Мало данных, чтобы назвать точную цену листинга — ориентируйтесь на диапазон ниже."
    sp = float(sale_price_ton)
    q = float(quick) if quick is not None and quick > 0 else None
    n = float(normal) if normal is not None and normal > 0 else None
    h = float(high) if high is not None and high > 0 else None
    if n is not None:
        ratio = sp / n
        if ratio >= 3:
            return (
                f"NFT уже выставлена за {_fmt_ton_us(sp)} TON — это сильно выше рынка похожих NFT. "
                f"Если цель — продать, разумный старт ближе к {_fmt_ton_us(n)} TON."
            )
        if ratio >= 1.5:
            return (
                f"NFT уже выставлена за {_fmt_ton_us(sp)} TON — выше рынка похожих NFT. "
                f"Более реалистичный старт обычно ближе к {_fmt_ton_us(n)} TON."
            )
    if q is not None and sp <= q * 1.02:
        return "Сейчас цена выглядит дёшево относительно похожих листингов."
    if q is not None and n is not None and sp > q and sp <= n * 1.05:
        return "Цена выглядит нормальной для продажи среди похожих объявлений."
    if n is not None and h is not None and sp > n * 0.95 and sp <= h * 1.1:
        return "Цена выше середины рынка — можно ждать покупателя."
    if h is not None and sp > h * 1.25:
        return "Цена заметно выше похожих листингов — продажа может занять больше времени."
    return "Цена в пределах разумного разброса по похожим лотам."


def final_listing_advice_ru(
    *,
    dont_below: float | None,
    normal: float | None,
    has_premium_trait: bool,
) -> str:
    parts: list[str] = []
    if normal is not None:
        parts.append(f"Разумный старт: около {_fmt_ton_us(normal)} TON.")
    if dont_below is not None:
        if has_premium_trait:
            parts.append(
                f"Ниже {_fmt_ton_us(dont_below)} TON выставлять обычно невыгодно: по трейтам видна поддержка цены выше «голого» floor коллекции."
            )
        else:
            parts.append(f"Ниже {_fmt_ton_us(dont_below)} TON выставлять, как правило, невыгодно относительно выбранной выборки.")
    return " ".join(parts) if parts else ""


def market_position_verdict_ru(
    *,
    normal: float | None,
    collection_median: float | None,
    trait_adjusted: float | None,
    n_comps_used: int,
) -> str:
    ref = normal
    if ref is None and trait_adjusted is not None:
        ref = trait_adjusted
    if ref is None or not collection_median or collection_median <= 0:
        return "Данных мало для точного вывода относительно всей коллекции."
    r = ref / float(collection_median)
    if n_comps_used < 3 and r > 1.08:
        return "Похоже дороже типичной середины коллекции, но выборка похожих NFT небольшая — трактуйте осторожно."
    if r < 0.88:
        return "Относительно общей середины коллекции этот набор трейтов выглядит дешевле рынка."
    if r <= 1.1:
        return "Относительно общей середины коллекции — около типичного уровня."
    if r <= 1.32:
        return "Выше типичной середины коллекции — часто так бывает из‑за редких трейтов."
    return "Сильно выше типичной середины коллекции — нужен уверенный спрос, иначе листинг может простаивать."

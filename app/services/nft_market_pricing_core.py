"""Collection-local NFT listing pricing: trait weights, weighted comps, robust outliers, confidence score."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


# Нормализация имён типов трейтов (ключи в traits_normalized — lower)
TRAIT_TYPE_ALIASES: dict[str, str] = {
    "model": "model",
    "backdrop": "backdrop",
    "symbol": "symbol",
    "pattern": "pattern",
    "class": "class",
    "class_type": "class",
    "edition": "edition",
    "breed": "breed",
}


def canonical_trait_type_key(raw: str) -> str:
    k = (raw or "").strip().lower().replace(" ", "_")
    return TRAIT_TYPE_ALIASES.get(k, k)


def norm_trait_val(v: str | None) -> str:
    return (v or "").strip().casefold()


def trait_vals_match(a: str | None, b: str | None) -> bool:
    return bool(a and b) and norm_trait_val(a) == norm_trait_val(b)


def effective_target_traits(target: Any) -> dict[str, str]:
    m = dict(getattr(target, "traits_normalized", None) or {})
    for attr in ("model", "backdrop", "symbol"):
        v = getattr(target, attr, None)
        if v and str(v).strip():
            k = attr.lower()
            m.setdefault(k, str(v).strip())
    return m


def row_trait_val(row: Any, key: str) -> str | None:
    traits = getattr(row, "traits_normalized", None) or {}
    if isinstance(traits, Mapping) and key in traits:
        v = traits.get(key)
        return str(v).strip() if v is not None else None
    return getattr(row, key, None)


def float_price_row(row: Any) -> float | None:
    pt = getattr(row, "price_ton", None)
    if pt is None:
        return None
    try:
        fp = float(pt)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fp) or fp <= 0:
        return None
    return fp


DEFAULT_WEIGHT_FALLBACK: dict[str, float] = {
    "model": 1.0,
    "symbol": 0.65,
    "backdrop": 0.45,
    "pattern": 0.5,
    "class": 0.5,
    "edition": 0.45,
    "breed": 0.45,
}
OTHER_TRAIT_WEIGHT = 0.25
WEIGHT_CAP = 1.25
WEIGHT_FLOOR = 0.15


def load_collection_trait_weights_override(collection_name: str, registry: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not registry or not collection_name:
        return None
    payload = registry.get(collection_name)
    if not isinstance(payload, dict):
        return None
    tw = payload.get("trait_weights")
    if not isinstance(tw, dict):
        return None
    out: dict[str, float] = {}
    for k, v in tw.items():
        ck = canonical_trait_type_key(str(k))
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv > 0:
            out[ck] = max(WEIGHT_FLOOR, min(WEIGHT_CAP, fv))
    return out or None


def resolve_final_trait_weights(
    collection_name: str,
    registry: Mapping[str, Any] | None,
    rows: Sequence[Any],
    *,
    exclude_address: str | None,
    target: Any | None = None,
) -> dict[str, float]:
    """Смешивание весов: registry (если есть), auto (при достаточном рынке), иначе default по ключам target + известным трейтам."""
    default = dict(DEFAULT_WEIGHT_FALLBACK)
    config = load_collection_trait_weights_override(collection_name, registry)
    auto = infer_auto_trait_weights(rows, exclude_address=exclude_address)
    auto_stable = bool(auto)

    keys: set[str] = set(default.keys())
    if config:
        keys |= set(config.keys())
    if auto:
        keys |= set(auto.keys())
    if target is not None:
        for k in effective_target_traits(target):
            keys.add(canonical_trait_type_key(str(k)))

    out: dict[str, float] = {}
    for ck in sorted(keys):
        dv = float(default.get(ck, OTHER_TRAIT_WEIGHT))
        av = auto.get(ck) if auto else None
        cv = config.get(ck) if config else None
        if cv is not None and av is not None and auto_stable:
            fw = 0.5 * float(cv) + 0.5 * float(av)
        elif cv is not None:
            fw = 0.7 * float(cv) + 0.3 * dv
        elif av is not None and auto_stable:
            fw = float(av)
        else:
            fw = dv
        out[ck] = max(0.15, min(1.0, float(fw)))
    return out


def _listing_rows_with_price(rows: Sequence[Any], *, exclude_address: str | None) -> list[Any]:
    out: list[Any] = []
    ex = (exclude_address or "").strip()
    for r in rows:
        if not getattr(r, "for_sale", False):
            continue
        fp = float_price_row(r)
        if fp is None:
            continue
        addr = str(getattr(r, "address", "") or "").strip()
        if ex and addr == ex:
            continue
        out.append(r)
    return out


def infer_auto_trait_weights(rows: Sequence[Any], *, exclude_address: str | None = None) -> dict[str, float]:
    """Impact trait keys via median log-price deviation; capped; weak if мало значений."""
    listings = _listing_rows_with_price(rows, exclude_address=exclude_address)
    if len(listings) < 20:
        return {}

    all_prices = [float_price_row(r) for r in listings]
    all_prices = [p for p in all_prices if p is not None]
    if len(all_prices) < 20:
        return {}
    coll_med = float(statistics.median(all_prices))
    if coll_med <= 0:
        return {}

    key_values: dict[str, dict[str, list[float]]] = {}
    for r in listings:
        p = float_price_row(r)
        if p is None:
            continue
        traits = getattr(r, "traits_normalized", None) or {}
        if not isinstance(traits, dict):
            continue
        for raw_k, raw_v in traits.items():
            ck = canonical_trait_type_key(str(raw_k))
            val = str(raw_v).strip()
            if not val:
                continue
            key_values.setdefault(ck, {}).setdefault(norm_trait_val(val), []).append(p)

    impacts: dict[str, float] = {}
    for ck, buckets in key_values.items():
        if len(buckets) < 2:
            continue
        medians: list[float] = []
        weights_n: list[int] = []
        for vals in buckets.values():
            if len(vals) < 2:
                continue
            medians.append(float(statistics.median(vals)))
            weights_n.append(len(vals))
        if len(medians) < 2:
            continue
        devs: list[float] = []
        for m, n in zip(medians, weights_n):
            devs.append(abs(math.log(max(m, 1e-9)) - math.log(max(coll_med, 1e-9))) * math.sqrt(min(n, 12)))
        impact = float(statistics.median(devs)) if devs else 0.0
        total_n = sum(len(v) for v in buckets.values())
        if total_n < 6:
            impact *= total_n / 6.0
        impacts[ck] = impact

    if not impacts:
        return {}

    mx = max(impacts.values()) or 1e-9
    out: dict[str, float] = {}
    for ck, imp in impacts.items():
        w = OTHER_TRAIT_WEIGHT + (imp / mx) * (WEIGHT_CAP - OTHER_TRAIT_WEIGHT)
        out[ck] = max(WEIGHT_FLOOR, min(WEIGHT_CAP, w))
    return out


def resolve_trait_weights(
    collection_name: str,
    registry: Mapping[str, Any] | None,
    rows: Sequence[Any],
    *,
    exclude_address: str | None,
) -> dict[str, float]:
    override = load_collection_trait_weights_override(collection_name, registry)
    if override:
        return dict(override)
    auto = infer_auto_trait_weights(rows, exclude_address=exclude_address)
    if auto:
        return auto
    return dict(DEFAULT_WEIGHT_FALLBACK)


def pick_primary_trait_keys(target: Any, weights: Mapping[str, float], *, top_n: int = 3) -> list[str]:
    et = effective_target_traits(target)
    scored: list[tuple[float, str]] = []
    for k, v in et.items():
        if not str(v).strip():
            continue
        ck = canonical_trait_type_key(str(k))
        w = float(weights.get(ck, OTHER_TRAIT_WEIGHT))
        scored.append((w, ck))
    scored.sort(key=lambda x: -x[0])
    seen: set[str] = set()
    out: list[str] = []
    for _, ck in scored:
        if ck in seen:
            continue
        seen.add(ck)
        out.append(ck)
        if len(out) >= top_n:
            break
    return out


def similarity_weighted(target: Any, row: Any, weights: Mapping[str, float]) -> float:
    et = effective_target_traits(target)
    matched = 0.0
    total = 0.0
    for k, tv in et.items():
        if not str(tv).strip():
            continue
        ck = canonical_trait_type_key(str(k))
        w = float(weights.get(ck, OTHER_TRAIT_WEIGHT))
        total += w
        if trait_vals_match(tv, row_trait_val(row, ck)):
            matched += w
    return (matched / total) if total > 0 else 0.0


def primary_match_count(target: Any, row: Any, primary_keys: Sequence[str]) -> int:
    et = effective_target_traits(target)
    n = 0
    for ck in primary_keys:
        tv = et.get(ck)
        if not tv or not str(tv).strip():
            continue
        if trait_vals_match(tv, row_trait_val(row, ck)):
            n += 1
    return n


@dataclass
class EnhancedFilterResult:
    used_prices: list[float]
    removed_low_outliers: list[float]
    removed_high_outliers: list[float]
    method: str
    reason: str

    @property
    def all_removed(self) -> list[float]:
        return sorted(set(self.removed_low_outliers + self.removed_high_outliers))


def filter_outliers_enhanced(prices: list[float]) -> EnhancedFilterResult:
    prices = sorted({float(p) for p in prices if p and p > 0 and math.isfinite(float(p))})
    if len(prices) < 3:
        return EnhancedFilterResult(
            list(prices),
            [],
            [],
            "insufficient",
            "Меньше трёх цен — выбросы не отделялись.",
        )

    aggressive = len(prices) >= 5
    logs = [math.log(p) for p in prices]
    log_med = float(statistics.median(logs))
    log_devs = [abs(x - log_med) for x in logs]
    log_mad = float(statistics.median(log_devs))
    low_out: set[float] = set()
    high_out: set[float] = set()

    if log_mad > 1e-12 and aggressive:
        denom = 1.4826 * log_mad
        for p, lg in zip(prices, logs, strict=False):
            if abs(lg - log_med) / denom > 3.5:
                if lg < log_med:
                    low_out.add(p)
                else:
                    high_out.add(p)

    # Tukey IQR на уровне цен (дополнительно), только при n>=5
    if len(prices) >= 5:
        q1, q2, q3 = statistics.quantiles(prices, n=4, method="inclusive")
        iqr = max(q3 - q1, 1e-9)
        low_fence = q1 - 1.5 * iqr
        high_fence = q3 + 1.5 * iqr
        for p in prices:
            if p < low_fence:
                low_out.add(p)
            if p > high_fence:
                high_out.add(p)

    med = float(statistics.median(prices))
    below_med = [p for p in prices if p < med]
    for p in prices:
        if p in low_out or p in high_out:
            continue
        if p > med * 3 and len([x for x in below_med if x < p]) >= 3:
            high_out.add(p)

    k = min(5, len(prices))
    if k >= 3:
        head = prices[:k]
        hmax = max(head)
        for p in prices[k:]:
            if p >= hmax * 3:
                high_out.add(p)

    # thin-floor: одиночный минимум, следующий скачок ≥3x и дальше плотный ряд
    if len(prices) >= 4:
        p0, p1 = prices[0], prices[1]
        if p0 > 0 and p1 >= 3 * p0:
            tail = prices[2:]
            if len(tail) >= 2:
                tail_med = float(statistics.median(tail))
                if tail_med >= 2 * p0 and p1 >= 2.5 * p0:
                    low_out.add(p0)

    used = sorted(p for p in prices if p not in low_out and p not in high_out)
    if not used:
        return EnhancedFilterResult(
            list(prices),
            [],
            [],
            "reverted",
            "После фильтра не осталось цен — показан полный ряд.",
        )
    return EnhancedFilterResult(
        used,
        sorted(low_out),
        sorted(high_out),
        "log_mad_iqr_heuristics",
        "Log-MAD (modified z), IQR/Tukey, защита от тонкого floor и высокого хвоста.",
    )


def floor_anchor_from_used(used_sorted: Sequence[float]) -> float:
    u = sorted(used_sorted)
    if not u:
        return 0.0
    # После фильтра выбросов минимум — якорь «стабильного» ряда (тонкий undercut уже снят фильтром).
    return float(u[0])


def derive_price_band_from_used(used: list[float], *, floor_anchor: float) -> tuple[float, float, float, float] | None:
    if not used:
        return None
    u = sorted(used)
    med = float(statistics.median(u))
    dont = round(float(floor_anchor) * 0.93, 4)
    quick = round(float(floor_anchor) * 0.97, 4)
    normal = round(med, 4)
    if len(u) >= 5:
        try:
            qs = statistics.quantiles(u, n=4, method="inclusive")
            high = round(float(qs[2]), 4)
        except Exception:
            high = round(float(max(u)), 4)
    else:
        high = round(float(max(u)), 4)
    return quick, normal, high, dont


def price_stability_score(prices: Sequence[float]) -> float:
    if len(prices) < 2:
        return 0.35
    m = float(statistics.median(prices))
    if m <= 0:
        return 0.35
    mad = float(statistics.median(abs(p - m) for p in prices))
    return 1.0 / (1.0 + 3.0 * mad / m)


def group_quality_score(
    *,
    tier: int,
    n_used: int,
    raw_n: int,
    used_prices: Sequence[float],
    removed_total: int,
) -> float:
    """Выше — лучше. tier: exact=5, top2=4, top1=3, weighted=2, collection=1."""
    if n_used <= 0:
        return -1.0
    stab = price_stability_score(used_prices)
    outlier_ratio = removed_total / max(raw_n, 1)
    sample = math.log1p(n_used)
    return tier * 1.15 + sample * 0.85 + stab * 2.0 - outlier_ratio * 1.2


def label_for_group_key(key: str) -> str:
    return {
        "exact_primary_match": "Точное совпадение ключевых трейтов",
        "top2_primary_match": "Совпадение 2 из 3 ключевых трейтов",
        "top1_primary_match": "Совпадение главного трейта",
        "weighted_close_comps": "Похожие по весам трейтов",
        "collection_market": "Общий рынок коллекции",
    }.get(key, key)


def select_best_listing_group(
    target: Any,
    candidates: Sequence[Any],
    weights: Mapping[str, float],
    primary_keys: Sequence[str],
) -> tuple[str, list[Any], EnhancedFilterResult, list[float], float]:
    """Возвращает (group_key, rows_in_group, filter_result, used_prices, floor_anchor)."""
    if not candidates:
        return "collection_market", [], EnhancedFilterResult([], [], [], "empty", "Нет кандидатов."), [], 0.0

    pkeys = list(primary_keys)
    need_exact = min(3, len(pkeys)) if pkeys else 0

    def exact_row(r: Any) -> bool:
        if need_exact <= 0:
            return False
        return primary_match_count(target, r, pkeys[:need_exact]) >= need_exact

    exact_rows = [r for r in candidates if exact_row(r)] if need_exact else []

    def top2_row(r: Any) -> bool:
        if len(pkeys) < 2:
            return False
        return primary_match_count(target, r, pkeys[:2]) >= 2

    top2_rows = [r for r in candidates if top2_row(r)]

    def top1_row(r: Any) -> bool:
        if not pkeys:
            return False
        return primary_match_count(target, r, pkeys[:1]) >= 1

    top1_rows = [r for r in candidates if top1_row(r)]

    w_thresh = 0.55
    weighted_rows = [r for r in candidates if similarity_weighted(target, r, weights) >= w_thresh]

    tiers = {
        "exact_primary_match": (5, exact_rows, 3, 2),
        "top2_primary_match": (4, top2_rows, 3, 2),
        "top1_primary_match": (3, top1_rows, 3, 2),
        "weighted_close_comps": (2, weighted_rows, 5, 3),
        "collection_market": (1, list(candidates), 1, 1),
    }

    best: tuple[float, str, list[Any], EnhancedFilterResult, list[float], float] | None = None

    for key, (tier, group_rows, min_raw, min_used) in tiers.items():
        raw_prices = sorted(
            p for p in (float_price_row(r) for r in group_rows) if p is not None and p > 0
        )
        if len(raw_prices) < min_raw:
            continue
        fr = filter_outliers_enhanced(raw_prices)
        used = fr.used_prices
        if not used:
            continue
        if key != "collection_market" and len(used) < min_used:
            continue
        fa = floor_anchor_from_used(used)
        removed = len(fr.removed_low_outliers) + len(fr.removed_high_outliers)
        gq = group_quality_score(
            tier=tier,
            n_used=len(used),
            raw_n=len(raw_prices),
            used_prices=used,
            removed_total=removed,
        )
        cand = (gq, key, group_rows, fr, used, fa)
        if best is None or gq > best[0]:
            best = cand

    if best is None:
        coll = list(candidates)
        raw_prices = sorted(p for p in (float_price_row(r) for r in coll) if p is not None and p > 0)
        if not raw_prices:
            return "collection_market", [], EnhancedFilterResult([], [], [], "empty", "Нет цен."), [], 0.0
        fr = filter_outliers_enhanced(raw_prices)
        used = fr.used_prices or raw_prices
        fa = floor_anchor_from_used(used)
        return "collection_market", coll, fr, used, fa

    _gq, key, group_rows, fr, used, fa = best
    # noisy exact fallback: если exact выбран, но мало used, а top1 стабильнее — переключить
    if key == "exact_primary_match" and len(used) < 3:
        alt = top1_rows
        rp2 = sorted(p for p in (float_price_row(r) for r in alt) if p is not None and p > 0)
        if len(rp2) >= 5:
            fr2 = filter_outliers_enhanced(rp2)
            if len(fr2.used_prices) >= max(len(used), 5):
                fa2 = floor_anchor_from_used(fr2.used_prices)
                return "top1_primary_match", alt, fr2, fr2.used_prices, fa2

    return key, group_rows, fr, used, fa


def confidence_score_from_signals(
    *,
    group_key: str,
    n_clean: int,
    is_partial_scan: bool,
    loaded_count: int,
    max_items: int,
    cache_age_minutes: float | None,
    collection_market_fallback: bool,
) -> tuple[int, str, str]:
    """Возвращает (0..100 score, label high|medium|low, короткое пояснение)."""
    relevance = {"exact_primary_match": 32, "top2_primary_match": 28, "top1_primary_match": 22, "weighted_close_comps": 16, "collection_market": 8}.get(group_key, 10)
    sample = min(28, 4 + n_clean * 3)
    stability = min(18, 6 + n_clean * 2)
    coverage = 14 if not is_partial_scan else 6
    if is_partial_scan and loaded_count >= int(max_items * 0.95):
        coverage = 3
    freshness = 12
    if cache_age_minutes is not None:
        if cache_age_minutes > 120:
            freshness = 4
        elif cache_age_minutes > 45:
            freshness = 7

    raw = relevance + sample + stability + coverage + freshness
    if collection_market_fallback or group_key == "collection_market":
        raw = min(raw, 52)
    if n_clean < 3:
        raw = min(raw, 38)
    if is_partial_scan and loaded_count >= int(max_items * 0.95):
        raw = min(raw, 62)

    score = int(max(0, min(100, raw)))
    if score >= 72:
        label = "high"
    elif score >= 45:
        label = "medium"
    else:
        label = "low"

    parts = [
        f"группа «{label_for_group_key(group_key)}»",
        f"очищенных цен: {n_clean}",
    ]
    if is_partial_scan:
        parts.append("скан частичный")
    if cache_age_minutes is not None and cache_age_minutes > 45:
        parts.append("данные из кэша")
    reason = "; ".join(parts) + ". Оценка по активным листингам, не по сделкам."
    return score, label, reason

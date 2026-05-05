"""Full collection market scan via TonAPI (active listings only), sell price planning — no mock."""

from __future__ import annotations

import asyncio
import html
import logging
import math
import re
import statistics
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.services.feature_limits import normalize_plan_for_limits
from app.services.nft_market_pricing_core import (
    canonical_trait_type_key,
    confidence_score_from_signals,
    derive_price_band_from_used,
    filter_outliers_enhanced,
    floor_anchor_from_used,
    label_for_group_key,
    pick_primary_trait_keys,
    resolve_final_trait_weights,
    select_best_listing_group,
    similarity_weighted,
)
from app.services.nft_trait_signals import (
    compute_trait_adjusted_median,
    compute_trait_market_signals,
    final_listing_advice_ru,
    harmonize_collection_median,
    human_cohort_explanation_ru,
    human_trait_impact_block,
    listing_median_ton,
    listing_verdict_ru,
    market_position_verdict_ru,
    price_range_hint_ru,
)
from app.services.nft_collection_resolve import normalize_collection_match_key, resolve_collection_address_by_name
from app.services.nft_tonapi_image import extract_nft_media_urls, extract_nft_preview_media
from app.services.tonapi_collection_client import TonAPICollectionClient
from app.sources.http import MarketSourceUnavailable
from app.sources.collections import load_collection_registry, resolve_collection

logger = logging.getLogger(__name__)

_DEFAULT_PAGE_LIMIT_FALLBACKS: tuple[int, ...] = (10000, 5000, 2000, 1000, 500, 200, 100)

_COLLECTION_SCAN_CACHE: dict[str, tuple[float, list["MarketNftRow"], bool, int, int | None]] = {}
_CACHE_LOCK = asyncio.Lock()

_NAME_NUM_RE = re.compile(r"#\s*(\d+)\s*$", re.IGNORECASE)


def parse_page_limit_fallbacks(raw: str | None) -> tuple[int, ...]:
    """Убывающая лестница лимитов из FULL_MARKET_PAGE_LIMIT_FALLBACKS (CSV)."""
    if not raw or not str(raw).strip():
        return _DEFAULT_PAGE_LIMIT_FALLBACKS
    vals: list[int] = []
    for part in str(raw).split(","):
        p = part.strip()
        if not p:
            continue
        try:
            v = int(p)
            if v > 0:
                vals.append(v)
        except ValueError:
            continue
    if not vals:
        return _DEFAULT_PAGE_LIMIT_FALLBACKS
    merged = set(vals)
    merged.update(_DEFAULT_PAGE_LIMIT_FALLBACKS)
    return tuple(sorted(merged, reverse=True))


def initial_full_scan_page_limit(settings: Settings) -> int:
    """Стартовый limit: наибольший из лестницы, не выше FULL_MARKET_PAGE_LIMIT и не ниже min."""
    ladder = parse_page_limit_fallbacks(settings.full_market_page_limit_fallbacks)
    min_lim = max(1, int(settings.full_market_min_page_limit))
    cap = max(1, min(int(settings.full_market_page_limit), int(settings.full_market_page_limit_max)))
    candidates = [x for x in ladder if min_lim <= x <= cap]
    if cap >= min_lim and cap not in candidates:
        candidates.append(cap)
    if not candidates:
        return min_lim
    start = max(candidates)
    if not bool(getattr(settings, "full_market_full_scan_enabled", True)):
        start = min(start, 1000)
    if (getattr(settings, "full_market_scan_mode", None) or "full").strip().lower() != "full":
        start = min(start, 1000)
    return max(min_lim, start)


def effective_collection_page_limit(settings: Settings) -> int:
    """Стартовый размер страницы TonAPI для full scan (адаптивная лестница)."""
    return initial_full_scan_page_limit(settings)


@dataclass
class MarketNftRow:
    name: str
    number: int | None
    address: str
    price_ton: Decimal | None
    for_sale: bool
    model: str | None
    backdrop: str | None
    symbol: str | None
    sale_market: str | None = None
    traits_normalized: dict[str, str] = field(default_factory=dict)


@dataclass
class TargetNftInfo:
    name: str
    number: int | None
    address: str
    collection_name: str
    collection_address: str
    model: str | None
    backdrop: str | None
    symbol: str | None
    traits_normalized: dict[str, str] = field(default_factory=dict)
    image_url: str | None = None
    preview_url: str | None = None
    # Анимация/видео с TonAPI (GIF/MP4/…): для Telegram answer_animation / answer_video, не answer_photo.
    rich_preview_url: str | None = None
    rich_preview_kind: str | None = None  # "animation" | "video" | None
    address_kind: str | None = None  # e.g. getgems_gift_ref — not a TonAPI NFT address


@dataclass
class TraitComps:
    trait_type: str
    trait_value: str | None
    listings_count: int
    floor: float | None
    median: float | None
    nearest: list[MarketNftRow] = field(default_factory=list)


@dataclass
class FilterResult:
    used_prices: list[float]
    outlier_prices: list[float]
    method: str
    reason: str
    removed_low_outliers: list[float] = field(default_factory=list)
    removed_high_outliers: list[float] = field(default_factory=list)


@dataclass
class SellPricePlan:
    quick_sell_ton: float | None
    normal_list_ton: float | None
    high_list_ton: float | None
    dont_list_below_ton: float | None
    confidence: str
    confidence_reason: str
    warnings: list[str] = field(default_factory=list)
    pricing_group_key: str = ""
    pricing_group_label_ru: str = ""
    comps_used_count: int = 0
    used_prices_ton: list[float] = field(default_factory=list)
    outlier_prices_ton: list[float] = field(default_factory=list)
    outlier_filter_note: str = ""
    used_collection_market_fallback: bool = False
    confidence_score: int = 0
    removed_low_outliers_ton: list[float] = field(default_factory=list)
    removed_high_outliers_ton: list[float] = field(default_factory=list)
    floor_anchor_ton: float | None = None
    primary_trait_keys: list[str] = field(default_factory=list)
    raw_prices_in_group_count: int = 0
    trait_signals: list[Any] = field(default_factory=list)
    trait_adjusted_median_ton: float | None = None
    listing_verdict_ru: str = ""
    market_position_ru: str = ""
    cohort_explanation_ru: str = ""
    trait_impact_block_ru: str = ""
    price_range_hint_ru: str = ""
    listing_advice_ru: str = ""
    target_listing_price_ton: float | None = None
    has_premium_traits: bool = False
    confidence_summary_ru: str = ""


@dataclass
class FullMarketNftReport:
    target: TargetNftInfo
    loaded_count: int
    listings_count: int
    collection_floor: float | None
    collection_median: float | None
    same_model: TraitComps
    same_backdrop: TraitComps
    same_symbol: TraitComps
    close_comps: list[MarketNftRow]
    sell_plan: SellPricePlan
    is_partial_scan: bool
    source_label: str
    warnings: list[str] = field(default_factory=list)
    cache_age_minutes: float | None = None
    collection_total_approx: int | None = None
    scan_target_source: str | None = None
    scan_market_source: str | None = None
    scan_target_address_kind: str | None = None


def parse_number_from_nft_name(name: str) -> int | None:
    m = _NAME_NUM_RE.search(name.strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _iter_attribute_lists(item: dict[str, Any]) -> list[list[Any]]:
    """Собирает списки атрибутов из metadata.attributes, traits, content.attributes и т.д."""
    out: list[list[Any]] = []
    if not isinstance(item, dict):
        return out
    for key in ("attributes", "traits"):
        v = item.get(key)
        if isinstance(v, list):
            out.append(v)
    meta = item.get("metadata")
    if isinstance(meta, dict):
        for key in ("attributes", "traits"):
            v = meta.get(key)
            if isinstance(v, list):
                out.append(v)
        content = meta.get("content")
        if isinstance(content, dict):
            for key in ("attributes", "traits"):
                v = content.get(key)
                if isinstance(v, list):
                    out.append(v)
    return out


def normalize_traits_from_nft_item(item: dict[str, Any]) -> dict[str, str]:
    """
    Универсально: attributes / traits / metadata / content.
    Ключи — в lower; значения — как в метаданных (trim), сравнение через casefold.
    """
    result: dict[str, str] = {}
    for alist in _iter_attribute_lists(item):
        for a in alist:
            if not isinstance(a, dict):
                continue
            key_raw = str(
                a.get("trait_type")
                or a.get("traitType")
                or a.get("type")
                or a.get("name")
                or ""
            ).strip()
            val = str(
                a.get("trait_value")
                or a.get("value")
                or a.get("traitValue")
                or ""
            ).strip()
            if not key_raw or not val:
                continue
            canon = canonical_trait_type_key(key_raw)
            result.setdefault(canon, val.strip())
    return result


def parse_market_nft_row(item: dict[str, Any]) -> MarketNftRow:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    name = str(meta.get("name") or "")
    addr = str(item.get("address") or "")
    sale = item.get("sale") if isinstance(item.get("sale"), dict) else None
    price_ton: Decimal | None = None
    for_sale = False
    sale_market: str | None = None
    if sale:
        pr = sale.get("price") if isinstance(sale.get("price"), dict) else None
        if pr is not None and pr.get("value") is not None:
            ton_ok = True
            cur = str(pr.get("currency") or pr.get("token_name") or "").strip().upper()
            if cur and cur not in ("TON", "NANOTON"):
                ton_ok = False
            tok = pr.get("token")
            if isinstance(tok, dict):
                sym = str(tok.get("symbol") or tok.get("name") or "").strip().upper()
                if sym and sym not in ("TON", "NANOTON"):
                    ton_ok = False
            if ton_ok:
                try:
                    dec = int(pr.get("decimals") if pr.get("decimals") is not None else 9)
                    val = int(pr["value"])
                    raw = Decimal(val) / (Decimal(10) ** dec)
                    fp = float(raw)
                    if fp > 0 and math.isfinite(fp):
                        price_ton = raw
                        for_sale = True
                except (TypeError, ValueError):
                    pass
        mk = sale.get("market") if isinstance(sale.get("market"), dict) else None
        if mk and mk.get("address"):
            sale_market = str(mk.get("address"))
    num = parse_number_from_nft_name(name)
    traits = normalize_traits_from_nft_item(item)
    model = traits.get("model")
    backdrop = traits.get("backdrop")
    symbol = traits.get("symbol")
    return MarketNftRow(
        name=name,
        number=num,
        address=addr,
        price_ton=price_ton,
        for_sale=for_sale,
        model=model,
        backdrop=backdrop,
        symbol=symbol,
        sale_market=sale_market,
        traits_normalized=dict(traits),
    )


def target_from_nft_payload(
    nft: dict[str, Any],
    *,
    ipfs_gateway_url: str = "https://ipfs.io/ipfs/",
) -> TargetNftInfo | None:
    coll = nft.get("collection") if isinstance(nft.get("collection"), dict) else {}
    c_addr = str(coll.get("address") or "").strip()
    if not c_addr:
        c_addr = str(nft.get("collection_address") or "").strip()
    c_meta = coll.get("metadata") if isinstance(coll.get("metadata"), dict) else {}
    c_name = str(coll.get("name") or c_meta.get("name") or "").strip()
    meta = nft.get("metadata") if isinstance(nft.get("metadata"), dict) else {}
    name = str(meta.get("name") or "")
    addr = str(nft.get("address") or "").strip()
    num = parse_number_from_nft_name(name)
    traits = normalize_traits_from_nft_item(nft)
    model = traits.get("model")
    backdrop = traits.get("backdrop")
    symbol = traits.get("symbol")
    if not c_addr:
        return None
    img, prev = extract_nft_media_urls(nft, ipfs_gateway_url=ipfs_gateway_url)
    pm = extract_nft_preview_media(nft, ipfs_gateway_url=ipfs_gateway_url)
    rich_url: str | None = None
    rich_kind: str | None = None
    if pm.kind in ("animation", "video") and pm.url:
        rich_url = pm.url
        rich_kind = pm.kind
    return TargetNftInfo(
        name=name or "NFT",
        number=num,
        address=addr,
        collection_name=c_name or "Collection",
        collection_address=c_addr,
        model=model,
        backdrop=backdrop,
        symbol=symbol,
        traits_normalized=dict(traits),
        image_url=img,
        preview_url=prev,
        rich_preview_url=rich_url,
        rich_preview_kind=rich_kind,
    )


def _float_price(row: MarketNftRow) -> float | None:
    if row.price_ton is None:
        return None
    return float(row.price_ton)


def effective_traits_normalized(target: TargetNftInfo) -> dict[str, str]:
    m = dict(target.traits_normalized)
    for attr in ("model", "backdrop", "symbol"):
        v = getattr(target, attr, None)
        if v and str(v).strip():
            m.setdefault(attr, str(v).strip())
    return m


def _row_trait_val(row: MarketNftRow, key: str) -> str | None:
    return row.traits_normalized.get(key) or getattr(row, key, None)


def norm_trait_val(v: str | None) -> str:
    return (v or "").strip().casefold()


def trait_vals_match(a: str | None, b: str | None) -> bool:
    return bool(a and b) and norm_trait_val(a) == norm_trait_val(b)


def match_score_row(target: TargetNftInfo, row: MarketNftRow) -> int:
    et = effective_traits_normalized(target)
    score = 0
    if trait_vals_match(et.get("model"), _row_trait_val(row, "model")):
        score += 50
    if trait_vals_match(et.get("symbol"), _row_trait_val(row, "symbol")):
        score += 25
    if trait_vals_match(et.get("backdrop"), _row_trait_val(row, "backdrop")):
        score += 15
    for k, tv in et.items():
        if k in ("model", "backdrop", "symbol"):
            continue
        if trait_vals_match(tv, _row_trait_val(row, k)):
            score += 5
    return score


def row_exact_main_traits(target: TargetNftInfo, row: MarketNftRow) -> bool:
    et = effective_traits_normalized(target)
    mains = [k for k in ("model", "backdrop", "symbol") if et.get(k)]
    if not mains:
        return False
    for k in mains:
        if not trait_vals_match(et.get(k), _row_trait_val(row, k)):
            return False
    return True


def filter_outliers(prices: list[float]) -> FilterResult:
    er = filter_outliers_enhanced([float(p) for p in prices if p is not None])
    merged = sorted(set(er.removed_low_outliers + er.removed_high_outliers))
    return FilterResult(
        er.used_prices,
        merged,
        er.method,
        er.reason,
        removed_low_outliers=list(er.removed_low_outliers),
        removed_high_outliers=list(er.removed_high_outliers),
    )


def _sale_rows_for_comps(target: TargetNftInfo, rows: list[MarketNftRow]) -> list[MarketNftRow]:
    out: list[MarketNftRow] = []
    for r in rows:
        if not r.for_sale:
            continue
        p = _float_price(r)
        if p is None or p <= 0:
            continue
        if target.address and r.address == target.address:
            continue
        out.append(r)
    return out


def _trait_subset(rows: list[MarketNftRow], attr: str, value: str | None) -> list[MarketNftRow]:
    if not value:
        return []
    out: list[MarketNftRow] = []
    for r in rows:
        if not r.for_sale or r.price_ton is None:
            continue
        rv = _row_trait_val(r, attr)
        if trait_vals_match(value, rv):
            out.append(r)
    return out


def _round_ton_price(x: float) -> float:
    return round(float(x), 2)


def _prices_from_rows(rs: list[MarketNftRow]) -> list[float]:
    return sorted(p for p in (_float_price(r) for r in rs) if p is not None and p > 0)


def _derive_list_prices(used: list[float]) -> tuple[float, float, float, float] | None:
    if not used:
        return None
    u = sorted(used)
    if len(u) >= 3:
        floor = min(u)
        med = float(statistics.median(u))
        quick = _round_ton_price(floor * 0.97)
        dont = _round_ton_price(floor * 0.93)
        normal = _round_ton_price(med)
        if len(u) >= 5:
            try:
                qs = statistics.quantiles(u, n=4, method="inclusive")
            except TypeError:
                qs = statistics.quantiles(u, n=4)
            high = _round_ton_price(float(qs[2]))
        else:
            high = _round_ton_price(max(u))
        return quick, normal, high, dont
    if len(u) == 2:
        quick = _round_ton_price(min(u) * 0.97)
        normal = _round_ton_price(float(statistics.mean(u)))
        high = _round_ton_price(max(u))
        dont = _round_ton_price(min(u) * 0.93)
        return quick, normal, high, dont
    quick = _round_ton_price(u[0] * 0.97)
    normal = _round_ton_price(u[0])
    high = _round_ton_price(u[0] * 1.1)
    dont = _round_ton_price(u[0] * 0.93)
    return quick, normal, high, dont


def build_trait_comps(trait_type: str, trait_value: str | None, rows: list[MarketNftRow], *, nearest_n: int = 5) -> TraitComps:
    attr = trait_type.lower()
    matched = _trait_subset(rows, attr, trait_value)
    prices = sorted(p for p in (_float_price(r) for r in matched) if p is not None and p > 0)
    floor_p = min(prices) if prices else None
    med_p = float(statistics.median(prices)) if prices else None
    nearest = sorted(matched, key=lambda r: (_float_price(r) or 1e12))[:nearest_n]
    return TraitComps(
        trait_type=trait_type,
        trait_value=trait_value,
        listings_count=len(matched),
        floor=floor_p,
        median=med_p,
        nearest=nearest,
    )


def build_close_comps(
    target: TargetNftInfo,
    rows: list[MarketNftRow],
    *,
    limit: int = 8,
    trait_weights: dict[str, float] | None = None,
    collection_registry: dict[str, Any] | None = None,
) -> list[MarketNftRow]:
    canon, _ = resolve_collection(target.collection_name, registry=collection_registry or {})
    wk = trait_weights or resolve_final_trait_weights(
        canon or target.collection_name,
        collection_registry or {},
        rows,
        exclude_address=(target.address or "").strip() or None,
        target=target,
    )
    scored: list[tuple[float, float, MarketNftRow]] = []
    for r in rows:
        if not r.for_sale or r.price_ton is None:
            continue
        if r.address == target.address:
            continue
        pt = _float_price(r)
        if pt is None:
            continue
        sc = similarity_weighted(target, r, wk)
        if sc <= 0:
            continue
        scored.append((sc, pt, r))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t[2] for t in scored[:limit]]


def build_sell_price_plan(
    target: TargetNftInfo,
    all_rows: list[MarketNftRow],
    *,
    loaded_count: int,
    listings_count: int,
    collection_floor: float | None,
    collection_median: float | None,
    same_model: TraitComps,
    same_backdrop: TraitComps,
    same_symbol: TraitComps,
    close_comps: list[MarketNftRow],
    settings: Settings,
    is_partial_scan: bool,
    collection_registry: dict[str, Any] | None = None,
    cache_age_minutes: float | None = None,
    target_sale_price_ton: float | None = None,
) -> SellPricePlan:
    """Оценка по активным листингам: веса трейтов, сигналы по трейтам, группы аналогов, робастные выбросы."""
    warns: list[str] = []
    _ = (same_model, same_backdrop, same_symbol, close_comps)

    if listings_count <= 0:
        return SellPricePlan(
            quick_sell_ton=None,
            normal_list_ton=None,
            high_list_ton=None,
            dont_list_below_ton=None,
            confidence="low",
            confidence_score=0,
            confidence_reason="Не хватает активных листингов с ценой для оценки.",
            warnings=["Недостаточно рынка."],
        )

    coll_vals = sorted(p for p in (_float_price(r) for r in all_rows if r.for_sale) if p is not None and p > 0)
    cf_raw = collection_floor if collection_floor is not None else (min(coll_vals) if coll_vals else None)
    cm_raw = collection_median if collection_median is not None else (
        float(statistics.median(coll_vals)) if coll_vals else None
    )
    cp75_raw = _collection_stats_p75(all_rows)
    cf, _cm, cp75, cwarn = _sanitize_collection_stats(cf_raw, cm_raw, cp75_raw)
    warns.extend(cwarn)

    candidates = _sale_rows_for_comps(target, all_rows)
    reg = collection_registry or {}
    canon, _ = resolve_collection(target.collection_name, registry=reg)
    name_key = canon or target.collection_name
    ex_addr = (target.address or "").strip() or None
    merged_wk = resolve_final_trait_weights(
        name_key,
        reg,
        all_rows,
        exclude_address=ex_addr,
        target=target,
    )
    pk = pick_primary_trait_keys(target, merged_wk)

    chosen_key, chosen_rows, efr, used, floor_anchor = select_best_listing_group(
        target, candidates, merged_wk, pk
    )
    raw_n_group = len([p for p in (_float_price(r) for r in chosen_rows) if p is not None and p > 0])

    used_fb = False
    fallback_note = ""
    if not used or floor_anchor <= 0:
        all_p = _prices_from_rows(candidates)
        if not all_p and cf is not None:
            all_p = [cf]
            if _cm is not None:
                all_p.append(_cm)
        if not all_p:
            return SellPricePlan(
                quick_sell_ton=None,
                normal_list_ton=None,
                high_list_ton=None,
                dont_list_below_ton=None,
                confidence="low",
                confidence_score=0,
                confidence_reason="Недостаточно цен среди активных листингов.",
                warnings=["Нужны листинги с ценой или уточните NFT address."],
            )
        efr = filter_outliers_enhanced(sorted(set(all_p)))
        used = efr.used_prices or all_p
        floor_anchor = floor_anchor_from_used(used)
        chosen_key = "collection_market"
        chosen_rows = list(candidates)
        used_fb = True
        fallback_note = (
            "Мало похожих листингов, оценка построена по общему рынку коллекции (листинги с ценой, floor/медиана)."
        )
        raw_n_group = len(all_p)

    priced0 = derive_price_band_from_used(sorted(used), floor_anchor=float(floor_anchor))
    if not priced0:
        return SellPricePlan(
            quick_sell_ton=None,
            normal_list_ton=None,
            high_list_ton=None,
            dont_list_below_ton=None,
            confidence="low",
            confidence_score=0,
            confidence_reason="Не удалось вычислить диапазон цен.",
            warnings=warns,
        )
    quick0, normal0, high0, dont0 = priced0

    list_med = listing_median_ton(all_rows, exclude_address=ex_addr)
    cm_traits = harmonize_collection_median(list_med, _cm)

    trait_signals = compute_trait_market_signals(
        target,
        all_rows,
        collection_floor=cf,
        collection_median=cm_traits,
        trait_weights=merged_wk,
        exclude_address=ex_addr,
    )
    trait_adj = compute_trait_adjusted_median(cm_traits, trait_signals, merged_wk)
    has_premium = any(
        s.price_signal == "premium" and s.support_level in ("medium", "high") for s in trait_signals
    )
    has_premium_strong = any(s.price_signal == "premium" and s.support_level == "high" for s in trait_signals)
    cm = float(_cm) if _cm is not None and _cm > 0 else None
    n_used = len(used)
    comp_med = float(statistics.median(used)) if used else None
    ta = trait_adj

    if n_used >= 5 and comp_med is not None:
        base_med = (0.93 * comp_med + 0.07 * ta) if ta is not None else comp_med
    elif n_used >= 3 and comp_med is not None:
        base_med = (0.68 * comp_med + 0.32 * ta) if ta is not None else comp_med
    else:
        coll_b = cm or comp_med or (float(cf) if cf is not None else 0.0)
        if ta is not None and comp_med is not None:
            base_med = 0.45 * comp_med + 0.55 * ta
        elif ta is not None and coll_b > 0:
            base_med = 0.45 * coll_b + 0.55 * ta
        elif comp_med is not None:
            base_med = comp_med
        else:
            base_med = float(ta) if ta is not None else float(normal0)

    if normal0 and base_med < float(normal0) * 0.9:
        base_med = float(normal0) * 0.9
    if normal0 and base_med > float(normal0) * 1.35 and n_used >= 5:
        base_med = min(base_med, float(normal0) * 1.12)

    if chosen_key == "exact_primary_match" and comp_med is not None and n_used >= 3:
        base_med = max(float(base_med), float(comp_med) * 0.985)

    eff_floor = float(floor_anchor)
    trait_floor_boost_ok = used_fb or chosen_key == "collection_market"
    if ta is not None and cm is not None and ta > cm * 1.07 and trait_floor_boost_ok:
        eff_floor = max(eff_floor, min(float(ta) * 0.83, (comp_med or float(ta)) * 0.97))
    if has_premium_strong and cm is not None and trait_floor_boost_ok:
        eff_floor = max(eff_floor, cm * 0.88)

    priced2 = derive_price_band_from_used(sorted(used), floor_anchor=float(eff_floor))
    if not priced2:
        quick, high, dont_below = quick0, high0, dont0
    else:
        quick, _, high, dont_below = priced2

    normal = round(float(base_med), 4)
    if quick > normal * 0.995:
        quick = round(normal * 0.945, 4)
    if dont_below > quick * 0.998:
        dont_below = round(quick * 0.965, 4)
    if high < max(normal, quick) * 1.02:
        high = round(max(normal, high0, quick) * 1.06, 4)
    quick, normal, high, dont_below = _sanitize_price_plan_monotonic(
        quick,
        normal,
        high,
        dont_below,
        p75_hint=cp75,
    )

    label_ru = label_for_group_key(chosen_key)
    max_items = max(100, int(settings.full_market_max_items))
    heavy_partial = is_partial_scan and loaded_count >= int(max_items * 0.95)

    score, conf_l, conf_det = confidence_score_from_signals(
        group_key=chosen_key,
        n_clean=n_used,
        is_partial_scan=is_partial_scan,
        loaded_count=loaded_count,
        max_items=max_items,
        cache_age_minutes=cache_age_minutes,
        collection_market_fallback=used_fb or chosen_key == "collection_market",
    )

    conf = conf_l
    if used_fb or n_used < 2:
        conf = "low"
    elif chosen_key == "collection_market" and not used_fb:
        conf = "low"
    elif n_used < 3:
        conf = "low"
    elif heavy_partial and conf == "high":
        conf = "medium"
    elif chosen_key == "weighted_close_comps" and conf == "high":
        conf = "medium"

    if chosen_key == "exact_primary_match" and n_used < 4 and any(
        s.support_level in ("medium", "high") for s in trait_signals
    ):
        if conf == "low" and score >= 34:
            conf = "medium"

    listing_note = "Рыночная оценка по активным листингам (не подтверждённые сделки)."
    cr = (fallback_note + " " if fallback_note else "") + conf_det + " " + listing_note

    comps_n = len([r for r in chosen_rows if _float_price(r)]) if chosen_rows else listings_count
    merged_out = sorted(set(efr.removed_low_outliers + efr.removed_high_outliers))

    if is_partial_scan:
        warns.append("Скан коллекции прерван или неполный — учитывайте с осторожностью.")

    if normal is not None and cf is not None and normal < cf * 0.95 and (used_fb or n_used < 5):
        warns.append("Нормальная цена ниже floor коллекции — перепроверьте вручную.")

    cohort_expl = human_cohort_explanation_ru(
        group_key=chosen_key,
        n_used=n_used,
        has_trait_adjustment=bool(trait_adj),
    )
    impact_block = human_trait_impact_block(trait_signals)
    range_hint = price_range_hint_ru(used) if n_used >= 3 else ""
    sale_ton = target_sale_price_ton if target_sale_price_ton and target_sale_price_ton > 0 else None
    listed = sale_ton is not None
    verdict = listing_verdict_ru(
        for_sale=listed,
        sale_price_ton=sale_ton,
        quick=quick,
        normal=normal,
        high=high,
    )
    mpos = market_position_verdict_ru(
        normal=normal,
        collection_median=cm,
        trait_adjusted=trait_adj,
        n_comps_used=n_used,
    )
    advice = final_listing_advice_ru(
        dont_below=dont_below,
        normal=normal,
        has_premium_trait=has_premium,
    )

    sum_parts: list[str] = []
    sum_parts.append("частичный скан" if is_partial_scan else "полный скан")
    if n_used >= 10:
        sum_parts.append("много цен в выбранной выборке")
    elif n_used >= 4:
        sum_parts.append("достаточно цен для ориентира")
    else:
        sum_parts.append("мало прямых аналогов — сильнее опора на трейты и общий рынок")
    if cache_age_minutes is not None and cache_age_minutes > 45:
        sum_parts.append("данные из кэша")
    conf_summary = "; ".join(sum_parts) + ". Оценка по активным листингам TonAPI."

    return SellPricePlan(
        quick_sell_ton=quick,
        normal_list_ton=normal,
        high_list_ton=high,
        dont_list_below_ton=dont_below,
        confidence=conf,
        confidence_reason=cr.strip(),
        warnings=warns,
        pricing_group_key=chosen_key,
        pricing_group_label_ru=label_ru,
        comps_used_count=comps_n,
        used_prices_ton=list(sorted(used)),
        outlier_prices_ton=merged_out,
        outlier_filter_note=efr.reason,
        used_collection_market_fallback=used_fb,
        confidence_score=score,
        removed_low_outliers_ton=list(efr.removed_low_outliers),
        removed_high_outliers_ton=list(efr.removed_high_outliers),
        floor_anchor_ton=float(eff_floor),
        primary_trait_keys=list(pk),
        raw_prices_in_group_count=raw_n_group,
        trait_signals=trait_signals,
        trait_adjusted_median_ton=trait_adj,
        listing_verdict_ru=verdict,
        market_position_ru=mpos,
        cohort_explanation_ru=cohort_expl,
        trait_impact_block_ru=impact_block,
        price_range_hint_ru=range_hint,
        listing_advice_ru=advice,
        target_listing_price_ton=sale_ton,
        has_premium_traits=has_premium,
        confidence_summary_ru=conf_summary,
    )


def next_lower_page_limit(current: int, min_limit: int, ladder: tuple[int, ...]) -> int | None:
    """Следующий меньший лимит из лестницы (или min_limit), либо None если уменьшать некуда."""
    for step in sorted(ladder, reverse=True):
        if step < current and step >= min_limit:
            return step
    if current > min_limit:
        return min_limit
    return None


def _body_suggests_limit_rejected(body: str) -> bool:
    bl = (body or "").lower()
    needles = (
        "limit too large",
        "bad request",
        "validation",
        "invalid limit",
        "page size",
        "query is too big",
        "payload too large",
    )
    return any(n in bl for n in needles)


def dedupe_scan_rows(rows: list[MarketNftRow]) -> list[MarketNftRow]:
    """Один адрес — одна строка; приоритет листингу с ценой."""
    by_addr: dict[str, MarketNftRow] = {}
    no_addr: list[MarketNftRow] = []
    for r in rows:
        a = (r.address or "").strip()
        if not a:
            no_addr.append(r)
            continue
        prev = by_addr.get(a)
        if prev is None:
            by_addr[a] = r
            continue
        if r.for_sale and not prev.for_sale:
            by_addr[a] = r
        elif (not r.for_sale) and prev.for_sale:
            continue
        elif r.for_sale and prev.for_sale:
            rp, pp = _float_price(r), _float_price(prev)
            if rp is not None and pp is None:
                by_addr[a] = r
            elif rp is not None and pp is not None:
                by_addr[a] = r
        else:
            by_addr[a] = r
    return no_addr + list(by_addr.values())


def _collection_stats(rows: list[MarketNftRow]) -> tuple[float | None, float | None, int]:
    prices = sorted(p for p in (_float_price(r) for r in rows if r.for_sale) if p is not None and p > 0)
    if not prices:
        return None, None, 0
    return min(prices), float(statistics.median(prices)), len(prices)


def _collection_stats_p75(rows: list[MarketNftRow]) -> float | None:
    prices = sorted(p for p in (_float_price(r) for r in rows if r.for_sale) if p is not None and p > 0)
    if not prices:
        return None
    if len(prices) < 2:
        return float(prices[0])
    try:
        qs = statistics.quantiles(prices, n=4, method="inclusive")
    except TypeError:
        qs = statistics.quantiles(prices, n=4)
    if len(qs) < 3:
        return float(prices[-1])
    return float(qs[2])


def _sanitize_collection_stats(
    floor: float | None,
    median: float | None,
    p75: float | None,
) -> tuple[float | None, float | None, float | None, list[str]]:
    warns: list[str] = []
    f = float(floor) if floor is not None and floor > 0 else None
    m = float(median) if median is not None and median > 0 else None
    p = float(p75) if p75 is not None and p75 > 0 else None
    if f is not None and m is not None and m < f:
        warns.append("Медиана коллекции ниже floor — данные пересчитываются.")
        m = None
    if m is not None and p is not None and m > p:
        warns.append("Медиана выше p75 — данные пересчитываются.")
        m = None
    if f is not None and p is not None and p < f:
        warns.append("p75 ниже floor — данные пересчитываются.")
        p = None
    return f, m, p, warns


def _sanitize_price_plan_monotonic(
    quick: float | None,
    normal: float | None,
    high: float | None,
    dont_below: float | None,
    *,
    p75_hint: float | None = None,
) -> tuple[float | None, float | None, float | None, float | None]:
    q = float(quick) if quick is not None and quick > 0 else None
    n = float(normal) if normal is not None and normal > 0 else None
    h = float(high) if high is not None and high > 0 else None
    d = float(dont_below) if dont_below is not None and dont_below > 0 else None
    p75 = float(p75_hint) if p75_hint is not None and p75_hint > 0 else None
    if q is not None and n is not None and q > n:
        q = round(n * 0.92, 4)
    if h is not None and n is not None and h < n:
        cands = [n * 1.10]
        if p75 is not None:
            cands.append(p75)
        h = round(max(cands), 4)
    if d is not None and q is not None and d > q:
        d = round(q * 0.95, 4)
    if q is not None and n is not None:
        q = min(q, n)
    if n is not None and h is not None:
        h = max(h, n)
    if d is not None and q is not None:
        d = min(d, q)
    return q, n, h, d


def _coerce_positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if not math.isfinite(value) or value <= 0:
            return None
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or not s.isdigit():
            return None
        try:
            n = int(s)
            return n if n > 0 else None
        except ValueError:
            return None
    return None


def extract_collection_total_approx(response: dict[str, Any] | None) -> int | None:
    """
    Достаёт из ответа TonAPI GET .../collections/{addr}/items оценку размера коллекции, если поле есть.
    Только проверенные варианты ключей; при смене API — безопасно вернёт None.
    """
    if not isinstance(response, dict):
        return None

    for key in ("total", "total_count", "approximate_nfts_count", "nft_count", "items_count"):
        n = _coerce_positive_int(response.get(key))
        if n is not None:
            return n

    meta = response.get("metadata")
    if isinstance(meta, dict):
        for key in ("total", "total_count", "approximate_nfts_count"):
            n = _coerce_positive_int(meta.get(key))
            if n is not None:
                return n

    coll = response.get("collection")
    if isinstance(coll, dict):
        for key in ("next_item_index", "approximate_items_count", "items_count"):
            n = _coerce_positive_int(coll.get(key))
            if n is not None:
                return n

    items = response.get("nft_items") or response.get("items")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            c = first.get("collection")
            if isinstance(c, dict):
                n = _coerce_positive_int(c.get("next_item_index"))
                if n is not None:
                    return n

    return None


async def scan_collection_listings(
    client: TonAPICollectionClient,
    settings: Settings,
    collection_address: str,
    on_progress: Callable[[int, int, str, int, int | None, str | None], Awaitable[None]] | None = None,
) -> tuple[list[MarketNftRow], int, bool, int | None]:
    ladder = parse_page_limit_fallbacks(settings.full_market_page_limit_fallbacks)
    rows: list[MarketNftRow] = []
    collection_total_approx: int | None = None
    offset = 0
    min_lim = max(1, int(settings.full_market_min_page_limit))
    working_limit = initial_full_scan_page_limit(settings)
    base_max = max(100, int(settings.full_market_max_items))
    fs_cap = int(settings.full_market_full_scan_max_items)
    max_all = min(base_max, max(100, fs_cap)) if fs_cap > 0 else base_max
    partial = False
    loaded = 0
    sleep_s = max(0.0, settings.full_market_request_sleep_ms / 1000.0)
    prog_every = max(50, settings.full_market_progress_every_items)
    last_prog = 0
    rl_streak = 0
    tonapi_429_count = 0
    tonapi_404_count = 0
    rl_reduce_after = max(1, int(settings.full_market_429_streak_before_reduce_limit))
    backoff_base = float(settings.full_market_rate_limit_sleep_seconds)
    page_limit_note: str | None = None
    under_pair: tuple[int, int] | None = None
    stuck_no_progress = 0
    max_stuck = 8

    async def _emit_ratelimit() -> None:
        if on_progress:
            ln = sum(1 for r in rows if r.for_sale)
            await on_progress(loaded, ln, "ratelimit", working_limit, collection_total_approx, page_limit_note)

    while loaded < max_all:
        req = working_limit
        items, status, body, page_json = await client.fetch_collection_items_page_raw(
            collection_address,
            limit=working_limit,
            offset=offset,
        )

        if status == 200:
            rl_streak = 0
            stuck_no_progress = 0
            if collection_total_approx is None and page_json is not None:
                collection_total_approx = extract_collection_total_approx(page_json)
            chunk = items
            if not chunk:
                break
            n = len(chunk)
            for item in chunk:
                rows.append(parse_market_nft_row(item))
            loaded += n
            offset += n
            listings_n = sum(1 for r in rows if r.for_sale)
            if on_progress and loaded - last_prog >= prog_every:
                last_prog = loaded
                await on_progress(loaded, listings_n, "scan", working_limit, collection_total_approx, page_limit_note)

            if loaded >= max_all:
                if not (collection_total_approx and loaded >= collection_total_approx):
                    partial = True
                break

            if collection_total_approx is not None and collection_total_approx > 0 and loaded >= collection_total_approx:
                break

            if n >= req:
                under_pair = None
                await asyncio.sleep(sleep_s)
                continue

            if collection_total_approx is not None and collection_total_approx > 0 and loaded < collection_total_approx:
                under_pair = None
                await asyncio.sleep(sleep_s)
                continue

            if collection_total_approx is not None and collection_total_approx > 0 and loaded >= collection_total_approx:
                break

            if under_pair == (req, n) and n < req:
                new_lim = max(min_lim, n)
                if new_lim < req:
                    page_limit_note = (
                        f"Запрашивали лимит {req:,}, TonAPI стабильно отдаёт по {n:,} NFT — "
                        f"продолжаю с лимитом {new_lim:,}."
                    ).replace(",", " ")
                working_limit = new_lim
                under_pair = None
                await asyncio.sleep(sleep_s)
                continue
            under_pair = (req, n)
            await asyncio.sleep(sleep_s)
            continue

        if status == 429:
            tonapi_429_count += 1
            rl_streak += 1
            stuck_no_progress = 0
            await _emit_ratelimit()
            await asyncio.sleep(backoff_base * (1 + (rl_streak - 1) * 0.25))
            if rl_streak >= rl_reduce_after:
                prev = working_limit
                nl = next_lower_page_limit(working_limit, min_lim, ladder)
                if nl is None:
                    partial = True
                    logger.warning("TonAPI 429: cannot reduce page limit further")
                    break
                working_limit = nl
                if nl < prev:
                    page_limit_note = (
                        f"Несколько ответов 429 при лимите {prev:,} — снижаю размер страницы до {nl:,}."
                    ).replace(",", " ")
                rl_streak = 0
            continue

        if status in (400, 413, 422) or _body_suggests_limit_rejected(body):
            rl_streak = 0
            stuck_no_progress = 0
            prev = working_limit
            nl = next_lower_page_limit(working_limit, min_lim, ladder)
            if nl is None:
                partial = True
                logger.warning("TonAPI rejected limit (status=%s), cannot reduce further", status)
                break
            working_limit = nl
            page_limit_note = (
                f"TonAPI не принял лимит {prev:,} — перехожу на {nl:,} (тот же offset {offset:,})."
            ).replace(",", " ")
            continue
        if status == 404:
            tonapi_404_count += 1

        stuck_no_progress += 1
        logger.warning("TonAPI collection page stopped: status=%s snippet=%s", status, (body or "")[:240])
        if stuck_no_progress >= max_stuck:
            partial = True
            break
        await asyncio.sleep(min(2.0, backoff_base))
        continue

    rows = dedupe_scan_rows(rows)
    logger.info(
        "full_scan done collection=%s loaded=%s listings=%s page_limit=%s tonapi_429=%s tonapi_404=%s",
        (collection_address or "")[:16],
        loaded,
        sum(1 for r in rows if r.for_sale),
        working_limit,
        tonapi_429_count,
        tonapi_404_count,
    )
    if collection_total_approx is not None and collection_total_approx > 0 and loaded >= collection_total_approx:
        partial = False
    elif collection_total_approx is not None and collection_total_approx > 0 and loaded < collection_total_approx:
        partial = True
    return rows, loaded, partial, collection_total_approx


async def get_cached_or_scan_collection(
    client: TonAPICollectionClient,
    settings: Settings,
    collection_address: str,
    on_progress: Callable[[int, int, str, int, int | None, str | None], Awaitable[None]] | None = None,
) -> tuple[list[MarketNftRow], int, bool, float | None, int | None]:
    """Returns rows, loaded_count, partial, cache_age_minutes (if cache hit), collection_total_approx."""
    ttl = max(60, settings.full_market_cache_ttl_seconds)
    now = time.time()
    async with _CACHE_LOCK:
        hit = _COLLECTION_SCAN_CACHE.get(collection_address)
        if hit and (now - hit[0]) <= ttl:
            age_m = (now - hit[0]) / 60.0
            total_apx = hit[4] if len(hit) > 4 else None
            return hit[1], hit[3], hit[2], age_m, total_apx

    rows, loaded, partial, coll_total = await scan_collection_listings(
        client, settings, collection_address, on_progress=on_progress
    )
    async with _CACHE_LOCK:
        _COLLECTION_SCAN_CACHE[collection_address] = (now, rows, partial, loaded, coll_total)
    return rows, loaded, partial, None, coll_total


def find_target_row(rows: list[MarketNftRow], target: TargetNftInfo) -> MarketNftRow | None:
    if target.address:
        for r in rows:
            if r.address == target.address:
                return r
    if target.number is not None:
        for r in rows:
            if r.number == target.number:
                return r
    return None


def enrich_target_from_row(target: TargetNftInfo, row: MarketNftRow) -> TargetNftInfo:
    merged_traits = {**target.traits_normalized, **row.traits_normalized}
    return TargetNftInfo(
        name=row.name or target.name,
        number=row.number or target.number,
        address=row.address or target.address,
        collection_name=target.collection_name,
        collection_address=target.collection_address,
        model=row.model or target.model,
        backdrop=row.backdrop or target.backdrop,
        symbol=row.symbol or target.symbol,
        traits_normalized=merged_traits,
        image_url=target.image_url,
        preview_url=target.preview_url,
        rich_preview_url=target.rich_preview_url,
        rich_preview_kind=target.rich_preview_kind,
    )


def build_full_report(
    target: TargetNftInfo,
    rows: list[MarketNftRow],
    *,
    loaded_count: int,
    is_partial_scan: bool,
    settings: Settings,
    cache_age_minutes: float | None,
    collection_total_approx: int | None = None,
) -> FullMarketNftReport:
    registry = load_collection_registry(settings.collection_registry_path)
    rows = dedupe_scan_rows(list(rows))
    coll_floor_raw, coll_med_raw, list_n = _collection_stats(rows)
    coll_p75_raw = _collection_stats_p75(rows)
    coll_floor, coll_med, _coll_p75, stat_warnings = _sanitize_collection_stats(
        coll_floor_raw,
        coll_med_raw,
        coll_p75_raw,
    )
    same_m = build_trait_comps("model", target.model, rows)
    same_b = build_trait_comps("backdrop", target.backdrop, rows)
    same_s = build_trait_comps("symbol", target.symbol, rows)
    canon, _ = resolve_collection(target.collection_name, registry=registry)
    wk = resolve_final_trait_weights(
        canon or target.collection_name,
        registry,
        rows,
        exclude_address=(target.address or "").strip() or None,
        target=target,
    )
    close = build_close_comps(target, rows, trait_weights=wk, collection_registry=registry)
    trow = find_target_row(rows, target)
    target_sale: float | None = None
    if trow and trow.for_sale and trow.price_ton is not None:
        fp = _float_price(trow)
        if fp is not None and fp > 0:
            target_sale = fp
    plan = build_sell_price_plan(
        target,
        rows,
        loaded_count=loaded_count,
        listings_count=list_n,
        collection_floor=coll_floor,
        collection_median=coll_med,
        same_model=same_m,
        same_backdrop=same_b,
        same_symbol=same_s,
        close_comps=close,
        settings=settings,
        is_partial_scan=is_partial_scan,
        collection_registry=registry,
        cache_age_minutes=cache_age_minutes,
        target_sale_price_ton=target_sale,
    )
    src = "TonAPI, реальные листинги"
    if cache_age_minutes is not None:
        src = f"TonAPI, кэш рынка обновлён ~{cache_age_minutes:.1f} мин назад"
    warns = list(plan.warnings) + list(stat_warnings)
    ak = getattr(target, "address_kind", None)
    scan_tgt = "Getgems" if ak == "getgems_gift_ref" else None
    scan_mkt = "TonAPI" if ak == "getgems_gift_ref" else None
    return FullMarketNftReport(
        target=target,
        loaded_count=loaded_count,
        listings_count=list_n,
        collection_floor=coll_floor,
        collection_median=coll_med,
        same_model=same_m,
        same_backdrop=same_b,
        same_symbol=same_s,
        close_comps=close,
        sell_plan=plan,
        is_partial_scan=is_partial_scan,
        source_label=src,
        warnings=warns,
        cache_age_minutes=cache_age_minutes,
        collection_total_approx=collection_total_approx,
        scan_target_source=scan_tgt,
        scan_market_source=scan_mkt,
        scan_target_address_kind=ak if ak == "getgems_gift_ref" else None,
    )


def format_trait_nearest(tc: TraitComps) -> str:
    ps = []
    for r in tc.nearest[:3]:
        p = _float_price(r)
        if p is not None:
            ps.append(f"{p:g}")
    return " · ".join(ps) if ps else "—"


_SELL_CONF_RU = {"low": "низкая", "medium": "средняя", "high": "высокая"}


def _sell_confidence_ru(value: str) -> str:
    return _SELL_CONF_RU.get((value or "").lower(), value or "—")


def _fmt_paragraph_block(text: str, *, indent: str = "   ") -> list[str]:
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line:
            out.append(f"{indent}{line}")
    return out if out else [f"{indent}—"]


def _format_ton_plain(x: float) -> str:
    fx = float(x)
    if fx >= 1000:
        s = f"{fx:.1f}"
    elif fx >= 1:
        s = f"{fx:.2f}"
    else:
        s = f"{fx:.4f}"
    s = s.rstrip("0").rstrip(".")
    return s if s else str(fx)


def _trait_comp_lines(title: str, trait_value: str, tc: TraitComps) -> list[str]:
    name = trait_value or "не указан"
    if tc.floor is None:
        return [
            "",
            f"   {title} — {name}",
            f"   Листингов с ценой — {tc.listings_count}",
            "   Нет совпадений среди активных листингов.",
        ]
    near = format_trait_nearest(tc)
    near_line = (
        "   Ближайшие цены — нет в выборке"
        if near == "—"
        else f"   Ближайшие цены — {near} TON"
    )
    return [
        "",
        f"   {title} — {name}",
        f"   Листингов с ценой — {tc.listings_count}",
        f"   Floor по трейту — {_format_ton_plain(tc.floor)} TON",
        near_line,
    ]


def format_full_market_nft_report(report: FullMarketNftReport) -> str:
    t = report.target
    sp = report.sell_plan
    lines: list[str] = [
        "🔎 Проверка NFT",
        "",
    ]
    if report.scan_target_source and report.scan_market_source:
        lines.extend(
            [
                f"Источник: {report.scan_target_source} / {report.scan_market_source}",
                "",
            ]
        )
    lines.extend(
        [
        f"🎁 {t.name}",
        "",
        f"Коллекция: {t.collection_name}",
        "",
    ]
    )
    if sp.target_listing_price_ton is not None and sp.target_listing_price_ton > 0:
        lines.extend(
            [
                "📌 Текущий листинг",
                f"NFT уже выставлена на продажу за {_format_ton_plain(sp.target_listing_price_ton)} TON.",
            ]
        )
        if sp.normal_list_ton is not None and sp.normal_list_ton > 0:
            ratio = float(sp.target_listing_price_ton) / float(sp.normal_list_ton)
            if ratio >= 3:
                lines.append("Это сильно выше рынка похожих NFT.")
            elif ratio >= 1.5:
                lines.append("Это выше рынка похожих NFT.")
            elif ratio >= 0.85:
                lines.append("Цена близка к рынку похожих NFT.")
            else:
                lines.append("Цена ниже похожих NFT — возможно слишком дёшево.")
        lines.append("")
    lines.extend(
        [
        "🧬 Трейты",
        f"Model: {t.model or 'не указан'}",
        f"Backdrop: {t.backdrop or 'не указан'}",
        f"Symbol: {t.symbol or 'не указан'}",
        "",
        "📊 Рынок коллекции",
        ]
    )
    tot = report.collection_total_approx
    if tot is not None and tot > 0:
        lines.append(f"Просканировано: {report.loaded_count:,} из ~{tot:,} NFT".replace(",", " "))
    else:
        lines.append(f"Просканировано: {report.loaded_count:,} NFT".replace(",", " "))
    lines.append(f"Активных объявлений: {report.listings_count}")
    if report.collection_floor is not None:
        lines.append(f"Самая низкая цена в коллекции: {_format_ton_plain(report.collection_floor)} TON")
    else:
        lines.append("Самая низкая цена в коллекции: нет данных")
    median_valid = (
        report.collection_median is not None
        and (report.collection_floor is None or report.collection_median >= report.collection_floor)
    )
    if median_valid:
        lines.append(f"Обычная середина рынка: {_format_ton_plain(report.collection_median)} TON")
    else:
        lines.append("Обычная середина рынка: данные пересчитываются")
    lines.append(f"Скан: {'частичный' if report.is_partial_scan else 'полный'}")
    if report.is_partial_scan:
        if tot is not None and tot > 0 and report.loaded_count < tot:
            lines.append(
                "   Скан частичный: по TonAPI в коллекции больше NFT, чем попало в выборку — оценка менее уверенная."
            )
        else:
            lines.append("   Скан частичный — ориентируйтесь на диапазон с осторожностью.")
    if report.cache_age_minutes is not None:
        if report.cache_age_minutes < 15:
            lines.append("   Данные кэша TonAPI — свежие.")
        else:
            lines.append(f"   Данные кэша TonAPI — примерно {report.cache_age_minutes:.0f} мин назад.")
    lines.append(f"Источник: {report.source_label or 'TonAPI'}")
    lines.append("")
    lines.append("🧬 Влияние трейтов")
    if sp.trait_impact_block_ru:
        lines.extend(_fmt_paragraph_block(sp.trait_impact_block_ru, indent=""))
    else:
        lines.append("Недостаточно данных по отдельным трейтам.")
    lines.append("")
    lines.append("🧾 Что сравнивал")
    lines.extend(_fmt_paragraph_block(sp.cohort_explanation_ru or "Сопоставил с рынком коллекции и трейтами.", indent=""))
    if sp.price_range_hint_ru:
        lines.append("")
        lines.extend(_fmt_paragraph_block(sp.price_range_hint_ru, indent=""))
    lines.append("")
    lines.append("💰 Как выставить")
    if sp.quick_sell_ton is not None:
        lines.append(f"Быстро продать: около {_format_ton_plain(sp.quick_sell_ton)} TON")
        if sp.normal_list_ton is not None:
            lines.append(f"Нормально выставить: около {_format_ton_plain(sp.normal_list_ton)} TON")
        else:
            lines.append("Нормально выставить: недостаточно данных")
        if sp.high_list_ton is not None:
            lines.append(f"Дорого / ждать: около {_format_ton_plain(sp.high_list_ton)} TON")
        else:
            lines.append("Дорого / ждать: недостаточно данных")
        if sp.dont_list_below_ton is not None:
            lines.append(f"Ниже не стоит: около {_format_ton_plain(sp.dont_list_below_ton)} TON")
        else:
            lines.append("Ниже не стоит: недостаточно данных")
    else:
        lines.append("Недостаточно листингов — диапазон цен не считаю.")
    lines.append("")
    lines.append("📌 Вывод")
    lines.extend(_fmt_paragraph_block(sp.listing_verdict_ru or "Смотрите ориентиры по цене выше.", indent=""))
    if sp.market_position_ru:
        lines.append("")
        lines.extend(_fmt_paragraph_block(sp.market_position_ru, indent=""))
    if sp.listing_advice_ru:
        lines.append("")
        lines.extend(_fmt_paragraph_block(sp.listing_advice_ru, indent=""))
    lines.append("")
    conf_word = _sell_confidence_ru(sp.confidence).capitalize()
    lines.append(f"⚠️ Уверенность: {conf_word}")
    if sp.confidence_summary_ru:
        conf_reason = " ".join(x.strip() for x in str(sp.confidence_summary_ru).splitlines() if x.strip())
        lines.append(f"Причина: {conf_reason}")
    lines.append("")
    lines.append("Важно: это оценка по активным листингам TonAPI, а не гарантия продажи.")
    notes: list[str] = list(report.warnings[:5])
    if report.is_partial_scan:
        notes.append("Скан мог быть неполным (лимит страниц или сеть).")
    if notes:
        lines.append("")
        lines.append("💡 Заметки")
        for w in notes:
            lines.append(f"   • {w}")
    return "\n".join(lines)


def format_full_market_nft_report_compact_plain(report: FullMarketNftReport) -> str:
    """Короткий текстовый отчёт для одного сообщения Telegram (без HTML)."""
    t = report.target
    sp = report.sell_plan
    scan_word = "частичный" if report.is_partial_scan else "полный"
    lines: list[str] = [
        "🔎 Проверка NFT (кратко)",
        "",
        f"🎁 {t.name}",
        f"Коллекция: {t.collection_name}",
        "",
        f"📊 Рынок: {report.listings_count} объявлений, скан {scan_word}.",
    ]
    if sp.quick_sell_ton is not None:
        lines.extend(
            [
                "",
                "💰 Ориентиры (TON)",
                f"• Быстро: ~{_format_ton_plain(sp.quick_sell_ton)}",
                f"• Нормально: ~{_format_ton_plain(sp.normal_list_ton)}",
                f"• Дорого: ~{_format_ton_plain(sp.high_list_ton)}",
                f"• Ниже не стоит: ~{_format_ton_plain(sp.dont_list_below_ton)}",
            ]
        )
    else:
        lines.extend(["", "💰 Недостаточно листингов для диапазона цен."])
    conf_word = _sell_confidence_ru(sp.confidence).capitalize()
    lines.extend(
        [
            "",
            f"⚠️ Уверенность: {conf_word}",
            "",
            "Важно: оценка по активным листингам TonAPI, не гарантия продажи.",
        ]
    )
    if report.is_partial_scan:
        lines.append("Скан мог быть неполным — ориентируйтесь осторожно.")
    return "\n".join(lines)


def format_full_market_nft_report_for_telegram_edit(report: FullMarketNftReport, *, max_len: int = 4090) -> str:
    """Полный отчёт или компактный, чтобы влезть в одно edit_message_text."""
    full = format_full_market_nft_report(report)
    if len(full) <= max_len:
        return full
    compact = format_full_market_nft_report_compact_plain(report)
    if len(compact) <= max_len:
        return compact
    return compact[: max(1, max_len - 1)] + "…"


NFT_CHECK_PHOTO_CAPTION_SAFE = 880


def _fmt_ton_caption(x: float | None) -> str:
    if x is None:
        return "—"
    return _format_ton_plain(float(x))


def format_nft_check_compact_caption_html(report: FullMarketNftReport) -> str:
    """Краткий HTML-caption для send_photo (имена и трейты экранируются)."""
    t = report.target
    sp = report.sell_plan
    scan_word = "частичный" if report.is_partial_scan else "полный"
    conf_l = _sell_confidence_ru(sp.confidence)
    nm = html.escape((t.name or "NFT").strip() or "NFT", quote=False)
    coll = html.escape((t.collection_name or "").strip() or "—", quote=False)
    m = html.escape((t.model or "не указан").strip(), quote=False)
    b = html.escape((t.backdrop or "не указан").strip(), quote=False)
    s = html.escape((t.symbol or "не указан").strip(), quote=False)
    lines: list[str] = [
        "<b>🔎 Проверка NFT</b>",
        "",
        f"🎁 <b>{nm}</b>",
        f"Коллекция: {coll}",
        "",
        "<b>🧬 Трейты</b>",
        f"• Model: {m}",
        f"• Backdrop: {b}",
        f"• Symbol: {s}",
        "",
        "<b>💰 Рекомендация</b>",
    ]
    if sp.quick_sell_ton is not None:
        lines.append(f"• Быстро: ~{_fmt_ton_caption(sp.quick_sell_ton)} TON")
        lines.append(f"• Нормально: ~{_fmt_ton_caption(sp.normal_list_ton)} TON")
        lines.append(f"• Дорого: ~{_fmt_ton_caption(sp.high_list_ton)} TON")
        lines.append(f"• Ниже не стоит: ~{_fmt_ton_caption(sp.dont_list_below_ton)} TON")
    else:
        lines.append("• Недостаточно листингов для диапазона цен.")
    lines.extend(
        [
            "",
            "<b>📊 Рынок</b>",
            f"• Листингов: {report.listings_count}",
            f"• Скан: {scan_word}",
            "• Источник: TonAPI",
            "",
            f"⚠️ Уверенность: {html.escape(conf_l, quote=False)} ({sp.confidence_score}/100)",
        ]
    )
    return "\n".join(lines)


def format_nft_check_minimal_caption_html(report: FullMarketNftReport) -> str:
    """Укороченный caption, если полный не влезает в лимит Telegram."""
    t = report.target
    sp = report.sell_plan
    nm = html.escape((t.name or "NFT").strip() or "NFT", quote=False)
    coll = html.escape((t.collection_name or "").strip() or "—", quote=False)
    conf_l = _sell_confidence_ru(sp.confidence)
    scan_word = "частичный" if report.is_partial_scan else "полный"
    if sp.quick_sell_ton is not None:
        band = (
            f"~{_fmt_ton_caption(sp.quick_sell_ton)} / ~{_fmt_ton_caption(sp.normal_list_ton)} / "
            f"~{_fmt_ton_caption(sp.high_list_ton)} TON"
        )
    else:
        band = "диапазон цен недоступен"
    return (
        f"<b>🔎 Проверка NFT</b>\n🎁 <b>{nm}</b>\n{coll}\n\n"
        f"<b>💰</b> {band}\n"
        f"📊 листингов {report.listings_count}, скан {scan_word}, TonAPI\n"
        f"⚠️ {html.escape(conf_l, quote=False)} ({sp.confidence_score}/100)"
    )


def _format_progress_message_simple_user(
    collection_name_raw: str,
    loaded: int,
    listings: int,
    *,
    collection_total_approx: int | None,
    lang: str,
) -> str:
    """Короткий user-facing текст прогресса: без page limit, без TonAPI, без «лимитов API»."""
    from app.i18n import normalize_lang, t

    lg = normalize_lang(lang)

    def _n(x: int) -> str:
        return f"{x:,}".replace(",", " ")

    raw = (collection_name_raw or "").strip()
    parts = [t("progress.simple_title_plain", lg)]
    if raw:
        parts.append(t("progress.simple_collection_named", lg, coll=raw))
    parts.append(t("progress.simple_intro", lg))
    if collection_total_approx and collection_total_approx > 0:
        parts.append(
            t(
                "progress.simple_checked_approx",
                lg,
                loaded=_n(loaded),
                total=_n(collection_total_approx),
            )
        )
    else:
        parts.append(t("progress.simple_checked", lg, loaded=_n(loaded)))
    parts.append(t("progress.simple_listings", lg, listings=_n(listings)))
    parts.append(t("progress.simple_slow", lg))
    parts.append(t("progress.simple_wallet", lg))
    return "".join(parts)


def format_progress_message(
    collection_name: str,
    loaded: int,
    listings: int,
    *,
    phase: str,
    page_limit: int | None = None,
    collection_total_approx: int | None = None,
    page_limit_note: str | None = None,
    lang: str | None = "en",
    simple_progress: bool = True,
) -> str:
    """Тексты прогресса full scan. При ``simple_progress=True`` — простой текст без page limit и TonAPI."""
    from app.i18n import normalize_lang, t

    lg = normalize_lang(lang)

    def _n(x: int) -> str:
        return f"{x:,}".replace(",", " ")

    coll_raw = (collection_name or "").strip()
    coll = coll_raw or t("progress.collection_fallback", lg)

    if phase in ("start", "prepare"):
        return _format_progress_message_simple_user(
            collection_name,
            loaded,
            listings,
            collection_total_approx=None,
            lang=lg,
        )

    if phase == "ratelimit":
        if simple_progress:
            if coll_raw:
                return t("progress.ratelimit_user", lg, coll=coll_raw, loaded=_n(loaded), listings=_n(listings))
            return t("progress.ratelimit_user_plain", lg, loaded=_n(loaded), listings=_n(listings))
        parts = [t("progress.ratelimit_title", lg), t("progress.ratelimit_body", lg)]
        parts.append(t("progress.ratelimit_stats", lg, coll=coll, loaded=_n(loaded), listings=_n(listings)))
        if page_limit and page_limit > 0:
            parts.append(t("progress.page_limit", lg, limit=_n(page_limit)))
        if page_limit_note:
            parts.append(t("progress.page_note", lg, note=page_limit_note))
        parts.append(t("progress.ratelimit_footer", lg))
        return "".join(parts)

    if phase == "scan":
        if simple_progress:
            return _format_progress_message_simple_user(
                collection_name,
                loaded,
                listings,
                collection_total_approx=collection_total_approx,
                lang=lg,
            )
        parts = [t("progress.scan_title", lg)]
        if collection_total_approx and collection_total_approx > 0:
            parts.append(
                t(
                    "progress.scan_loaded_approx",
                    lg,
                    loaded=_n(loaded),
                    total=_n(collection_total_approx),
                )
            )
        else:
            parts.append(t("progress.scan_loaded", lg, loaded=_n(loaded)))
        parts.append(t("progress.scan_listings", lg, listings=_n(listings)))
        parts.append(t("progress.scan_mode", lg))
        if page_limit and page_limit > 0:
            parts.append(t("progress.scan_page_limit", lg, limit=_n(page_limit)))
        if page_limit_note:
            parts.append(t("progress.scan_note", lg, note=page_limit_note))
        parts.append(t("progress.scan_source", lg))
        return "".join(parts)

    return t("progress.default", lg, coll=coll, loaded=_n(loaded), listings=_n(listings))


_NFT_RESOLVER_MAX_PAGES = 80


def _nft_item_matches_collection_number(item: dict[str, Any], collection_name: str, number: int) -> bool:
    raw_i = item.get("index")
    if raw_i is not None:
        try:
            if int(raw_i) == number:
                return True
        except (TypeError, ValueError):
            pass
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    iname = str(meta.get("name") or item.get("name") or "")
    parsed = parse_number_from_nft_name(iname)
    if parsed is not None and parsed == number:
        return True
    tag = f"#{number}"
    low = iname.lower()
    if tag in iname or f"# {number}" in low:
        return True
    want = normalize_collection_match_key(f"{collection_name.strip()} #{number}")
    if want and normalize_collection_match_key(iname) == want:
        return True
    return False


async def resolve_target_nft_from_collection_number(
    client: TonAPICollectionClient,
    settings: Settings,
    collection_address: str,
    collection_name: str,
    number: int,
    *,
    max_pages: int | None = None,
) -> TargetNftInfo | None:
    """Locate the NFT item inside a collection via TonAPI items pagination (bounded)."""
    page_limit = min(1000, max(100, initial_full_scan_page_limit(settings)))
    offset = 0
    cap = max_pages if max_pages is not None else _NFT_RESOLVER_MAX_PAGES
    for _ in range(max(1, int(cap))):
        items, status, _snippet, _root = await client.fetch_collection_items_page_raw(
            collection_address, limit=page_limit, offset=offset
        )
        if status != 200:
            break
        for item in items:
            if not _nft_item_matches_collection_number(item, collection_name, number):
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            name = str(meta.get("name") or item.get("name") or f"#{number}")
            addr = str(item.get("address") or "").strip()
            num = parse_number_from_nft_name(name)
            if num is None:
                num = number
            traits = normalize_traits_from_nft_item(item)
            img, prev = extract_nft_media_urls(item, ipfs_gateway_url=settings.ipfs_gateway_url)
            pm = extract_nft_preview_media(item, ipfs_gateway_url=settings.ipfs_gateway_url)
            rich_url = pm.url if pm.kind in ("animation", "video") and pm.url else None
            rich_kind = pm.kind if rich_url else None
            return TargetNftInfo(
                name=name,
                number=num,
                address=addr,
                collection_name=collection_name.strip() or "Collection",
                collection_address=collection_address.strip(),
                model=traits.get("model"),
                backdrop=traits.get("backdrop"),
                symbol=traits.get("symbol"),
                traits_normalized=dict(traits),
                image_url=img,
                preview_url=prev,
                rich_preview_url=rich_url,
                rich_preview_kind=rich_kind,
            )
        if len(items) < page_limit:
            break
        offset += len(items)
    return None


async def resolve_target_for_full_market(
    raw_text: str,
    user: Any,
    settings: Settings,
    client: TonAPICollectionClient,
) -> tuple[TargetNftInfo | None, str | None]:
    from app.services.gift_intake import parse_gift_input, parse_nft_address
    from app.services.gift_resolver import resolve_gift_identity

    text = raw_text.strip()
    registry = load_collection_registry(settings.collection_registry_path)

    gi = parse_gift_input(text)
    if getattr(gi, "source_hint", None) == "getgems_startapp_collection_only":
        return None, (
            "Это ссылка на коллекцию, а не на конкретный NFT. "
            "Пришли ссылку на сам NFT."
        )
    addr = gi.nft_address or parse_nft_address(text)

    def _tonapi_not_found_msg() -> str:
        return (
            "❌ Не нашёл NFT через TonAPI.\n\n"
            "Проверь адрес или пришли ссылку на NFT / Telegram Gift."
        )

    async def _safe_get_nft(nft_address: str) -> dict[str, Any] | None:
        try:
            return await client.get_nft(nft_address)
        except MarketSourceUnavailable as exc:
            msg = str(exc).lower()
            if "404" in msg:
                return None
            raise

    if addr:
        nft = await _safe_get_nft(addr)
        if not nft:
            return None, _tonapi_not_found_msg()
        tgt = target_from_nft_payload(nft, ipfs_gateway_url=settings.ipfs_gateway_url)
        if not tgt:
            return None, (
                "❌ NFT найден, но TonAPI не вернул адрес коллекции.\n\n"
                "Попробуй позже или пришли другую ссылку."
            )
        return tgt, None

    _, identity = await resolve_gift_identity(user, text, settings)
    if identity.nft_address:
        nft = await _safe_get_nft(identity.nft_address)
        if not nft:
            return None, _tonapi_not_found_msg()
        tgt = target_from_nft_payload(nft, ipfs_gateway_url=settings.ipfs_gateway_url)
        if not tgt:
            return None, (
                "❌ NFT найден, но TonAPI не вернул адрес коллекции.\n\n"
                "Попробуй позже или пришли другую ссылку."
            )
        return tgt, None

    coll_name = identity.collection
    num = identity.number
    if coll_name in ("Unknown", "") or num is None:
        return None, (
            "❌ Не удалось автоматически определить коллекцию.\n\n"
            "Пришли NFT address или ссылку на NFT — так я смогу получить коллекцию через TonAPI."
        )

    if getattr(settings, "nft_global_index_enabled", False):
        from app.db.session import SessionLocal
        from app.services.nft_global_resolve import try_resolve_via_global_index

        async with SessionLocal() as session:
            g_tgt, g_err = await try_resolve_via_global_index(
                session,
                settings,
                client,
                display_collection=coll_name,
                number=int(num),
            )
        if g_tgt:
            return g_tgt, None
        if g_err:
            return None, g_err

    resolved = await resolve_collection_address_by_name(
        coll_name, settings=settings, client=client, registry=registry
    )

    if resolved.candidates and not resolved.address:
        display = coll_name.strip()
        return None, (
            f"⚠️ Нашёл несколько похожих коллекций для «{display}».\n\n"
            "Чтобы не ошибиться, пришли ссылку на NFT или NFT address."
        )

    c_addr = (resolved.address or "").strip()
    if not c_addr:
        display = coll_name.strip()
        if getattr(settings, "nft_global_index_enabled", False):
            from app.db.session import SessionLocal
            from app.services.nft_global_resolve import (
                enqueue_live_discovery,
                is_paid_user_plan,
                message_unknown_collection_free,
                message_unknown_collection_paid,
            )

            plan = getattr(user, "plan", None)
            paid = is_paid_user_plan(plan) and getattr(
                settings, "nft_global_index_live_discovery_for_paid", False
            )
            if paid:
                async with SessionLocal() as session:
                    await enqueue_live_discovery(session, settings, collection_hint=display)
                return None, message_unknown_collection_paid(display)
            return None, message_unknown_collection_free(display)
        return None, (
            f"❌ Не удалось автоматически найти коллекцию «{display}».\n\n"
            "Пришли ссылку на NFT или NFT address — так я точно определю коллекцию через TonAPI."
        )

    display_name = (resolved.name or coll_name).strip()
    tgt_hit = await resolve_target_nft_from_collection_number(
        client, settings, c_addr, display_name, int(num)
    )
    if not tgt_hit:
        return None, (
            f"❌ Не нашёл NFT #{num} в коллекции {display_name}. "
            "Пришли ссылку или NFT address."
        )
    return tgt_hit, None


async def run_full_market_analysis_flow(
    raw_text: str,
    user: Any,
    settings: Settings,
    client: TonAPICollectionClient,
    on_progress: Callable[[str, int, int, str, int, int | None, str | None], Awaitable[None]] | None = None,
    *,
    pre_resolved_target: TargetNftInfo | None = None,
) -> tuple[FullMarketNftReport | None, str | None]:
    if not settings.tonapi_enabled:
        return None, "Реальный рынок недоступен: включите TONAPI_ENABLED=true в .env."
    if not client.configured:
        return None, "Реальный рынок недоступен: TONAPI_API_KEY не задан"

    if not settings.full_market_scan_enabled:
        return None, "Полный скан рынка выключен (FULL_MARKET_SCAN_ENABLED=false)."

    if pre_resolved_target is not None:
        tgt = pre_resolved_target
        err = None
    else:
        tgt, err = await resolve_target_for_full_market(raw_text, user, settings, client)
    if err or not tgt:
        return None, err or "Не удалось определить NFT."

    start_lim = effective_collection_page_limit(settings)
    if normalize_plan_for_limits(getattr(user, "plan", None)) == "free":
        # MVP: на Free — более узкий page limit (basic / fast), без обещания полного рынка по гигантским коллекциям.
        start_lim = min(start_lim, 500)

    async def _prog(
        loaded: int,
        listings: int,
        phase: str,
        page_limit: int = 0,
        total_apx: int | None = None,
        note: str | None = None,
    ) -> None:
        if on_progress:
            await on_progress(tgt.collection_name, loaded, listings, phase, page_limit, total_apx, note)

    if on_progress:
        await on_progress(tgt.collection_name, 0, 0, "prepare", start_lim, None, None)

    rows, loaded, partial, cache_age, coll_total_apx = await get_cached_or_scan_collection(
        client, settings, tgt.collection_address, on_progress=_prog
    )

    hit = find_target_row(rows, tgt)
    if hit:
        tgt = enrich_target_from_row(tgt, hit)
    elif not (tgt.model or tgt.backdrop or tgt.symbol):
        return (
            None,
            f"В загруженных {loaded} NFT не найден #{tgt.number}. Пришлите NFT address (Tonviewer/TonAPI).",
        )

    rep = build_full_report(
        tgt,
        rows,
        loaded_count=loaded,
        is_partial_scan=partial,
        settings=settings,
        cache_age_minutes=cache_age,
        collection_total_approx=coll_total_apx,
    )
    if rep is not None and getattr(settings, "nft_global_index_enabled", False):
        from app.db.session import SessionLocal
        from app.services.nft_global_resolve import learn_from_successful_nft_check

        nft_raw = None
        if (getattr(rep.target, "address_kind", None) or "") != "getgems_gift_ref":
            if (rep.target.address or "").strip():
                nft_raw = await client.get_nft(rep.target.address.strip())
        async with SessionLocal() as session:
            await learn_from_successful_nft_check(session, settings, rep.target, nft_raw=nft_raw)
    return rep, None

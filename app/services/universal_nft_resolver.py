from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any

from app.config import Settings
from app.db.repositories import nft_global_index_repo as repo
from app.db.session import SessionLocal
from app.services.nft_global_resolve import learn_from_successful_nft_check
from app.services.nft_name_index import normalize_nft_text, parse_collection_number_payload
from app.services.nft_global_resolve import (
    enqueue_live_discovery,
    is_paid_user_plan,
    message_unknown_collection_free,
    message_unknown_collection_paid,
)
from app.services.gift_intake import GiftInput, GiftInputType, parse_gift_input, parse_nft_address
from app.services.nft_tonapi_image import extract_nft_preview_media
from app.services.real_market_collection_scan import (
    TargetNftInfo,
    extract_nft_media_urls,
    normalize_traits_from_nft_item,
    resolve_target_for_full_market,
    resolve_target_nft_from_collection_number,
    target_from_nft_payload,
)
from app.services.getgems_web_next_data import resolve_getgems_startapp_via_web
from app.services.tonapi_collection_client import TonAPICollectionClient
from app.services.toncenter_client import ToncenterClient
from app.sources.http import MarketSourceUnavailable

import asyncio
import logging

logger = logging.getLogger(__name__)

_LAST_DISCOVERY_TRACE: dict[str, Any] | None = None


def get_last_discovery_trace() -> dict[str, Any] | None:
    return dict(_LAST_DISCOVERY_TRACE) if isinstance(_LAST_DISCOVERY_TRACE, dict) else None

@dataclass
class ResolvedNft:
    original_payload: str
    nft_address: str
    collection_address: str
    nft_name: str
    collection_name: str
    item_number: int | None
    image_url: str | None
    traits: dict[str, str | None]
    sale_price_ton: float | None
    for_sale: bool
    source: str
    learned: bool
    target: TargetNftInfo
    nft_raw: dict[str, Any] | None
    resolver_trace: dict[str, Any] | None = None
    user_source_label: str = "TonAPI"
    external_sale_hint: bool = False
    preview_trait_lines: list[tuple[str, str]] | None = None
    animation_url: str | None = None
    address_kind: str | None = None
    nft_address_is_tonapi_valid: bool = True
    resolution_source_hint: str | None = None


@dataclass
class ResolveError:
    code: str
    message: str


def _set_trace(trace: dict[str, Any]) -> None:
    global _LAST_DISCOVERY_TRACE
    _LAST_DISCOVERY_TRACE = dict(trace)


_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_DROP_WORDS = {"nft", "gifts", "gift", "collection"}


def _norm_name(value: str, *, weak: bool = False) -> str:
    s = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    s = s.replace("_", " ").replace("-", " ").replace(".", " ")
    # Remove symbols/punctuation/emoji while keeping letters/digits/spaces.
    s = _NON_WORD_RE.sub(" ", s)
    s = _SPACE_RE.sub(" ", s).strip()
    if weak and s:
        toks = [t for t in s.split(" ") if t and t not in _DROP_WORDS]
        s = " ".join(toks).strip()
    return s


def _token_overlap_score(a: str, b: str) -> int:
    sa = {x for x in a.split(" ") if x}
    sb = {x for x in b.split(" ") if x}
    if not sa or not sb:
        return 0
    inter = len(sa & sb)
    if inter == 0:
        return 0
    union = len(sa | sb)
    j = inter / max(1, union)
    return int(50 + j * 20)


def _score_name_match(query: str, candidate: str) -> tuple[int, str]:
    qn = _norm_name(query, weak=False)
    cn = _norm_name(candidate, weak=False)
    if not qn or not cn:
        return 0, "empty"
    if qn == cn:
        return 100, "exact_normalized"
    qw = _norm_name(query, weak=True)
    cw = _norm_name(candidate, weak=True)
    if qw and cw and qw == cw:
        return 95, "weak_normalized_equal"
    if cn.startswith(qn) or (cw and qw and cw.startswith(qw)):
        return 80, "startswith"
    if qn in cn or (qw and cw and qw in cw):
        return 65, "contains"
    token_score = _token_overlap_score(qn, cn)
    if token_score >= 50:
        return token_score, "token_overlap"
    ratio = int(SequenceMatcher(None, qn, cn).ratio() * 100)
    if ratio >= 70:
        return min(79, ratio), "fuzzy_ratio"
    return 0, "no_match"


def _extract_ton_sale_price(nft_raw: dict[str, Any] | None) -> tuple[float | None, bool]:
    if not isinstance(nft_raw, dict):
        return None, False
    sale = nft_raw.get("sale") if isinstance(nft_raw.get("sale"), dict) else None
    if not sale:
        return None, False
    price = sale.get("price") if isinstance(sale.get("price"), dict) else {}
    token_name = str(price.get("token_name") or price.get("currency") or "").strip().upper()
    if token_name and token_name != "TON":
        return None, True
    value_raw = price.get("value")
    decimals = int(price.get("decimals") or 9)
    try:
        nano = int(value_raw)
    except (TypeError, ValueError):
        return None, True
    return nano / (10 ** max(0, decimals)), True


async def _enqueue_paid_index_search(user: Any, settings: Settings, payload: str) -> None:
    if not getattr(settings, "nft_global_index_enabled", False):
        return
    if not is_paid_user_plan(getattr(user, "plan", None)):
        return
    parsed = parse_collection_number_payload(payload)
    if not parsed:
        return
    coll_name, _num = parsed
    try:
        async with SessionLocal() as session:
            await enqueue_live_discovery(session, settings, collection_hint=coll_name)
    except Exception:
        logger.debug("enqueue paid index search skipped")


async def _friendly_name_number_not_found(payload: str, user: Any, settings: Settings) -> str:
    parsed = parse_collection_number_payload(payload)
    if not parsed:
        return "❌ Не удалось определить NFT."
    coll_name, _num = parsed
    if is_paid_user_plan(getattr(user, "plan", None)):
        await _enqueue_paid_index_search(user, settings, payload)
        return message_unknown_collection_paid(coll_name)
    return message_unknown_collection_free(coll_name)


def _target_from_toncenter_item(
    item: dict[str, Any],
    *,
    payload: str,
    ipfs_gateway_url: str = "https://ipfs.io/ipfs/",
    collection_address_hint: str | None = None,
) -> TargetNftInfo | None:
    if not isinstance(item, dict):
        return None
    addr = str(
        item.get("address")
        or item.get("raw_address")
        or item.get("friendly_address")
        or item.get("nft_address")
        or ""
    ).strip()
    coll_blk = item.get("collection") if isinstance(item.get("collection"), dict) else {}
    caddr = str(item.get("collection_address") or coll_blk.get("address") or "").strip()
    if collection_address_hint and not caddr:
        caddr = collection_address_hint.strip()
    elif collection_address_hint and caddr and caddr != collection_address_hint.strip():
        # Prefer on-chain collection from indexer; hint used only when missing.
        pass
    if not addr:
        return None
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    meta_inner = meta.get("content") if isinstance(meta.get("content"), dict) else {}
    c_meta = coll_blk.get("metadata") if isinstance(coll_blk.get("metadata"), dict) else {}
    c_content = coll_blk.get("content") if isinstance(coll_blk.get("content"), dict) else {}
    name = (
        str(meta.get("name") or content.get("name") or meta_inner.get("name") or item.get("name") or payload or "NFT")
        .strip()
        or "NFT"
    )
    coll_name = str(
        item.get("collection_name")
        or coll_blk.get("name")
        or c_meta.get("name")
        or c_content.get("name")
        or meta.get("collection_name")
        or "Collection"
    ).strip() or "Collection"
    n = item.get("index")
    if n is None:
        n = item.get("item_index")
    try:
        number = int(n) if n is not None else None
    except (TypeError, ValueError):
        number = None
    traits = normalize_traits_from_nft_item(item)
    model = traits.get("model")
    backdrop = traits.get("backdrop")
    symbol = traits.get("symbol")
    img, prev = extract_nft_media_urls(item, ipfs_gateway_url=ipfs_gateway_url)
    pm = extract_nft_preview_media(item, ipfs_gateway_url=ipfs_gateway_url)
    rich_url = pm.url if pm.kind in ("animation", "video") and pm.url else None
    rich_kind = pm.kind if rich_url else None
    return TargetNftInfo(
        name=name,
        number=number,
        address=addr,
        collection_name=coll_name,
        collection_address=caddr or (collection_address_hint or "").strip(),
        model=model,
        backdrop=backdrop,
        symbol=symbol,
        traits_normalized=dict(traits),
        image_url=img,
        preview_url=prev,
        rich_preview_url=rich_url,
        rich_preview_kind=rich_kind,
    )


async def resolve_nft_item_via_toncenter(
    settings: Settings,
    address: str,
    *,
    collection_address_hint: str | None = None,
    source_hint: str | None = None,
) -> tuple[TargetNftInfo | None, dict[str, Any]]:
    """
    GET {TONCENTER}/nft/items?address=…&limit=1 — normalized TargetNftInfo.
    """
    trace: dict[str, Any] = {
        "toncenter_item_lookup": "skipped",
        "source_hint": source_hint,
    }
    tc = ToncenterClient(settings)
    if not tc.configured():
        trace["toncenter_item_lookup"] = "disabled"
        return None, trace
    item = await tc.fetch_nft_item_by_address(address.strip(), trace=trace)
    if not item:
        trace["toncenter_item_lookup"] = "not_found"
        return None, trace
    trace["toncenter_item_lookup"] = "ok"
    tgt = _target_from_toncenter_item(
        item,
        payload=address,
        ipfs_gateway_url=settings.ipfs_gateway_url,
        collection_address_hint=collection_address_hint,
    )
    if not tgt:
        trace["toncenter_item_lookup"] = "invalid_shape"
        return None, trace
    return tgt, trace


def getgems_startapp_failure_user_message(trace: dict[str, Any]) -> str:
    """
    Понятное объяснение: TonAPI 404 ≠ «Toncenter не работал».
    Toncenter может ответить 200 с пустым списком или с объектом без адреса.
    """
    if trace.get("getgems_web_attempted") and not trace.get("getgems_item_found"):
        return (
            "❌ Не смог получить конкретный NFT из этой Telegram-ссылки.\n\n"
            "Эта ссылка открывается через Getgems Mini App, но публичные данные NFT не удалось получить автоматически.\n\n"
            "Открой NFT на Getgems / Tonviewer / Fragment и пришли прямую ссылку на сам NFT."
        )
    lookup = str(trace.get("toncenter_item_lookup") or "")
    http_ok = trace.get("toncenter_http_ok")
    n_items = trace.get("toncenter_items_count")
    http_err = trace.get("toncenter_http_err")

    if lookup == "invalid_shape":
        return (
            "❌ Не нашёл NFT по этой ссылке.\n\n"
            "Toncenter вернул запись, но без ожидаемого адреса NFT в ответе — не смог разобрать карточку.\n"
            "Попробуй прямую ссылку на NFT со страницы Getgems, Fragment или Tonviewer."
        )
    if lookup == "disabled":
        return (
            "❌ Не нашёл NFT по этой ссылке.\n\n"
            "TonAPI не вернул карточку, а запрос к Toncenter сейчас отключён в настройках бота.\n"
            "Попробуй другую ссылку или обратись к администратору (Toncenter / TonAPI)."
        )
    if http_ok is True and n_items == 0:
        return (
            "❌ Не нашёл NFT по этой ссылке.\n\n"
            "TonAPI не вернул эту карточку (404). Toncenter ответил успешно, но **по этому адресу в индексе пусто** "
            "(нет ни одной записи NFT). Для части Telegram Gift так бывает: адрес есть в ссылке, "
            "но индекс ещё не содержит объект или Getgems использует другой идентификатор.\n\n"
            "Попробуй открыть подарок в Getgems и прислать **прямую ссылку на страницу NFT** ещё раз, "
            "или ссылку с Fragment / Tonviewer."
        )
    if http_ok is False:
        err_bit = f" ({http_err})" if http_err else ""
        return (
            "❌ Не нашёл NFT по этой ссылке.\n\n"
            "TonAPI не вернул карточку. Запрос к Toncenter не удался или вернул ошибку"
            f"{err_bit}.\n"
            "Попробуй позже или пришли прямую ссылку на NFT с Getgems / Fragment / Tonviewer."
        )
    return (
        "❌ Не нашёл NFT по этой ссылке.\n\n"
        "TonAPI не вернул карточку, а по данным Toncenter собрать NFT тоже не вышло.\n"
        "Попробуй открыть NFT в Getgems и прислать прямую ссылку на сам NFT ещё раз."
    )


def _target_from_getgems_web_payload(
    web: dict[str, Any],
    *,
    raw_ref: str,
    collection_address: str,
) -> TargetNftInfo:
    traits_norm = dict(web.get("traits_normalized") or {})
    anim = (web.get("animation_url") or "").strip() or None
    img = (web.get("image_url") or "").strip() or None
    return TargetNftInfo(
        name=str(web.get("nft_name") or "NFT").strip() or "NFT",
        number=web.get("item_number"),
        address=raw_ref.strip(),
        collection_name=str(web.get("collection_name") or "Collection").strip() or "Collection",
        collection_address=collection_address.strip(),
        model=web.get("model"),
        backdrop=web.get("backdrop"),
        symbol=web.get("symbol"),
        traits_normalized=traits_norm,
        image_url=img or None,
        preview_url=None,
        rich_preview_url=anim,
        rich_preview_kind="animation" if anim else None,
        address_kind="getgems_gift_ref",
    )


async def _resolve_getgems_startapp(
    gi: GiftInput,
    raw_payload: str,
    _user: Any,
    settings: Settings,
    client: TonAPICollectionClient,
    *,
    learn: bool,
) -> tuple[ResolvedNft | None, str | None]:
    nft_addr = (gi.nft_address or "").strip()
    coll_hint = (gi.collection_address or "").strip()
    trace: dict[str, Any] = {
        "input_type": "getgems_startapp",
        "decoded_path": gi.startapp_decoded_path,
        "collection_address_from_link": coll_hint or None,
        "nft_address_from_link": nft_addr or None,
        "raw_ref_present": bool(nft_addr),
        "tonapi_retries": 0,
        "raw_ref_tonapi_retries": 0,
        "tonapi_get_nft_status": None,
        "raw_ref_tonapi_status": None,
        "toncenter_item_lookup": "skipped",
        "raw_ref_toncenter_items_count": None,
        "getgems_web_attempted": False,
        "final_source": None,
        "resolved": False,
    }
    if not nft_addr:
        trace["final_source"] = "invalid_input"
        _set_trace(trace)
        return (
            None,
            "❌ Не удалось разобрать ссылку Getgems: в startapp не найден адрес NFT.\n\n"
            "Открой подарок в Getgems и пришли прямую ссылку на страницу NFT.",
        )

    nft_raw: dict[str, Any] | None = None
    if client.configured:
        nft_raw = await client.get_nft(nft_addr)
    ta_st = 200 if isinstance(nft_raw, dict) else 404
    trace["tonapi_get_nft_status"] = ta_st
    trace["raw_ref_tonapi_status"] = ta_st

    target: TargetNftInfo | None = None
    source = "tonapi_short_scan"
    user_label = "TonAPI"

    if isinstance(nft_raw, dict):
        patched = dict(nft_raw)
        coll = patched.get("collection") if isinstance(patched.get("collection"), dict) else {}
        if coll_hint and not str(coll.get("address") or "").strip():
            patched["collection"] = {**coll, "address": coll_hint}
        target = target_from_nft_payload(patched, ipfs_gateway_url=settings.ipfs_gateway_url)
        if target and coll_hint and not (target.collection_address or "").strip():
            target = replace(target, collection_address=coll_hint)
        if target:
            trace["toncenter_item_lookup"] = "skipped"
            trace["final_source"] = "tonapi"

    web_payload_for_preview: dict[str, Any] | None = None

    if not target:
        tc_tgt, tc_trace = await resolve_nft_item_via_toncenter(
            settings,
            nft_addr,
            collection_address_hint=coll_hint or None,
            source_hint="getgems_startapp_toncenter_item",
        )
        trace.update(tc_trace)
        trace["raw_ref_toncenter_items_count"] = tc_trace.get("toncenter_items_count")
        if not tc_tgt:
            trace["getgems_web_attempted"] = True
            web_payload, web_trace = await resolve_getgems_startapp_via_web(coll_hint, nft_addr, settings)
            trace.update(web_trace)
            if web_payload and coll_hint:
                web_payload_for_preview = web_payload
                target = _target_from_getgems_web_payload(
                    web_payload,
                    raw_ref=nft_addr,
                    collection_address=coll_hint,
                )
                source = "getgems_web"
                user_label = "Getgems / TonAPI"
                nft_raw = {}
                img = (web_payload.get("image_url") or "").strip()
                anim = (web_payload.get("animation_url") or "").strip()
                meta: dict[str, Any] = {}
                if img:
                    meta["image"] = img
                if anim:
                    meta["animation_url"] = anim
                if meta:
                    nft_raw = {"metadata": meta}
                trace["final_source"] = "getgems_web"
            else:
                trace["final_source"] = "not_found"
                trace["resolved"] = False
                _set_trace(trace)
                return None, getgems_startapp_failure_user_message(trace)
        else:
            target = tc_tgt
            if coll_hint and not (target.collection_address or "").strip():
                target = replace(target, collection_address=coll_hint)
            source = "toncenter_item"
            user_label = "Toncenter"
            enrich = await client.get_nft((target.address or nft_addr).strip())
            trace["tonapi_enrich_after_toncenter_status"] = 200 if isinstance(enrich, dict) else 404
            if isinstance(enrich, dict):
                tt = target_from_nft_payload(enrich, ipfs_gateway_url=settings.ipfs_gateway_url)
                if tt:
                    target = tt
                    nft_raw = enrich
                    user_label = "TonAPI / Toncenter"
            trace["final_source"] = source

    if not target:
        trace["final_source"] = "not_found"
        trace["resolved"] = False
        _set_trace(trace)
        return None, getgems_startapp_failure_user_message(trace)

    sale_price_ton, for_sale = _extract_ton_sale_price(nft_raw)
    preview_lines: list[tuple[str, str]] | None = None
    animation_url: str | None = None
    address_kind = getattr(target, "address_kind", None)
    nft_address_is_tonapi_valid = (address_kind or "") != "getgems_gift_ref"
    resolution_source_hint: str | None = None
    ext_sale_hint = True

    if source == "getgems_web" and web_payload_for_preview:
        tdisp = dict(web_payload_for_preview.get("traits_display") or {})
        preview_lines = sorted(tdisp.items(), key=lambda x: x[0].lower())
        animation_url = (web_payload_for_preview.get("animation_url") or "").strip() or None
        lp = web_payload_for_preview.get("listing_price_ton")
        if lp is not None:
            sale_price_ton = float(lp)
            for_sale = True
            ext_sale_hint = False
        resolution_source_hint = "getgems_startapp_web_next_data"

    learned_ok = False
    if (
        learn
        and getattr(settings, "nft_global_index_enabled", False)
        and target
        and (getattr(target, "address_kind", None) or "") != "getgems_gift_ref"
    ):
        try:
            async with SessionLocal() as session:
                await learn_from_successful_nft_check(session, settings, target, nft_raw=nft_raw)
            learned_ok = True
        except Exception:
            learned_ok = False

    trace["resolved"] = True
    trace["final_source"] = trace.get("final_source") or source
    trace["resolved_name"] = (target.name or "").strip() or None
    trace["resolved_collection_name"] = (target.collection_name or "").strip() or None
    _set_trace(trace)

    logger.info(
        "nft_resolver getgems_startapp source=%s toncenter=%s",
        source,
        trace.get("toncenter_item_lookup"),
    )
    return (
        ResolvedNft(
            original_payload=raw_payload,
            nft_address=(target.address or nft_addr).strip(),
            collection_address=(target.collection_address or coll_hint or "").strip(),
            nft_name=(target.name or "").strip() or "NFT",
            collection_name=(target.collection_name or "").strip() or "Collection",
            item_number=target.number,
            image_url=(target.image_url or "").strip() or None,
            traits={
                "model": target.model,
                "backdrop": target.backdrop,
                "symbol": target.symbol,
            },
            sale_price_ton=sale_price_ton,
            for_sale=for_sale,
            source=source,
            learned=learned_ok,
            target=target,
            nft_raw=nft_raw if isinstance(nft_raw, dict) else None,
            resolver_trace=dict(trace),
            user_source_label=user_label,
            external_sale_hint=ext_sale_hint,
            preview_trait_lines=preview_lines,
            animation_url=animation_url,
            address_kind=address_kind,
            nft_address_is_tonapi_valid=nft_address_is_tonapi_valid,
            resolution_source_hint=resolution_source_hint,
        ),
        None,
    )


async def _resolve_via_toncenter(
    payload: str,
    user: Any,
    settings: Settings,
    client: TonAPICollectionClient,
    *,
    live_discovery: bool = True,
    max_pages_override: int | None = None,
) -> tuple[TargetNftInfo | None, str | None, str]:
    trace: dict[str, Any] = {
        "input": payload,
        "base_name": None,
        "normalized_base_name": None,
        "item_number": None,
        "local_alias_hit": False,
        "local_collections_checked": 0,
        "toncenter_enabled": False,
        "toncenter_collections_pages_checked": 0,
        "toncenter_collections_checked": 0,
        "toncenter_candidate_names_sample": [],
        "toncenter_best_candidates": [],
        "tonapi_collections_pages_checked": 0,
        "tonapi_candidate_names_sample": [],
        "chosen_collection_address": None,
        "chosen_collection_name": None,
        "match_confidence": None,
        "item_lookup_tried": False,
        "final_reason": "not_found",
    }
    tc = ToncenterClient(settings)
    trace["toncenter_enabled"] = bool(tc.configured())
    if not tc.configured():
        trace["final_reason"] = "toncenter_not_configured"
        _set_trace(trace)
        return None, None, "not_found"
    gi = parse_gift_input(payload)
    addr = gi.nft_address or parse_nft_address(payload)
    if addr:
        item = await tc.fetch_nft_item_by_address(addr, trace=trace)
        if not item:
            trace["final_reason"] = "address_not_found"
            _set_trace(trace)
            return None, None, "not_found"
        tgt = _target_from_toncenter_item(
            item, payload=payload, ipfs_gateway_url=settings.ipfs_gateway_url
        )
        if not tgt:
            trace["final_reason"] = "address_item_invalid"
            _set_trace(trace)
            return None, None, "not_found"
        nft_raw = await client.get_nft(tgt.address)
        if nft_raw:
            tt = target_from_nft_payload(nft_raw, ipfs_gateway_url=settings.ipfs_gateway_url)
            if tt:
                trace["final_reason"] = "resolved_by_address_tonapi_enrich"
                _set_trace(trace)
                return tt, None, "tonapi_short_scan"
        trace["final_reason"] = "resolved_by_address_toncenter_item"
        _set_trace(trace)
        return tgt, None, "toncenter_item"

    parsed = parse_collection_number_payload(payload)
    if not parsed:
        trace["final_reason"] = "not_name_number_payload"
        _set_trace(trace)
        return None, None, "not_found"
    coll_name, number = parsed
    base_norm = normalize_nft_text(coll_name)
    trace["base_name"] = coll_name
    trace["normalized_base_name"] = _norm_name(coll_name)
    trace["item_number"] = int(number)
    if not base_norm:
        trace["final_reason"] = "empty_normalized_name"
        _set_trace(trace)
        return None, None, "not_found"

    async with SessionLocal() as session:
        aliases = await repo.find_aliases_by_normalized(session, base_norm)
        coll_rows = await repo.find_collection_by_name_normalized(session, base_norm)
    trace["local_collections_checked"] = len(coll_rows)
    cand_addrs = [a.collection_address for a in aliases if a.collection_address]
    trace["local_alias_hit"] = bool(cand_addrs)
    if not cand_addrs and len(coll_rows) == 1 and coll_rows[0].collection_address:
        cand_addrs = [coll_rows[0].collection_address]
    for caddr in cand_addrs[:25]:
        trace["item_lookup_tried"] = True
        item = await tc.fetch_nft_item_by_collection_and_index(caddr, int(number))
        if not item:
            continue
        tgt = _target_from_toncenter_item(
            item, payload=payload, ipfs_gateway_url=settings.ipfs_gateway_url
        )
        if not tgt:
            continue
        nft_raw = await client.get_nft(tgt.address)
        if nft_raw:
            tt = target_from_nft_payload(nft_raw, ipfs_gateway_url=settings.ipfs_gateway_url)
            if tt:
                trace["chosen_collection_address"] = caddr
                trace["chosen_collection_name"] = tt.collection_name
                trace["match_confidence"] = "high"
                trace["final_reason"] = "resolved_from_local_alias_toncenter_item"
                _set_trace(trace)
                return tt, None, "local_alias_toncenter"
        trace["chosen_collection_address"] = caddr
        trace["match_confidence"] = "high"
        trace["final_reason"] = "resolved_from_local_alias_toncenter_item_raw"
        _set_trace(trace)
        return tgt, None, "local_alias_toncenter"

    if not live_discovery:
        trace["final_reason"] = "live_discovery_disabled"
        _set_trace(trace)
        return None, None, "not_found"

    is_paid = (getattr(user, "plan", "") or "").lower() in {"pro", "trader", "sniper"}
    max_pages = (
        max_pages_override
        if max_pages_override is not None
        else (
            int(getattr(settings, "nft_live_discovery_max_pages_paid", 30))
            if is_paid
            else int(getattr(settings, "nft_live_discovery_max_pages_free", 2))
        )
    )
    page_limit = int(getattr(settings, "nft_live_discovery_page_limit", 100) or 100)
    sleep_s = max(0.0, float(getattr(settings, "nft_live_discovery_sleep_ms", 1200) or 1200) / 1000.0)
    candidates: list[tuple[int, str, str, str]] = []
    sample_names: list[str] = []
    tonapi_sample_names: list[str] = []
    for page in range(max(1, max_pages)):
        ok, rows, err, _raw = await tc.fetch_nft_collections_page(limit=page_limit, offset=page * page_limit)
        trace["toncenter_collections_pages_checked"] = int(trace["toncenter_collections_pages_checked"]) + 1
        if err == "rate_limited":
            if bool(getattr(settings, "nft_live_discovery_stop_on_429", True)):
                trace["final_reason"] = "discovery_deferred_rate_limited"
                _set_trace(trace)
                return None, "discovery_deferred", "discovery_deferred"
            await asyncio.sleep(max(1.0, float(getattr(settings, "nft_live_discovery_429_backoff_seconds", 10))))
            continue
        if not ok:
            break
        if not rows:
            break
        trace["toncenter_collections_checked"] = int(trace["toncenter_collections_checked"]) + len(rows)
        for r in rows:
            cname = str(r.get("name") or r.get("collection_name") or "").strip()
            caddr = str(r.get("address") or r.get("collection_address") or "").strip()
            if not cname or not caddr:
                continue
            if len(sample_names) < 20:
                sample_names.append(cname)
            score, reason = _score_name_match(coll_name, cname)
            if score > 0:
                candidates.append((score, caddr, cname, reason))
        if len(rows) < page_limit:
            break
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)
    # TonAPI collections probe for trace/comparison.
    if hasattr(client, "fetch_nft_collections_page"):
        for page in range(max(1, max_pages)):
            rows, status, _ = await client.fetch_nft_collections_page(limit=page_limit, offset=page * page_limit)
            trace["tonapi_collections_pages_checked"] = int(trace["tonapi_collections_pages_checked"]) + 1
            if status != 200 or not rows:
                break
            for r in rows:
                cname = str(r.get("name") or r.get("collection_name") or "").strip()
                if cname and len(tonapi_sample_names) < 20:
                    tonapi_sample_names.append(cname)
            if len(rows) < page_limit:
                break
    trace["toncenter_candidate_names_sample"] = sample_names[:10]
    trace["tonapi_candidate_names_sample"] = tonapi_sample_names[:10]
    candidates.sort(key=lambda x: x[0], reverse=True)
    trace["toncenter_best_candidates"] = [
        {"name": n, "address": a, "score": s, "reason": rsn, "source": "toncenter"}
        for s, a, n, rsn in candidates[:5]
    ]

    strong = [c for c in candidates if c[0] >= 90]
    medium = [c for c in candidates if c[0] >= 80]
    chosen: tuple[int, str, str, str] | None = None
    if len(strong) == 1:
        chosen = strong[0]
    elif len(strong) == 0 and len(medium) == 1:
        chosen = medium[0]

    if len(medium) > 1:
        trace["final_reason"] = "ambiguous_candidates"
        _set_trace(trace)
        return None, "⚠️ Нашёл несколько похожих коллекций. Пришли ссылку на NFT или NFT address.", "not_found"

    if chosen:
        score, caddr, cname, _ = chosen
        trace["chosen_collection_address"] = caddr
        trace["chosen_collection_name"] = cname
        trace["match_confidence"] = "high" if score >= 90 else "medium"
        trace["item_lookup_tried"] = True
        item = await tc.fetch_nft_item_by_collection_and_index(caddr, int(number))
        if item:
            tgt = _target_from_toncenter_item(
                item, payload=payload, ipfs_gateway_url=settings.ipfs_gateway_url
            )
            if tgt:
                async with SessionLocal() as session:
                    await repo.upsert_collection(
                        session,
                        collection_address=caddr,
                        collection_name=cname,
                        collection_name_normalized=normalize_nft_text(cname),
                        owner_address=None,
                        next_item_index=None,
                        source="toncenter",
                        index_status="metadata_indexed",
                    )
                    await repo.upsert_alias(
                        session,
                        alias_normalized=base_norm,
                        display_name=cname[:255],
                        collection_address=caddr,
                        source="live_discovery_toncenter",
                        confidence="high",
                    )
                    await session.commit()
                trace["final_reason"] = "resolved_toncenter_collection_item_index"
                _set_trace(trace)
                return tgt, None, "live_discovery_toncenter"
        # fallback B: TonAPI short scan by chosen collection.
        tgt2 = await resolve_target_nft_from_collection_number(
            client,
            settings,
            caddr,
            cname,
            int(number),
            max_pages=max_pages,
        )
        if tgt2:
            nft_raw = await client.get_nft(tgt2.address)
            if isinstance(nft_raw, dict):
                tt = target_from_nft_payload(nft_raw, ipfs_gateway_url=settings.ipfs_gateway_url)
                if tt:
                    async with SessionLocal() as session:
                        await repo.upsert_alias(
                            session,
                            alias_normalized=base_norm,
                            display_name=cname[:255],
                            collection_address=caddr,
                            source="live_discovery_toncenter",
                            confidence="high",
                        )
                        await session.commit()
                    trace["final_reason"] = "resolved_via_tonapi_short_scan_after_candidate"
                    _set_trace(trace)
                    return tt, None, "toncenter_item"
        trace["final_reason"] = "candidate_found_item_not_found"
        _set_trace(trace)
        return None, None, "not_found"
    trace["final_reason"] = "no_collection_candidate"
    _set_trace(trace)
    return None, None, "not_found"


def _user_source_label_for_resolve(source: str, nft_raw: dict[str, Any] | None) -> str:
    s = (source or "").lower()
    if "toncenter" in s:
        return "TonAPI / Toncenter" if isinstance(nft_raw, dict) else "Toncenter"
    return "TonAPI"


async def resolve_universal_nft(
    payload: str,
    user: Any,
    settings: Settings,
    client: TonAPICollectionClient,
    *,
    learn: bool = True,
    live_discovery: bool = True,
    max_pages: int | None = None,
) -> tuple[ResolvedNft | None, str | None]:
    raw_payload = (payload or "").strip()
    gi0 = parse_gift_input(raw_payload)
    if gi0.input_type == GiftInputType.getgems_startapp and gi0.nft_address:
        return await _resolve_getgems_startapp(gi0, raw_payload, user, settings, client, learn=learn)
    source = "tonapi_short_scan"
    external_sale_hint = bool(
        gi0.input_type in {GiftInputType.marketplace_url, GiftInputType.telegram_gift_url, GiftInputType.getgems_startapp}
        and (
            (gi0.marketplace or "").lower() in {"getgems", "telegram"}
            or str(gi0.source_hint or "").startswith("getgems_startapp")
        )
    )
    try:
        target, err = await resolve_target_for_full_market(raw_payload, user, settings, client)
    except MarketSourceUnavailable as exc:
        low = str(exc).lower()
        if "404" in low:
            target, err, source = await _resolve_via_toncenter(
                raw_payload,
                user,
                settings,
                client,
                live_discovery=live_discovery,
                max_pages_override=max_pages,
            )
            if not target:
                return None, (
                    "❌ Не нашёл NFT через TonAPI.\n\n"
                    "Проверь адрес или пришли ссылку на NFT / Telegram Gift."
                )
        else:
            return None, "❌ TonAPI сейчас недоступен. Попробуй позже."

    if err or not target:
        t2, e2, s2 = await _resolve_via_toncenter(
            raw_payload,
            user,
            settings,
            client,
            live_discovery=live_discovery,
            max_pages_override=max_pages,
        )
        if t2:
            target = t2
            source = s2
            err = None
        else:
            if parse_collection_number_payload(raw_payload):
                if err == "discovery_deferred" or e2 == "discovery_deferred":
                    if is_paid_user_plan(getattr(user, "plan", None)):
                        await _enqueue_paid_index_search(user, settings, raw_payload)
                        return None, (
                            "❌ Пока не нашёл NFT «"
                            + raw_payload
                            + "».\n\nЯ запустил расширенный поиск по NFT-индексу. "
                            "TonAPI/Toncenter сейчас ограничивают частоту запросов. "
                            "Чтобы проверить сразу — пришли ссылку на конкретный NFT или NFT address."
                        )
                    return None, (
                        "❌ Не нашёл NFT «"
                        + raw_payload
                        + "».\n\nСейчас действует лимит запросов TonAPI. "
                        "Пришли ссылку на конкретный NFT или NFT address — так найду быстрее."
                    )
                if e2 and ("похож" in e2.lower() or "ambiguous" in e2.lower()):
                    return None, e2
                friendly = await _friendly_name_number_not_found(raw_payload, user, settings)
                return None, friendly
            return None, err or "❌ Не удалось определить NFT."

    nft_raw = None
    try:
        nft_raw = await client.get_nft(target.address)
    except MarketSourceUnavailable:
        nft_raw = None
    sale_price_ton, for_sale = _extract_ton_sale_price(nft_raw)

    learned_ok = False
    if learn and getattr(settings, "nft_global_index_enabled", False):
        try:
            async with SessionLocal() as session:
                await learn_from_successful_nft_check(session, settings, target, nft_raw=nft_raw)
            learned_ok = True
        except Exception:
            learned_ok = False

    logger.info(
        "nft_resolver source=%s has_target=%s toncenter_enabled=%s",
        source,
        bool(target),
        bool(getattr(settings, "toncenter_enabled", False)),
    )
    return (
        ResolvedNft(
            original_payload=raw_payload,
            nft_address=(target.address or "").strip(),
            collection_address=(target.collection_address or "").strip(),
            nft_name=(target.name or "").strip() or "NFT",
            collection_name=(target.collection_name or "").strip() or "Collection",
            item_number=target.number,
            image_url=(target.image_url or "").strip() or None,
            traits={
                "model": target.model,
                "backdrop": target.backdrop,
                "symbol": target.symbol,
            },
            sale_price_ton=sale_price_ton,
            for_sale=for_sale,
            source=source,
            learned=learned_ok,
            target=target,
            nft_raw=nft_raw if isinstance(nft_raw, dict) else None,
            resolver_trace=get_last_discovery_trace(),
            user_source_label=_user_source_label_for_resolve(source, nft_raw if isinstance(nft_raw, dict) else None),
            external_sale_hint=external_sale_hint,
        ),
        None,
    )


async def resolve_any_nft_input(
    payload: str,
    user: Any,
    settings: Settings,
    client: TonAPICollectionClient,
    *,
    learn: bool = True,
    live_discovery: bool = True,
    max_pages: int | None = None,
) -> tuple[ResolvedNft | None, ResolveError | None]:
    resolved, err = await resolve_universal_nft(
        payload,
        user,
        settings,
        client,
        learn=learn,
        live_discovery=live_discovery,
        max_pages=max_pages,
    )
    if err:
        return None, ResolveError(code="not_found", message=err)
    return resolved, None


async def search_nft_collections(
    query: str,
    settings: Settings,
    client: TonAPICollectionClient,
    *,
    source: str = "toncenter",
    max_pages: int = 30,
    page_limit: int = 100,
) -> dict[str, Any]:
    q = (query or "").strip()
    qn = _norm_name(q)
    best: list[dict[str, Any]] = []
    pages_checked = 0
    collections_checked = 0
    if source == "toncenter":
        tc = ToncenterClient(settings)
        if not tc.configured():
            return {
                "ok": False,
                "query": q,
                "normalized_query": qn,
                "pages_checked": 0,
                "collections_checked": 0,
                "best_candidates": [],
                "reason": "toncenter_not_configured",
            }
        for page in range(max(1, int(max_pages))):
            ok, rows, _err, _raw = await tc.fetch_nft_collections_page(limit=page_limit, offset=page * page_limit)
            pages_checked += 1
            if not ok or not rows:
                break
            collections_checked += len(rows)
            for r in rows:
                cname = str(r.get("name") or r.get("collection_name") or "").strip()
                caddr = str(r.get("address") or r.get("collection_address") or "").strip()
                if not cname or not caddr:
                    continue
                score, _reason = _score_name_match(q, cname)
                if score <= 0:
                    continue
                best.append({"name": cname, "address": caddr, "score": score, "source": "toncenter"})
            if len(rows) < page_limit:
                break
    else:
        for page in range(max(1, int(max_pages))):
            rows, status, _ = await client.fetch_nft_collections_page(limit=page_limit, offset=page * page_limit)
            pages_checked += 1
            if status != 200 or not rows:
                break
            collections_checked += len(rows)
            for r in rows:
                cname = str(r.get("name") or r.get("collection_name") or "").strip()
                caddr = str(r.get("address") or r.get("collection_address") or "").strip()
                if not cname or not caddr:
                    continue
                score, _reason = _score_name_match(q, cname)
                if score <= 0:
                    continue
                best.append({"name": cname, "address": caddr, "score": score, "source": "tonapi"})
            if len(rows) < page_limit:
                break
    best.sort(key=lambda x: int(x["score"]), reverse=True)
    return {
        "ok": True,
        "query": q,
        "normalized_query": qn,
        "pages_checked": pages_checked,
        "collections_checked": collections_checked,
        "best_candidates": best[:20],
    }

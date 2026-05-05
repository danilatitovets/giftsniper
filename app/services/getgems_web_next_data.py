"""Resolve Getgems NFT preview from public HTML __NEXT_DATA__ (no API keys, no browser)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import Settings
from app.services.nft_market_pricing_core import canonical_trait_type_key
from app.services.real_market_collection_scan import parse_number_from_nft_name

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script\s+id=["\']__NEXT_DATA__["\']\s+type=["\']application/json["\']>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

_MOZILLA_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _clamp_timeout_seconds(settings: Settings) -> float:
    base = float(getattr(settings, "market_http_timeout_seconds", 10) or 10)
    return max(10.0, min(15.0, base))


def _extract_next_data_json(html: str) -> dict[str, Any] | None:
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return None
    raw = (m.group(1) or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _gql_cache(root: dict[str, Any]) -> dict[str, Any]:
    props = root.get("props")
    if not isinstance(props, dict):
        return {}
    page = props.get("pageProps")
    if not isinstance(page, dict):
        return {}
    gc = page.get("gqlCache")
    return gc if isinstance(gc, dict) else {}


def _iter_gql_objects(gql_cache: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _k, val in gql_cache.items():
        if isinstance(val, dict):
            out.append(val)
    return out


def _find_nft_item(gql_cache: dict[str, Any], raw_ref: str) -> dict[str, Any] | None:
    want = (raw_ref or "").strip()
    for obj in _iter_gql_objects(gql_cache):
        if str(obj.get("__typename") or "") != "NftItem":
            continue
        if str(obj.get("address") or "").strip() == want:
            return obj
    return None


def _find_nft_collection(gql_cache: dict[str, Any], collection_address: str) -> dict[str, Any] | None:
    want = (collection_address or "").strip()
    for obj in _iter_gql_objects(gql_cache):
        if str(obj.get("__typename") or "") != "NftCollection":
            continue
        if str(obj.get("address") or "").strip() == want:
            return obj
    return None


def _find_nft_sale_fix_price(gql_cache: dict[str, Any], raw_ref: str) -> dict[str, Any] | None:
    want = (raw_ref or "").strip()
    for obj in _iter_gql_objects(gql_cache):
        if str(obj.get("__typename") or "") != "NftSaleFixPrice":
            continue
        if str(obj.get("address") or "").strip() == want:
            return obj
    return None


def _pick_http_url(*candidates: object) -> str | None:
    for c in candidates:
        if isinstance(c, str) and c.startswith(("http://", "https://")):
            return c.strip()
    return None


def _image_from_content_image_block(block: dict[str, Any] | None) -> str | None:
    if not isinstance(block, dict):
        return None
    u = _pick_http_url(block.get("sized"), block.get("baseUrl"), block.get("url"))
    if u:
        return u
    inner = block.get("image")
    if isinstance(inner, dict):
        return _pick_http_url(inner.get("sized"), inner.get("baseUrl"), inner.get("url"))
    return None


def extract_nft_image_url_from_gql_nft_item(item: dict[str, Any]) -> str | None:
    content = item.get("content")
    if not isinstance(content, dict):
        return None
    img = content.get("image")
    if isinstance(img, dict):
        u = _image_from_content_image_block(img)
        if u:
            return u
    return None


def extract_animation_url_from_gql_nft_item(item: dict[str, Any]) -> str | None:
    content = item.get("content")
    if isinstance(content, dict):
        u = _pick_http_url(
            content.get("animation_url"),
            content.get("animationUrl"),
        )
        if u:
            return u
    meta = item.get("metadata")
    if isinstance(meta, dict):
        u = _pick_http_url(meta.get("animation_url"), meta.get("animationUrl"))
        if u:
            return u
    return None


def traits_dict_from_nft_item_attributes(item: dict[str, Any]) -> dict[str, str]:
    """traitType -> value (original trait type keys for display)."""
    out: dict[str, str] = {}
    attrs = item.get("attributes")
    if not isinstance(attrs, list):
        return out
    for a in attrs:
        if not isinstance(a, dict):
            continue
        t = str(a.get("traitType") or a.get("trait_type") or "").strip()
        v = str(a.get("value") or a.get("trait_value") or "").strip()
        if t and v:
            out[t] = v
    return out


def ton_listing_price_from_sale_fix(sale: dict[str, Any] | None) -> float | None:
    if not isinstance(sale, dict):
        return None
    if str(sale.get("currency") or "").strip().upper() != "TON":
        return None
    fp = sale.get("fullPrice")
    try:
        nano = int(str(fp).strip())
    except (TypeError, ValueError):
        return None
    if nano <= 0:
        return None
    return nano / 1_000_000_000.0


def parse_getgems_next_data_bundle(
    next_data: dict[str, Any],
    *,
    collection_address: str,
    raw_ref: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    Returns (bundle, flags) where bundle has keys: nft_item, nft_collection, sale, traits_display, image_url, animation_url, listing_price_ton.
    flags: booleans for trace.
    """
    flags: dict[str, Any] = {
        "getgems_next_data_found": True,
        "getgems_item_found": False,
        "getgems_collection_found": False,
        "getgems_sale_found": False,
    }
    gc = _gql_cache(next_data)
    if not gc:
        flags["getgems_next_data_found"] = False
        return None, flags

    nft_item = _find_nft_item(gc, raw_ref)
    coll = _find_nft_collection(gc, collection_address)
    sale = _find_nft_sale_fix_price(gc, raw_ref)

    flags["getgems_item_found"] = bool(nft_item)
    flags["getgems_collection_found"] = bool(coll)
    flags["getgems_sale_found"] = bool(sale)

    if not nft_item:
        return None, flags

    traits_display = traits_dict_from_nft_item_attributes(nft_item)
    image_url = extract_nft_image_url_from_gql_nft_item(nft_item)
    animation_url = extract_animation_url_from_gql_nft_item(nft_item)
    listing = ton_listing_price_from_sale_fix(sale) if sale else None

    bundle = {
        "nft_item": nft_item,
        "nft_collection": coll,
        "sale": sale,
        "traits_display": traits_display,
        "image_url": image_url,
        "animation_url": animation_url,
        "listing_price_ton": listing,
    }
    return bundle, flags


async def fetch_getgems_html_status_body(url: str, *, timeout: float) -> tuple[int, str | None]:
    headers = {
        "User-Agent": _MOZILLA_UA,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.info("getgems web fetch failed url=%s err=%s", url[:80], type(exc).__name__)
        return 0, None
    text = resp.text or ""
    # Never log full HTML
    if len(text) > 2_000_000:
        text = text[:2_000_000]
    return int(resp.status_code), text


async def resolve_getgems_startapp_via_web(
    collection_address: str,
    raw_ref: str,
    settings: Settings,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    Try collection slug URL then /nft/{raw_ref}.
    Returns (payload, trace) — payload suitable for building TargetNftInfo / ResolvedNft, or None.
    """
    ca = (collection_address or "").strip()
    rr = (raw_ref or "").strip()
    trace: dict[str, Any] = {
        "getgems_web_url": None,
        "getgems_web_url_secondary": None,
        "getgems_web_status": None,
        "getgems_web_status_secondary": None,
        "getgems_next_data_found": False,
        "getgems_item_found": False,
        "getgems_collection_found": False,
        "getgems_sale_found": False,
        "resolved_name": None,
        "resolved_collection_name": None,
    }
    if not ca or not rr:
        return None, trace

    timeout = _clamp_timeout_seconds(settings)
    urls = [
        f"https://getgems.io/collection/{ca}/{rr}",
        f"https://getgems.io/nft/{rr}",
    ]

    for idx, url in enumerate(urls):
        trace["getgems_web_url" if idx == 0 else "getgems_web_url_secondary"] = url
        status, body = await fetch_getgems_html_status_body(url, timeout=timeout)
        key_status = "getgems_web_status" if idx == 0 else "getgems_web_status_secondary"
        trace[key_status] = status
        if status != 200 or not body:
            continue
        nd = _extract_next_data_json(body)
        trace["getgems_next_data_found"] = bool(nd)
        if not nd:
            continue
        bundle, flags = parse_getgems_next_data_bundle(nd, collection_address=ca, raw_ref=rr)
        trace.update(flags)
        if bundle:
            item = bundle["nft_item"]
            coll = bundle.get("nft_collection") or {}
            name = str(item.get("name") or "").strip() or "NFT"
            cname = str(coll.get("name") or "").strip() if isinstance(coll, dict) else ""
            trace["resolved_name"] = name
            trace["resolved_collection_name"] = cname or None
            traits_display: dict[str, str] = bundle["traits_display"]
            traits_norm: dict[str, str] = {}
            for tk, tv in traits_display.items():
                ck = canonical_trait_type_key(tk)
                traits_norm.setdefault(ck, tv)
            number = parse_number_from_nft_name(name)
            payload = {
                "nft_name": name,
                "collection_name": cname or "Collection",
                "traits_display": traits_display,
                "traits_normalized": traits_norm,
                "model": traits_norm.get("model"),
                "backdrop": traits_norm.get("backdrop"),
                "symbol": traits_norm.get("symbol"),
                "image_url": bundle.get("image_url"),
                "animation_url": bundle.get("animation_url"),
                "listing_price_ton": bundle.get("listing_price_ton"),
                "item_number": number,
            }
            return payload, trace

    return None, trace

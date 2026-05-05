from __future__ import annotations

import secrets
import time
from datetime import datetime
import json
from typing import Any, TypedDict

last_price_alert_check: datetime | None = None
last_smart_alert_check: datetime | None = None
last_digest_check: datetime | None = None
last_manual_payment_expiry_check: datetime | None = None
last_stuck_payment_alert_by_request: dict[int, datetime] = {}
last_smoke_test_result: dict | None = None
last_accuracy_digest_check: datetime | None = None

# user_id -> short_id -> (expires_at_unix, raw_input)
pending_gift_inputs: dict[int, dict[str, tuple[float, str]]] = {}

PENDING_GIFT_TTL_SECONDS = 900


def _prune_pending(user_id: int, now: float) -> None:
    bucket = pending_gift_inputs.get(user_id)
    if not bucket:
        return
    dead = [k for k, (exp, _) in bucket.items() if exp < now]
    for k in dead:
        del bucket[k]
    if not bucket:
        pending_gift_inputs.pop(user_id, None)


def pending_gift_put(user_id: int, raw_input: str, *, ttl_seconds: float | None = None) -> str:
    now = time.time()
    ttl = float(ttl_seconds if ttl_seconds is not None else PENDING_GIFT_TTL_SECONDS)
    _prune_pending(user_id, now)
    bucket = pending_gift_inputs.setdefault(user_id, {})
    sid = secrets.token_hex(3)
    while sid in bucket:
        sid = secrets.token_hex(3)
    bucket[sid] = (now + ttl, raw_input.strip())
    return sid


def pending_gift_get(user_id: int, short_id: str) -> str | None:
    now = time.time()
    _prune_pending(user_id, now)
    bucket = pending_gift_inputs.get(user_id)
    if not bucket:
        return None
    entry = bucket.get(short_id)
    if not entry:
        return None
    exp, raw = entry
    if exp < now:
        del bucket[short_id]
        return None
    return raw


def pending_gift_cancel(user_id: int, short_id: str) -> None:
    now = time.time()
    bucket = pending_gift_inputs.get(user_id)
    if not bucket:
        return
    bucket.pop(short_id, None)
    _prune_pending(user_id, now)


# user_id -> sid -> (expires_at_unix, full_report_text, nft_address or None, snapshot_json or None)
nft_check_sidebar: dict[int, dict[str, tuple[float, str, str | None, str | None]]] = {}
NFT_CHECK_SIDEBAR_TTL_SECONDS = 900


def _prune_nft_check_sidebar(user_id: int, now: float) -> None:
    bucket = nft_check_sidebar.get(user_id)
    if not bucket:
        return
    dead = [k for k, (exp, *_rest) in bucket.items() if exp < now]
    for k in dead:
        del bucket[k]
    if not bucket:
        nft_check_sidebar.pop(user_id, None)


def nft_check_sidebar_put(
    user_id: int,
    *,
    full_report: str,
    nft_address: str | None,
    snapshot: dict[str, Any] | None = None,
) -> str:
    now = time.time()
    _prune_nft_check_sidebar(user_id, now)
    bucket = nft_check_sidebar.setdefault(user_id, {})
    sid = secrets.token_hex(6)
    while sid in bucket:
        sid = secrets.token_hex(6)
    snap_json: str | None = None
    if snapshot:
        try:
            snap_json = json.dumps(snapshot, ensure_ascii=False)
        except Exception:
            snap_json = None
    bucket[sid] = (
        now + NFT_CHECK_SIDEBAR_TTL_SECONDS,
        full_report,
        (nft_address or "").strip() or None,
        snap_json,
    )
    return sid


def nft_check_sidebar_get(user_id: int, sid: str) -> tuple[str | None, str | None, dict[str, Any] | None]:
    now = time.time()
    _prune_nft_check_sidebar(user_id, now)
    bucket = nft_check_sidebar.get(user_id)
    if not bucket:
        return None, None, None
    entry = bucket.get(sid)
    if not entry:
        return None, None, None
    exp, full_text, addr, snap_json = entry
    if exp < now:
        del bucket[sid]
        _prune_nft_check_sidebar(user_id, now)
        return None, None, None
    snap: dict[str, Any] | None = None
    if snap_json:
        try:
            raw = json.loads(snap_json)
            snap = raw if isinstance(raw, dict) else None
        except Exception:
            snap = None
    return full_text, addr, snap


class NftActionSession(TypedDict, total=False):
    nft_address: str
    collection_address: str | None
    original_payload: str
    nft_name: str | None
    collection_name: str | None
    model: str | None
    backdrop: str | None
    symbol: str | None
    image_url: str | None
    animation_url: str | None
    sale_price_ton: float | None
    for_sale: bool
    market_resolve_payload: str | None
    getgems_web_preview: bool
    address_kind: str | None
    resolved_source: str | None
    traits: dict[str, str]


# user_id -> sid -> (expires_at_unix, payload)
nft_action_sessions: dict[int, dict[str, tuple[float, NftActionSession]]] = {}
NFT_ACTION_SESSION_TTL_SECONDS = 900


def _prune_nft_action_sessions(user_id: int, now: float) -> None:
    bucket = nft_action_sessions.get(user_id)
    if not bucket:
        return
    dead = [k for k, (exp, _) in bucket.items() if exp < now]
    for k in dead:
        del bucket[k]
    if not bucket:
        nft_action_sessions.pop(user_id, None)


def nft_action_session_put(
    user_id: int,
    *,
    nft_address: str,
    collection_address: str | None,
    original_payload: str,
    nft_name: str | None = None,
    collection_name: str | None = None,
    model: str | None = None,
    backdrop: str | None = None,
    symbol: str | None = None,
    image_url: str | None = None,
    animation_url: str | None = None,
    sale_price_ton: float | None = None,
    for_sale: bool = False,
    market_resolve_payload: str | None = None,
    getgems_web_preview: bool = False,
    address_kind: str | None = None,
    resolved_source: str | None = None,
    traits: dict[str, str] | None = None,
) -> str:
    now = time.time()
    _prune_nft_action_sessions(user_id, now)
    bucket = nft_action_sessions.setdefault(user_id, {})
    sid = secrets.token_hex(6)
    while sid in bucket:
        sid = secrets.token_hex(6)
    traits_clean: dict[str, str] | None = None
    if traits:
        traits_clean = {str(k): str(v) for k, v in traits.items() if str(v).strip()}
    elif model or backdrop or symbol:
        traits_clean = {}
        if model:
            traits_clean["model"] = str(model).strip()
        if backdrop:
            traits_clean["backdrop"] = str(backdrop).strip()
        if symbol:
            traits_clean["symbol"] = str(symbol).strip()
    payload: NftActionSession = {
        "nft_address": (nft_address or "").strip(),
        "collection_address": (collection_address or "").strip() or None,
        "original_payload": (original_payload or "").strip(),
        "nft_name": (nft_name or "").strip() or None,
        "collection_name": (collection_name or "").strip() or None,
        "model": (model or "").strip() or None,
        "backdrop": (backdrop or "").strip() or None,
        "symbol": (symbol or "").strip() or None,
        "image_url": (image_url or "").strip() or None,
        "animation_url": (animation_url or "").strip() or None,
        "sale_price_ton": float(sale_price_ton) if sale_price_ton is not None else None,
        "for_sale": bool(for_sale),
        "market_resolve_payload": (market_resolve_payload or "").strip() or None,
        "getgems_web_preview": bool(getgems_web_preview),
        "address_kind": (address_kind or "").strip() or None,
        "resolved_source": (resolved_source or "").strip() or None,
    }
    if traits_clean:
        payload["traits"] = traits_clean
    bucket[sid] = (now + NFT_ACTION_SESSION_TTL_SECONDS, payload)
    return sid


def nft_action_session_get(user_id: int, sid: str) -> NftActionSession | None:
    now = time.time()
    _prune_nft_action_sessions(user_id, now)
    bucket = nft_action_sessions.get(user_id)
    if not bucket:
        return None
    entry = bucket.get(sid)
    if not entry:
        return None
    exp, payload = entry
    if exp < now:
        del bucket[sid]
        _prune_nft_action_sessions(user_id, now)
        return None
    return payload


# user_id -> (expires_at_unix, nft_address)
pending_deal_inputs: dict[int, tuple[float, str]] = {}
PENDING_DEAL_TTL_SECONDS = 600


def pending_deal_put(user_id: int, *, nft_address: str, ttl_seconds: float | None = None) -> None:
    now = time.time()
    ttl = float(ttl_seconds if ttl_seconds is not None else PENDING_DEAL_TTL_SECONDS)
    pending_deal_inputs[user_id] = (now + ttl, (nft_address or "").strip())


def pending_deal_get(user_id: int) -> str | None:
    now = time.time()
    row = pending_deal_inputs.get(user_id)
    if not row:
        return None
    exp, addr = row
    if exp < now:
        pending_deal_inputs.pop(user_id, None)
        return None
    return addr.strip() or None


def pending_deal_clear(user_id: int) -> None:
    pending_deal_inputs.pop(user_id, None)

"""Добавление NFT в «Мой список» из callback (сессия превью или снимок /check)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.config import Settings
from app.db.repositories.gifts import GiftRepository
from app.services.feature_limits import check_usage_limit, get_plan_limits
from app.services.gift_intake import GiftIdentity, build_canonical_gift_key, normalize_gift_collection
from app.services.gift_resolver import enrich_identity_with_collection_registry, resolve_from_nft_address
from app.services.real_market_collection_scan import parse_number_from_nft_name


class MyListAddResult(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    LIMIT = "limit"
    INVALID = "invalid"


def stable_list_number_from_ref(nft_address: str) -> int:
    h = hashlib.sha256(nft_address.encode("utf-8")).digest()
    return 100_000_000 + (int.from_bytes(h[:4], "big") % 800_000_000)


def _traits_from_session(sp: dict[str, Any] | None) -> dict[str, str] | None:
    if not sp:
        return None
    traits = sp.get("traits")
    if isinstance(traits, dict) and traits:
        return {str(k): str(v) for k, v in traits.items() if str(v).strip()}
    out: dict[str, str] = {}
    for key in ("model", "backdrop", "symbol"):
        v = sp.get(key)
        if v:
            out[key] = str(v).strip()
    return out or None


def should_build_identity_from_session(sp: dict[str, Any] | None) -> bool:
    if not sp:
        return False
    addr = (sp.get("nft_address") or "").strip()
    coll = (sp.get("collection_name") or "").strip()
    name = (sp.get("nft_name") or "").strip()
    if not addr or not coll or not name:
        return False
    if (sp.get("address_kind") or "") == "getgems_gift_ref":
        return True
    if sp.get("getgems_web_preview"):
        return True
    return True


def snapshot_to_action_session(snapshot: dict[str, Any] | None, *, nft_address: str) -> dict[str, Any] | None:
    if not snapshot:
        return None
    addr = (nft_address or "").strip()
    if not addr:
        return None
    out: dict[str, Any] = dict(snapshot)
    out["nft_address"] = addr
    return out


def gift_identity_from_action_session(sp: dict[str, Any], settings: Settings) -> GiftIdentity:
    nft_address = (sp.get("nft_address") or "").strip()
    coll_name = (sp.get("collection_name") or "").strip() or "Unknown"
    nft_name = (sp.get("nft_name") or "").strip()
    caddr = (sp.get("collection_address") or "").strip() or None
    addr_kind = (sp.get("address_kind") or "").strip() or None
    src = (sp.get("resolved_source") or "").strip() or None

    norm = normalize_gift_collection(coll_name)
    num = parse_number_from_nft_name(nft_name) if nft_name else None
    if num is None:
        num = stable_list_number_from_ref(nft_address)

    canonical = build_canonical_gift_key(
        collection=norm,
        number=num,
        nft_address=nft_address,
        normalized_collection=norm,
    )
    meta_extra: dict[str, Any] = {}
    if addr_kind:
        meta_extra["address_kind"] = addr_kind
    if src:
        meta_extra["resolved_source"] = src
    tr = _traits_from_session(sp)
    if tr:
        meta_extra["traits"] = tr

    ident = GiftIdentity(
        collection=norm,
        number=num,
        nft_address=nft_address or None,
        collection_address=caddr,
        normalized_collection=norm,
        canonical_key=canonical,
        marketplace=src or None,
        confidence=82,
        warnings=[],
        metadata_extra=meta_extra or None,
    )
    return enrich_identity_with_collection_registry(settings, ident)


async def build_gift_identity_for_my_list_add(
    *,
    settings: Settings,
    nft_address: str,
    action_session: dict[str, Any] | None,
) -> GiftIdentity:
    if should_build_identity_from_session(action_session):
        return gift_identity_from_action_session(action_session or {}, settings)
    return await resolve_from_nft_address(settings, nft_address)


@dataclass
class MyListAddOutcome:
    result: MyListAddResult
    gift: Any | None = None
    max_gifts: int = 0
    current_count: int = 0
    display_name: str = ""
    collection_display: str = ""


def _attributes_json_from_session(sp: dict[str, Any] | None) -> str | None:
    tr = _traits_from_session(sp)
    if not tr:
        return None
    try:
        return json.dumps(tr, ensure_ascii=False)
    except Exception:
        return None


async def add_to_my_list(
    *,
    gift_repo: GiftRepository,
    user: Any,
    settings: Settings,
    nft_address: str,
    action_session: dict[str, Any] | None,
) -> MyListAddOutcome:
    addr = (nft_address or "").strip()
    if not addr:
        return MyListAddOutcome(MyListAddResult.INVALID)

    existing = await gift_repo.get_by_nft_address(user.id, addr)
    if existing is None:
        current_count = await gift_repo.count_by_user(user.id)
        allowed, max_allowed = check_usage_limit(user, "max_gifts", current_count)
        if not allowed:
            lim = get_plan_limits(user.plan)
            cap = int(lim.get("max_gifts", max_allowed))
            return MyListAddOutcome(MyListAddResult.LIMIT, None, cap, current_count, "", "")

    identity = await build_gift_identity_for_my_list_add(
        settings=settings,
        nft_address=addr,
        action_session=action_session,
    )
    gift, status = await gift_repo.add_or_update_gift_from_identity(user.id, identity)
    title = ((action_session or {}).get("nft_name") or "").strip() or None
    image_u = ((action_session or {}).get("image_url") or "").strip() or None
    attrs = _attributes_json_from_session(action_session)
    if title or image_u or attrs:
        await gift_repo.update_gift_visuals(
            user.id,
            gift.id,
            title=title,
            image_url=image_u,
            attributes_json=attrs,
        )
        gift = await gift_repo.get_by_id(user.id, gift.id)

    disp = ((action_session or {}).get("nft_name") or "").strip() or (getattr(gift, "title", None) or "").strip()
    if not disp:
        disp = f"{gift.collection} #{gift.number}"
    coll_disp = str(gift.collection)
    if status == "updated":
        return MyListAddOutcome(
            MyListAddResult.UPDATED, gift, 0, 0, display_name=disp, collection_display=coll_disp
        )
    return MyListAddOutcome(
        MyListAddResult.CREATED, gift, 0, 0, display_name=disp, collection_display=coll_disp
    )

from __future__ import annotations

import json
from typing import Any

from app.config import Settings
from app.services.gift_intake import (
    GiftIdentity,
    GiftInput,
    GiftInputType,
    build_canonical_gift_key,
    normalize_gift_collection,
    parse_gift_input,
)
from app.sources.collections import get_source_identifier, load_collection_registry, resolve_collection
from app.sources.http import MarketHTTPClient
from app.sources.tonapi import TonApiSource


def _find_canonical_by_collection_address(collection_address: str, registry: dict) -> str | None:
    target = (collection_address or "").strip()
    if not target:
        return None
    for canonical, payload in registry.items():
        addr = (payload.get("getgems") or {}).get("collection_address")
        if addr and str(addr).strip() == target:
            return canonical
    return None


def _nft_index(nft: dict) -> int | None:
    for key in ("index", "number"):
        raw = nft.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _collection_name_from_nft(nft: dict) -> str | None:
    block = nft.get("collection")
    if isinstance(block, dict):
        name = block.get("name") or block.get("metadata", {}).get("name")
        if name:
            return str(name)
    meta = nft.get("metadata")
    if isinstance(meta, dict):
        cn = meta.get("collection_name") or meta.get("collection")
        if isinstance(cn, str):
            return cn
    return None


def _collection_address_from_nft(nft: dict) -> str | None:
    block = nft.get("collection")
    if isinstance(block, dict):
        addr = block.get("address")
        if addr:
            return str(addr)
    return None


async def enrich_identity_with_tonapi(settings: Settings, identity: GiftIdentity) -> GiftIdentity:
    if not identity.nft_address:
        return identity
    source = TonApiSource(
        settings,
        http_client=MarketHTTPClient(
            timeout_seconds=settings.market_http_timeout_seconds,
            retries=settings.market_http_retries,
            user_agent=settings.market_http_user_agent,
        ),
    )
    nft = await source.get_nft_by_address(identity.nft_address)
    if not nft:
        identity.warnings.append("TonAPI: не удалось загрузить NFT по address.")
        identity.confidence = min(identity.confidence, 45)
        return identity

    cname = _collection_name_from_nft(nft)
    idx = _nft_index(nft)
    caddr = _collection_address_from_nft(nft)
    if cname:
        identity.collection = normalize_gift_collection(cname)
    if idx is not None:
        identity.number = idx
    if caddr:
        identity.collection_address = caddr
    identity.normalized_collection = normalize_gift_collection(identity.collection or cname or "")
    identity.canonical_key = build_canonical_gift_key(
        collection=identity.collection,
        number=identity.number,
        nft_address=identity.nft_address,
        normalized_collection=identity.normalized_collection or None,
    )
    identity.confidence = min(100, identity.confidence + 10)
    return identity


def enrich_identity_with_collection_registry(settings: Settings, identity: GiftIdentity) -> GiftIdentity:
    registry = load_collection_registry(settings.collection_registry_path)
    if identity.collection_address and not identity.collection:
        guess = _find_canonical_by_collection_address(identity.collection_address, registry)
        if guess:
            identity.collection = guess
            identity.warnings.append("Коллекция восстановлена из registry по collection address из ссылки.")
    col = identity.collection
    if not col:
        return identity
    canonical, payload = resolve_collection(col, registry=registry)
    if canonical:
        identity.collection = canonical
        identity.normalized_collection = normalize_gift_collection(canonical)
    elif payload is None:
        identity.warnings.append("Коллекция не найдена в registry — анализ может быть менее точным.")
        identity.confidence = min(identity.confidence, 55)
    if not identity.collection_address and canonical:
        addr = get_source_identifier(canonical, "getgems", "collection_address", registry=registry)
        if addr:
            identity.collection_address = addr
    identity.canonical_key = build_canonical_gift_key(
        collection=identity.collection,
        number=identity.number,
        nft_address=identity.nft_address,
        normalized_collection=identity.normalized_collection or normalize_gift_collection(identity.collection),
    )
    return identity


async def resolve_from_collection_number(
    settings: Settings, collection: str, number: int, base_warnings: list[str] | None = None
) -> GiftIdentity:
    warnings = list(base_warnings or [])
    norm = normalize_gift_collection(collection)
    ident = GiftIdentity(
        collection=norm,
        number=number,
        nft_address=None,
        collection_address=None,
        normalized_collection=norm,
        canonical_key=build_canonical_gift_key(collection=norm, number=number, nft_address=None, normalized_collection=norm),
        confidence=75,
        warnings=warnings,
    )
    return enrich_identity_with_collection_registry(settings, ident)


async def resolve_from_nft_address(settings: Settings, address: str) -> GiftIdentity:
    ident = GiftIdentity(
        collection="Unknown",
        number=None,
        nft_address=address,
        collection_address=None,
        normalized_collection="",
        canonical_key=build_canonical_gift_key(collection=None, number=None, nft_address=address, normalized_collection=""),
        confidence=60,
        warnings=[],
    )
    ident = await enrich_identity_with_tonapi(settings, ident)
    ident = enrich_identity_with_collection_registry(settings, ident)
    if ident.collection == "Unknown" and ident.nft_address:
        ident.collection = ident.normalized_collection or "Unknown"
    return ident


async def resolve_from_url(settings: Settings, gi: GiftInput) -> GiftIdentity:
    warnings = list(gi.parse_warnings)
    ident = GiftIdentity(
        collection=gi.collection or "Unknown",
        number=gi.number,
        nft_address=gi.nft_address,
        collection_address=gi.collection_address,
        normalized_collection=normalize_gift_collection(gi.collection) if gi.collection else "",
        canonical_key="",
        source_url=gi.source_url,
        marketplace=gi.marketplace,
        confidence=55 if gi.input_type == GiftInputType.unknown else 65,
        warnings=warnings,
    )
    if ident.nft_address:
        ident = await enrich_identity_with_tonapi(settings, ident)
    ident = enrich_identity_with_collection_registry(settings, ident)
    if not ident.canonical_key:
        ident.canonical_key = build_canonical_gift_key(
            collection=ident.collection if ident.collection != "Unknown" else None,
            number=ident.number,
            nft_address=ident.nft_address,
            normalized_collection=ident.normalized_collection or None,
        )
    return ident


async def resolve_gift_identity(
    user: object,
    raw_input: str,
    settings: Settings,
) -> tuple[GiftInput, GiftIdentity]:
    _ = user
    gi = parse_gift_input(raw_input.strip())
    if gi.input_type == GiftInputType.collection_number and gi.collection is not None and gi.number is not None:
        ident = await resolve_from_collection_number(settings, gi.collection, gi.number, gi.parse_warnings)
        return gi, ident
    if gi.input_type == GiftInputType.nft_address and gi.nft_address:
        ident = await resolve_from_nft_address(settings, gi.nft_address)
        ident.warnings.extend(gi.parse_warnings)
        return gi, ident
    if gi.input_type in (
        GiftInputType.marketplace_url,
        GiftInputType.telegram_gift_url,
        GiftInputType.getgems_startapp,
    ):
        ident = await resolve_from_url(settings, gi)
        return gi, ident
    # unknown or unresolved url
    ident = GiftIdentity(
        collection=gi.collection or "Unknown",
        number=gi.number,
        nft_address=gi.nft_address,
        collection_address=gi.collection_address,
        normalized_collection=normalize_gift_collection(gi.collection) if gi.collection else "",
        canonical_key="",
        source_url=gi.source_url,
        marketplace=gi.marketplace,
        confidence=25,
        warnings=list(gi.parse_warnings),
    )
    if ident.nft_address:
        ident = await enrich_identity_with_tonapi(settings, ident)
        ident = enrich_identity_with_collection_registry(settings, ident)
    elif ident.collection and ident.collection != "Unknown" and ident.number is not None:
        ident = await resolve_from_collection_number(settings, ident.collection, ident.number, ident.warnings)
    ident.canonical_key = build_canonical_gift_key(
        collection=ident.collection if ident.collection != "Unknown" else None,
        number=ident.number,
        nft_address=ident.nft_address,
        normalized_collection=ident.normalized_collection or None,
    )
    return gi, ident


def format_resolved_gift_card(identity: GiftIdentity) -> str:
    lines = [
        "🪪 Gift",
        f"Коллекция: {identity.collection}",
        f"Номер: {('#' + str(identity.number)) if identity.number is not None else '—'}",
        f"NFT address: {identity.nft_address or '—'}",
        f"Canonical: {identity.canonical_key}",
        f"Уверенность: {identity.confidence}/100",
    ]
    if identity.marketplace:
        lines.append(f"Источник ссылки: {identity.marketplace}")
    if identity.warnings:
        lines.append("Предупреждения:\n- " + "\n- ".join(identity.warnings))
    return "\n".join(lines)


def identity_metadata_blob(identity: GiftIdentity) -> str | None:
    payload: dict[str, Any] = {
        "canonical_key": identity.canonical_key,
        "marketplace": identity.marketplace,
        "source_url": identity.source_url,
        "confidence": identity.confidence,
    }
    extra = getattr(identity, "metadata_extra", None)
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is not None:
                payload[k] = v
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return None

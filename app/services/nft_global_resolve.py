"""Разрешение «коллекция #номер» через локальный индекс + live TonAPI verify."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories import nft_global_index_repo as repo
from app.services.nft_name_index import (
    extract_base_name_from_nft_name,
    extract_item_number_from_name,
    normalize_nft_text,
)
from app.services.nft_tonapi_image import extract_nft_media_urls
from app.services.real_market_collection_scan import (
    TargetNftInfo,
    parse_number_from_nft_name,
    resolve_target_nft_from_collection_number,
    target_from_nft_payload,
)
from app.services.tonapi_collection_client import TonAPICollectionClient

logger = logging.getLogger(__name__)


def is_paid_user_plan(plan: str | None) -> bool:
    return (plan or "free").strip().lower() in {"pro", "trader", "sniper"}


def message_unknown_collection_free(display_name: str) -> str:
    name = display_name.strip()
    return (
        f"❌ Не нашёл NFT «{name}».\n\n"
        "Пришли ссылку на конкретный NFT или NFT address — я точно определю его и запомню."
    )


def message_unknown_collection_paid(display_name: str) -> str:
    name = display_name.strip()
    return (
        f"❌ Пока не нашёл NFT «{name}».\n\n"
        "Я запустил расширенный поиск по NFT-индексу. "
        "Чтобы проверить сразу — пришли ссылку на конкретный NFT или NFT address."
    )


async def try_resolve_via_global_index(
    session: AsyncSession,
    settings: Settings,
    client: TonAPICollectionClient,
    *,
    display_collection: str,
    number: int,
) -> tuple[TargetNftInfo | None, str | None]:
    """
    Локальный индекс → live verify TonAPI get_nft / короткий scan.
    (None, None) — продолжить обычный resolve (registry + TonAPI listing).
    (None, str) — стоп с сообщением пользователю.
    """
    if not getattr(settings, "nft_global_index_enabled", False):
        return None, None

    base_norm = normalize_nft_text(display_collection)
    if not base_norm:
        return None, None

    hits = await repo.find_items_by_base_and_number(session, base_norm, int(number))
    addrs = list({h.nft_address for h in hits if h.nft_address})
    verified_items: list[TargetNftInfo] = []
    for addr in addrs[:15]:
        nft = await client.get_nft(addr)
        if not nft:
            continue
        tgt = target_from_nft_payload(nft, ipfs_gateway_url=settings.ipfs_gateway_url)
        if not tgt:
            continue
        meta = nft.get("metadata") if isinstance(nft.get("metadata"), dict) else {}
        iname = str(meta.get("name") or "").strip()
        nmeta = extract_item_number_from_name(iname) or parse_number_from_nft_name(iname)
        if nmeta is not None and int(nmeta) != int(number):
            continue
        verified_items.append(tgt)
    if len(verified_items) == 1:
        return verified_items[0], None
    if len(verified_items) > 1:
        disp = display_collection.strip()
        return None, (
            f"⚠️ Нашёл несколько коллекций для «{disp}».\n\n"
            "Пришли ссылку на NFT или NFT address."
        )

    aliases = await repo.find_aliases_by_normalized(session, base_norm)
    seen: set[str] = set()
    coll_addrs: list[str] = []
    for a in aliases:
        if a.collection_address in seen:
            continue
        seen.add(a.collection_address)
        coll_addrs.append(a.collection_address)

    found: list[TargetNftInfo] = []
    for caddr in coll_addrs[:15]:
        tgt = await resolve_target_nft_from_collection_number(
            client,
            settings,
            caddr,
            display_collection.strip(),
            int(number),
            max_pages=12,
        )
        if tgt:
            found.append(tgt)
    if len(found) == 1:
        return found[0], None
    if len(found) > 1:
        disp = display_collection.strip()
        return None, (
            f"⚠️ Нашёл несколько коллекций для «{disp}».\n\n"
            "Пришли ссылку на NFT или NFT address."
        )

    crows = await repo.find_collection_by_name_normalized(session, base_norm)
    if len(crows) == 1:
        caddr = crows[0].collection_address
        dname = (crows[0].collection_name or display_collection).strip() or "NFT"
        tgt = await resolve_target_nft_from_collection_number(
            client, settings, caddr, dname, int(number), max_pages=12
        )
        if tgt:
            return tgt, None

    return None, None


async def enqueue_live_discovery(session: AsyncSession, settings: Settings, *, collection_hint: str | None) -> None:
    if not getattr(settings, "nft_global_index_enabled", False):
        return
    try:
        await repo.enqueue_index_job(
            session,
            job_type="sync_collections",
            collection_address=None,
            status="pending",
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.debug("enqueue_live_discovery skipped")


async def learn_from_successful_nft_check(
    session: AsyncSession,
    settings: Settings,
    target: TargetNftInfo,
    *,
    nft_raw: dict[str, Any] | None = None,
) -> None:
    """После успешного /check: коллекция, алиас, item в индексе."""
    if not getattr(settings, "nft_global_index_enabled", False):
        return
    try:
        caddr = (target.collection_address or "").strip()
        if not caddr:
            return
        cnorm = normalize_nft_text(target.collection_name or "")
        await repo.upsert_collection(
            session,
            collection_address=caddr,
            collection_name=target.collection_name,
            collection_name_normalized=cnorm or None,
            owner_address=None,
            next_item_index=None,
            source="tonapi",
            index_status="metadata_indexed",
        )
        if cnorm:
            await repo.upsert_alias(
                session,
                alias_normalized=cnorm,
                display_name=(target.collection_name or caddr)[:255],
                collection_address=caddr,
                source="learned_from_check",
                confidence="high",
            )
        base = extract_base_name_from_nft_name(target.name)
        bn = normalize_nft_text(base) if base else None
        if bn:
            await repo.upsert_alias(
                session,
                alias_normalized=bn,
                display_name=(base or bn)[:255],
                collection_address=caddr,
                source="learned_from_check",
                confidence="high",
            )
        img = None
        if nft_raw and isinstance(nft_raw, dict):
            img, _ = extract_nft_media_urls(nft_raw, ipfs_gateway_url=settings.ipfs_gateway_url)
        elif target.image_url:
            img = target.image_url
        num = target.number
        if num is None:
            num = extract_item_number_from_name(target.name) or parse_number_from_nft_name(target.name)
        addr = (target.address or "").strip()
        if addr:
            await repo.upsert_item(
                session,
                nft_address=addr,
                collection_address=caddr,
                item_index=None,
                item_number=int(num) if num is not None else None,
                item_name=target.name,
                item_name_normalized=normalize_nft_text(target.name),
                base_name=base,
                base_name_normalized=bn,
                image_url=img,
            )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("learn_from_successful_nft_check failed", exc_info=False)

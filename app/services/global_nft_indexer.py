"""Фоновая синхронизация глобального индекса NFT (TonAPI), без блокировки /check."""

from __future__ import annotations

import asyncio
import logging
import random
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.config import Settings
from app.db.models import NftCollectionsIndex
from app.db.repositories import nft_global_index_repo as repo
from app.db.session import SessionLocal
from app.services.nft_collection_resolve import display_name_from_tonapi_collection
from app.services.nft_name_index import (
    extract_base_name_from_nft_name,
    extract_item_number_from_name,
    normalize_nft_text,
)
from app.services.nft_tonapi_image import extract_nft_media_urls
from app.services.real_market_collection_scan import normalize_traits_from_nft_item, parse_number_from_nft_name
from app.services.tonapi_collection_client import TonAPICollectionClient

logger = logging.getLogger(__name__)


def _owner_from_collection(coll: dict[str, Any]) -> str | None:
    own = coll.get("owner")
    if isinstance(own, dict) and own.get("address"):
        return str(own["address"]).strip() or None
    return None


def _next_item_index(coll: dict[str, Any]) -> int | None:
    for key in ("next_item_index", "items_count"):
        raw = coll.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


async def sync_all_nft_collections(
    settings: Settings,
    *,
    limit_per_page: int | None = None,
    max_collections: int | None = None,
    sleep_ms: int | None = None,
) -> dict[str, Any]:
    """Пагинация TonAPI /v2/nfts/collections → nft_collections_index."""
    if not getattr(settings, "nft_global_index_enabled", False):
        return {"skipped": True, "reason": "NFT_GLOBAL_INDEX_ENABLED=false"}
    client = TonAPICollectionClient(settings)
    if not client.configured:
        return {"skipped": True, "reason": "tonapi_not_configured"}

    lim = int(limit_per_page or settings.nft_global_index_limit_per_page)
    lim = max(1, min(lim, 1000))
    sleep_s = max(0.0, float(sleep_ms if sleep_ms is not None else settings.nft_global_index_request_sleep_ms) / 1000.0)
    backoff = max(1.0, float(settings.nft_global_index_429_backoff_seconds))
    max_run = int(settings.nft_global_index_max_collections_per_run or 0)

    offset = 0
    total = 0
    pages = 0
    errors = 0
    t0 = asyncio.get_event_loop().time()

    while True:
        if max_collections is not None and total >= int(max_collections):
            break
        if max_run > 0 and total >= max_run:
            break

        cols, status, _ = await client.fetch_nft_collections_page(limit=lim, offset=offset)
        pages += 1
        if status == 429:
            wait_s = max(backoff, random.uniform(10.0, 30.0))
            logger.warning("nft index sync 429 at offset=%s, backing off %.1fs", offset, wait_s)
            await asyncio.sleep(wait_s)
            errors += 1
            continue
        if status != 200:
            logger.warning("nft index sync bad status=%s offset=%s", status, offset)
            errors += 1
            break
        if not cols:
            break

        async with SessionLocal() as session:
            try:
                for coll in cols:
                    addr = str(coll.get("address") or "").strip()
                    if not addr:
                        continue
                    dname = display_name_from_tonapi_collection(coll) or None
                    dnorm = normalize_nft_text(dname) if dname else None
                    await repo.upsert_collection(
                        session,
                        collection_address=addr,
                        collection_name=dname,
                        collection_name_normalized=dnorm,
                        owner_address=_owner_from_collection(coll),
                        next_item_index=_next_item_index(coll),
                        source=getattr(settings, "nft_global_index_provider", "tonapi") or "tonapi",
                        index_status="metadata_indexed",
                    )
                    if dnorm:
                        await repo.upsert_alias(
                            session,
                            alias_normalized=dnorm,
                            display_name=(dname or addr)[:255],
                            collection_address=addr,
                            source="collection_name",
                            confidence="high",
                        )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("nft index sync batch commit failed offset=%s", offset)
                errors += 1
                break

        batch_len = len(cols)
        offset += batch_len
        total += batch_len
        logger.info(
            "nft index sync collections progress offset=%s batch=%s total=%s pages=%s errors=%s",
            offset,
            batch_len,
            total,
            pages,
            errors,
        )
        if batch_len < lim:
            break
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

    elapsed = asyncio.get_event_loop().time() - t0
    logger.info(
        "nft index sync collections done total=%s offset_final=%s errors=%s elapsed=%.2fs",
        total,
        offset,
        errors,
        elapsed,
    )
    return {"collections_upserted": total, "offset": offset, "errors": errors, "elapsed_sec": elapsed}


async def sample_collection_aliases(
    settings: Settings,
    collection_address: str,
    *,
    sample_items: int | None = None,
) -> dict[str, Any]:
    """Первые N NFT коллекции → алиасы base_name."""
    client = TonAPICollectionClient(settings)
    if not client.configured:
        return {"skipped": True}
    n = max(1, int(sample_items or settings.nft_global_index_sample_items))
    items, status, _, _ = await client.fetch_collection_items_page_raw(
        collection_address, limit=min(n, 1000), offset=0
    )
    if status != 200:
        return {"error": f"http_{status}"}

    bases: list[str] = []
    async with SessionLocal() as session:
        try:
            for it in items[:n]:
                meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                iname = str(meta.get("name") or it.get("name") or "").strip()
                if not iname:
                    continue
                base = extract_base_name_from_nft_name(iname)
                if not base:
                    continue
                bn = normalize_nft_text(base)
                if not bn:
                    continue
                bases.append(bn)
                num = extract_item_number_from_name(iname) or parse_number_from_nft_name(iname)
                iaddr = str(it.get("address") or "").strip()
                coll = str(collection_address).strip()
                idx_raw = it.get("index")
                try:
                    iidx = int(idx_raw) if idx_raw is not None else None
                except (TypeError, ValueError):
                    iidx = None
                img, _ = extract_nft_media_urls(it, ipfs_gateway_url=settings.ipfs_gateway_url)
                if iaddr:
                    await repo.upsert_item(
                        session,
                        nft_address=iaddr,
                        collection_address=coll,
                        item_index=iidx,
                        item_number=int(num) if num is not None else None,
                        item_name=iname,
                        item_name_normalized=normalize_nft_text(iname),
                        base_name=base,
                        base_name_normalized=bn,
                        image_url=img,
                    )
            cnt = Counter(bases)
            for bnorm, c in cnt.items():
                conf = "high" if c >= 2 else "medium"
                await repo.upsert_alias(
                    session,
                    alias_normalized=bnorm,
                    display_name=bnorm[:255],
                    collection_address=collection_address.strip(),
                    source="item_base_name",
                    confidence=conf,
                )
            await repo.update_collection_index_state(
                session,
                collection_address.strip(),
                index_status="aliases_sampled",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("sample_collection_aliases failed for %s", collection_address[:20])
            return {"error": "commit_failed"}
    return {"sampled": len(items), "unique_bases": len(set(bases))}


async def index_collection_items(
    settings: Settings,
    collection_address: str,
    *,
    limit_per_page: int | None = None,
    max_items: int | None = None,
    resume: bool = True,
    sleep_ms: int | None = None,
) -> dict[str, Any]:
    """Полная (или частичная) индексация items коллекции с resume по last_index_offset."""
    if not getattr(settings, "nft_global_index_full_items_enabled", False):
        return {"skipped": True, "reason": "NFT_GLOBAL_INDEX_FULL_ITEMS_ENABLED=false"}
    client = TonAPICollectionClient(settings)
    if not client.configured:
        return {"skipped": True}

    lim = max(1, min(int(limit_per_page or settings.nft_global_index_limit_per_page), 1000))
    sleep_s = max(0.0, float(sleep_ms if sleep_ms is not None else settings.nft_global_index_request_sleep_ms) / 1000.0)
    backoff = max(1.0, float(settings.nft_global_index_429_backoff_seconds))

    async with SessionLocal() as session:
        row = await repo.get_collection_row(session, collection_address)
        start_offset = int(row.last_index_offset or 0) if resume and row else 0
        cap_total = int(row.next_item_index) if row and row.next_item_index is not None else None
        base_items_count = int(row.items_indexed_count or 0) if row else 0

    offset = start_offset
    indexed = 0
    errors = 0

    while True:
        if max_items is not None and int(max_items) > 0 and indexed >= int(max_items):
            break
        if cap_total is not None and offset >= cap_total:
            break
        items, status, _, _root = await client.fetch_collection_items_page_raw(
            collection_address, limit=lim, offset=offset
        )
        if status == 429:
            wait_s = max(backoff, random.uniform(10.0, 30.0))
            await asyncio.sleep(wait_s)
            errors += 1
            continue
        if status != 200:
            errors += 1
            break
        if not items:
            break

        async with SessionLocal() as session:
            try:
                for it in items:
                    meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                    iname = str(meta.get("name") or it.get("name") or "").strip()
                    iaddr = str(it.get("address") or "").strip()
                    if not iaddr:
                        continue
                    traits = normalize_traits_from_nft_item(it)
                    _ = traits
                    base = extract_base_name_from_nft_name(iname) if iname else None
                    bn = normalize_nft_text(base) if base else None
                    num = extract_item_number_from_name(iname) if iname else None
                    if num is None:
                        num = parse_number_from_nft_name(iname)
                    idx_raw = it.get("index")
                    try:
                        iidx = int(idx_raw) if idx_raw is not None else None
                    except (TypeError, ValueError):
                        iidx = None
                    img, _ = extract_nft_media_urls(it, ipfs_gateway_url=settings.ipfs_gateway_url)
                    await repo.upsert_item(
                        session,
                        nft_address=iaddr,
                        collection_address=collection_address.strip(),
                        item_index=iidx,
                        item_number=int(num) if num is not None else None,
                        item_name=iname or None,
                        item_name_normalized=normalize_nft_text(iname) if iname else None,
                        base_name=base,
                        base_name_normalized=bn,
                        image_url=img,
                    )
                    if bn:
                        await repo.upsert_alias(
                            session,
                            alias_normalized=bn,
                            display_name=(base or bn)[:255],
                            collection_address=collection_address.strip(),
                            source="item_base_name",
                            confidence="medium",
                        )
                new_off = offset + len(items)
                await repo.update_collection_index_state(
                    session,
                    collection_address.strip(),
                    index_status="items_indexing",
                    items_indexed_count=base_items_count + indexed + len(items),
                    last_index_offset=new_off,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("index_collection_items batch failed offset=%s", offset)
                errors += 1
                break

        batch = len(items)
        offset += batch
        indexed += batch
        if max_items is not None and int(max_items) > 0 and indexed >= int(max_items):
            break
        if batch < lim:
            async with SessionLocal() as session:
                await repo.update_collection_index_state(
                    session,
                    collection_address.strip(),
                    index_status="items_indexed",
                    last_index_offset=offset,
                )
                await session.commit()
            break
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

    return {"indexed": indexed, "last_offset": offset, "errors": errors}


async def sample_all_collection_aliases(
    settings: Settings,
    *,
    sample_items: int | None = None,
    max_collections: int | None = None,
    only_new: bool = True,
    sleep_ms: int | None = None,
) -> dict[str, Any]:
    """Проход по коллекциям в БД и sample aliases для каждой."""
    if not getattr(settings, "nft_global_index_enabled", False):
        return {"skipped": True}
    cap = int(max_collections or 0)
    processed = 0
    errors = 0
    async with SessionLocal() as session:
        q = select(NftCollectionsIndex.collection_address)
        if only_new:
            q = q.where(NftCollectionsIndex.index_status.in_(("new", "metadata_indexed")))
        if cap > 0:
            q = q.limit(cap)
        else:
            q = q.limit(5000)
        rows = list((await session.execute(q)).scalars().all())
    for addr in rows:
        if not addr:
            continue
        r = await sample_collection_aliases(settings, addr, sample_items=sample_items)
        if r.get("error"):
            errors += 1
        processed += 1
        if sleep_ms and sleep_ms > 0:
            await asyncio.sleep(float(sleep_ms) / 1000.0)
    return {"collections": processed, "errors": errors}

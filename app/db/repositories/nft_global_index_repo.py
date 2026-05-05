"""CRUD для глобального индекса NFT (TonAPI / check learn)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NftCollectionAliases, NftCollectionsIndex, NftIndexJobs, NftItemsIndex


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def upsert_collection(
    session: AsyncSession,
    *,
    collection_address: str,
    collection_name: str | None,
    collection_name_normalized: str | None,
    owner_address: str | None,
    next_item_index: int | None,
    source: str = "tonapi",
    index_status: str = "metadata_indexed",
) -> None:
    now = _utcnow()
    row = {
        "collection_address": collection_address.strip(),
        "collection_name": collection_name,
        "collection_name_normalized": collection_name_normalized,
        "owner_address": owner_address,
        "next_item_index": next_item_index,
        "source": source,
        "index_status": index_status,
        "last_seen_at": now,
        "updated_at": now,
        "indexed_at": now,
    }
    stmt = insert(NftCollectionsIndex).values(created_at=now, **row)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_nft_collections_index_address",
        set_={
            "collection_name": stmt.excluded.collection_name,
            "collection_name_normalized": stmt.excluded.collection_name_normalized,
            "owner_address": stmt.excluded.owner_address,
            "next_item_index": stmt.excluded.next_item_index,
            "source": stmt.excluded.source,
            "index_status": stmt.excluded.index_status,
            "last_seen_at": stmt.excluded.last_seen_at,
            "updated_at": stmt.excluded.updated_at,
            "indexed_at": stmt.excluded.indexed_at,
        },
    )
    await session.execute(stmt)


async def upsert_alias(
    session: AsyncSession,
    *,
    alias_normalized: str,
    display_name: str,
    collection_address: str,
    source: str,
    confidence: str = "medium",
) -> None:
    now = _utcnow()
    stmt = insert(NftCollectionAliases).values(
        alias_normalized=alias_normalized[:255],
        display_name=display_name[:255],
        collection_address=collection_address.strip(),
        source=source,
        confidence=confidence,
        seen_count=1,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_nft_alias_norm_coll",
        set_={
            "display_name": stmt.excluded.display_name,
            "source": stmt.excluded.source,
            "confidence": stmt.excluded.confidence,
            "seen_count": NftCollectionAliases.seen_count + 1,  # type: ignore[arg-type]
            "last_seen_at": stmt.excluded.last_seen_at,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)


async def upsert_item(
    session: AsyncSession,
    *,
    nft_address: str,
    collection_address: str,
    item_index: int | None,
    item_number: int | None,
    item_name: str | None,
    item_name_normalized: str | None,
    base_name: str | None,
    base_name_normalized: str | None,
    image_url: str | None = None,
) -> None:
    now = _utcnow()
    stmt = insert(NftItemsIndex).values(
        nft_address=nft_address.strip(),
        collection_address=collection_address.strip(),
        item_index=item_index,
        item_number=item_number,
        item_name=item_name,
        item_name_normalized=item_name_normalized,
        base_name=base_name,
        base_name_normalized=base_name_normalized,
        image_url=image_url,
        indexed_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_nft_items_index_address",
        set_={
            "collection_address": stmt.excluded.collection_address,
            "item_index": stmt.excluded.item_index,
            "item_number": stmt.excluded.item_number,
            "item_name": stmt.excluded.item_name,
            "item_name_normalized": stmt.excluded.item_name_normalized,
            "base_name": stmt.excluded.base_name,
            "base_name_normalized": stmt.excluded.base_name_normalized,
            "image_url": stmt.excluded.image_url,
            "indexed_at": stmt.excluded.indexed_at,
            "last_seen_at": stmt.excluded.last_seen_at,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)


async def find_items_by_base_and_number(
    session: AsyncSession,
    base_name_normalized: str,
    item_number: int,
) -> Sequence[NftItemsIndex]:
    q = (
        select(NftItemsIndex)
        .where(
            NftItemsIndex.base_name_normalized == base_name_normalized,
            NftItemsIndex.item_number == int(item_number),
        )
        .limit(25)
    )
    r = await session.execute(q)
    return r.scalars().all()


async def find_aliases_by_normalized(
    session: AsyncSession, alias_normalized: str
) -> Sequence[NftCollectionAliases]:
    q = (
        select(NftCollectionAliases)
        .where(NftCollectionAliases.alias_normalized == alias_normalized[:255])
        .order_by(
            NftCollectionAliases.confidence.desc(),
            NftCollectionAliases.seen_count.desc(),
        )
        .limit(50)
    )
    r = await session.execute(q)
    return r.scalars().all()


async def find_collection_by_name_normalized(
    session: AsyncSession, name_normalized: str
) -> Sequence[NftCollectionsIndex]:
    q = (
        select(NftCollectionsIndex)
        .where(NftCollectionsIndex.collection_name_normalized == name_normalized)
        .limit(20)
    )
    r = await session.execute(q)
    return r.scalars().all()


async def update_collection_index_state(
    session: AsyncSession,
    collection_address: str,
    *,
    index_status: str | None = None,
    items_indexed_count: int | None = None,
    last_index_offset: int | None = None,
    last_error: str | None = None,
) -> None:
    vals: dict[str, Any] = {"updated_at": _utcnow()}
    if index_status is not None:
        vals["index_status"] = index_status
    if items_indexed_count is not None:
        vals["items_indexed_count"] = items_indexed_count
    if last_index_offset is not None:
        vals["last_index_offset"] = last_index_offset
    if last_error is not None:
        vals["last_error"] = last_error[:8000] if last_error else None
    await session.execute(
        update(NftCollectionsIndex).where(NftCollectionsIndex.collection_address == collection_address).values(**vals)
    )


async def get_collection_row(
    session: AsyncSession, collection_address: str
) -> NftCollectionsIndex | None:
    q = select(NftCollectionsIndex).where(NftCollectionsIndex.collection_address == collection_address.strip()).limit(1)
    r = await session.execute(q)
    return r.scalars().first()


async def enqueue_index_job(
    session: AsyncSession,
    *,
    job_type: str,
    collection_address: str | None = None,
    offset_value: int = 0,
    limit_value: int = 1000,
    status: str = "pending",
) -> None:
    now = _utcnow()
    stmt = insert(NftIndexJobs).values(
        job_type=job_type,
        status=status,
        collection_address=collection_address,
        offset_value=offset_value,
        limit_value=limit_value,
        created_at=now,
        updated_at=now,
    )
    await session.execute(stmt)


async def count_collections(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(NftCollectionsIndex))
    return int(r.scalar_one())


async def count_aliases(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(NftCollectionAliases))
    return int(r.scalar_one())


async def count_items(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(NftItemsIndex))
    return int(r.scalar_one())


async def count_failed_jobs(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(NftIndexJobs).where(NftIndexJobs.status == "failed"))
    return int(r.scalar_one())


async def max_collection_indexed_at(session: AsyncSession) -> dt.datetime | None:
    r = await session.execute(select(func.max(NftCollectionsIndex.indexed_at)))
    return r.scalar_one()

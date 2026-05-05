from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Gift, User
from app.services.feature_limits import normalize_plan_for_limits
from app.services.gift_intake import GiftIdentity, normalize_gift_collection
from app.services.gift_resolver import identity_metadata_blob


class GiftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_gift(self, user_id: int, collection: str, number: int, title: str | None = None) -> Gift:
        gift = Gift(
            user_id=user_id,
            collection=collection,
            number=number,
            title=title,
            created_at=datetime.utcnow(),
            signals_enabled=False,
        )
        self.session.add(gift)
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def list_by_user(self, user_id: int) -> list[Gift]:
        stmt = select(Gift).where(Gift.user_id == user_id).order_by(Gift.created_at.desc())
        return list((await self.session.scalars(stmt)).all())

    async def count_by_user(self, user_id: int) -> int:
        stmt = select(func.count(Gift.id)).where(Gift.user_id == user_id)
        return int(await self.session.scalar(stmt) or 0)

    async def get_by_id(self, user_id: int, gift_id: int) -> Gift | None:
        stmt = select(Gift).where(Gift.user_id == user_id, Gift.id == gift_id)
        return await self.session.scalar(stmt)

    async def get_by_canonical_key(self, user_id: int, canonical_key: str) -> Gift | None:
        if not canonical_key:
            return None
        stmt = select(Gift).where(Gift.user_id == user_id, Gift.canonical_key == canonical_key)
        return await self.session.scalar(stmt)

    async def get_by_nft_address(self, user_id: int, nft_address: str) -> Gift | None:
        if not nft_address:
            return None
        stmt = select(Gift).where(Gift.user_id == user_id, Gift.nft_address == nft_address)
        return await self.session.scalar(stmt)

    async def get_by_collection_number(self, user_id: int, collection: str, number: int) -> Gift | None:
        stmt = select(Gift).where(Gift.user_id == user_id, Gift.collection == collection, Gift.number == number)
        return await self.session.scalar(stmt)

    def _apply_identity(self, gift: Gift, identity: GiftIdentity, meta: str | None) -> None:
        now = datetime.utcnow()
        gift.collection = identity.collection
        if identity.number is not None:
            gift.number = identity.number
        gift.nft_address = identity.nft_address
        gift.collection_address = identity.collection_address
        gift.source_url = identity.source_url
        gift.marketplace = identity.marketplace
        gift.canonical_key = identity.canonical_key
        gift.normalized_collection = identity.normalized_collection or normalize_gift_collection(identity.collection)
        gift.identity_confidence = identity.confidence
        gift.last_resolved_at = now
        if meta:
            gift.metadata_json = meta

    async def update_gift_identity(self, user_id: int, gift_id: int, identity: GiftIdentity) -> Gift | None:
        gift = await self.get_by_id(user_id, gift_id)
        if gift is None:
            return None
        self._apply_identity(gift, identity, identity_metadata_blob(identity))
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def add_or_update_gift_from_identity(
        self,
        user_id: int,
        identity: GiftIdentity,
        purchase_price_ton: float | None = None,
        target_price_ton: float | None = None,
    ) -> tuple[Gift, str]:
        meta = identity_metadata_blob(identity)
        candidate: Gift | None = None
        if identity.canonical_key:
            candidate = await self.get_by_canonical_key(user_id, identity.canonical_key)
        if candidate is None and identity.nft_address:
            candidate = await self.get_by_nft_address(user_id, identity.nft_address)
        if candidate is None and identity.number is not None:
            candidate = await self.get_by_collection_number(user_id, identity.collection, identity.number)

        if candidate:
            self._apply_identity(candidate, identity, meta)
            if purchase_price_ton is not None:
                candidate.purchase_price_ton = purchase_price_ton
            if target_price_ton is not None:
                candidate.target_price_ton = target_price_ton
            if not candidate.title:
                candidate.title = f"{candidate.collection} #{candidate.number}"
            await self.session.commit()
            await self.session.refresh(candidate)
            return candidate, "updated"

        gift = Gift(
            user_id=user_id,
            collection=identity.collection,
            number=identity.number if identity.number is not None else 0,
            created_at=datetime.utcnow(),
            title=f"{identity.collection} #{identity.number}" if identity.number is not None else identity.collection,
            purchase_price_ton=purchase_price_ton,
            target_price_ton=target_price_ton,
            signals_enabled=False,
        )
        self._apply_identity(gift, identity, meta)
        self.session.add(gift)
        await self.session.commit()
        await self.session.refresh(gift)
        return gift, "created"

    async def list_duplicates(self, user_id: int) -> dict[str, list[int]]:
        gifts = await self.list_by_user(user_id)
        buckets: dict[str, list[int]] = {}
        for g in gifts:
            if g.canonical_key:
                buckets.setdefault(f"canonical_key:{g.canonical_key}", []).append(g.id)
            if g.nft_address:
                buckets.setdefault(f"nft_address:{g.nft_address}", []).append(g.id)
        return {k: v for k, v in buckets.items() if len(v) > 1}

    async def set_purchase_price(self, user_id: int, gift_id: int, price_ton: float) -> Gift | None:
        gift = await self.get_by_id(user_id, gift_id)
        if gift is None:
            return None
        gift.purchase_price_ton = price_ton
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def update_gift_visuals(
        self,
        user_id: int,
        gift_id: int,
        *,
        title: str | None = None,
        image_url: str | None = None,
        attributes_json: str | None = None,
    ) -> Gift | None:
        gift = await self.get_by_id(user_id, gift_id)
        if gift is None:
            return None
        if title is not None:
            gift.title = title[:255]
        if image_url is not None:
            gift.image_url = image_url[:1024]
        if attributes_json is not None:
            gift.attributes_json = attributes_json
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def set_target_price(self, user_id: int, gift_id: int, price_ton: float) -> Gift | None:
        gift = await self.get_by_id(user_id, gift_id)
        if gift is None:
            return None
        gift.target_price_ton = price_ton
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def delete_by_id(self, user_id: int, gift_id: int) -> bool:
        stmt = delete(Gift).where(Gift.user_id == user_id, Gift.id == gift_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return bool(result.rowcount)

    async def set_signals_enabled(self, user_id: int, gift_id: int, enabled: bool) -> Gift | None:
        gift = await self.get_by_id(user_id, gift_id)
        if gift is None:
            return None
        gift.signals_enabled = enabled
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def list_gifts_for_notifications_scan(self, prefetch: int = 400) -> list[tuple[Gift, User]]:
        """Кандидаты с включёнными уведомлениями (план и интервал отфильтровывает job)."""
        stmt = (
            select(Gift, User)
            .join(User, User.id == Gift.user_id)
            .where(Gift.signals_enabled.is_(True))
            .order_by(Gift.last_signal_checked_at.is_(None).desc(), Gift.last_signal_checked_at.asc())
            .limit(prefetch)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(g, u) for g, u in rows]

    def filter_due_notification_scan(
        self,
        pairs: list[tuple[Gift, User]],
        *,
        now_utc: datetime,
        pro_interval_minutes: int,
        sniper_interval_minutes: int,
        max_items: int,
    ) -> list[tuple[Gift, User]]:
        out: list[tuple[Gift, User]] = []
        for gift, user in pairs:
            plan = normalize_plan_for_limits(user.plan)
            if plan not in ("pro", "sniper"):
                continue
            payload = gift_notifications_scan_text(gift)
            if not payload:
                continue
            interval = sniper_interval_minutes if plan == "sniper" else pro_interval_minutes
            last = gift.last_signal_checked_at
            if last is not None:
                lu = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
                nu = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
                if (nu - lu).total_seconds() < interval * 60:
                    continue
            out.append((gift, user))
            if len(out) >= max_items:
                break
        return out


def gift_notifications_scan_text(gift: Gift) -> str | None:
    addr = (gift.nft_address or "").strip()
    if addr:
        return addr
    coll = (gift.collection or "").strip()
    if coll and coll != "Unknown" and gift.number is not None:
        return f"{coll} #{gift.number}"
    return None

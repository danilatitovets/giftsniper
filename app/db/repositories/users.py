from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User, UserUniverseCollection
from app.i18n import normalize_lang


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_with_created(self, telegram_id: int, username: str | None) -> tuple[User, bool]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = await self.session.scalar(stmt)
        if user:
            return user, False
        settings = get_settings()
        now = datetime.utcnow()
        user = User(
            telegram_id=telegram_id,
            username=username,
            created_at=now,
            risk_mode=settings.default_risk_mode,
            currency=settings.default_currency,
            check_interval_minutes=settings.check_interval_minutes,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, True

    async def get_or_create(self, telegram_id: int, username: str | None) -> User:
        user, _ = await self.get_or_create_with_created(telegram_id, username)
        return user

    async def touch_activity(self, user_id: int, now: datetime | None = None) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        current = now or datetime.utcnow()
        user.last_seen_at = current
        if user.first_seen_at is None:
            user.first_seen_at = current
        user.command_count = int(user.command_count or 0) + 1
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        return await self.session.scalar(stmt)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        return await self.session.scalar(stmt)

    async def list_all(self) -> list[User]:
        stmt = select(User).order_by(User.id.asc())
        return list((await self.session.scalars(stmt)).all())

    async def count_all(self) -> int:
        return int(await self.session.scalar(select(func.count(User.id))) or 0)

    async def count_recent_created(self, days: int = 7) -> int:
        since = datetime.utcnow() - timedelta(days=days)
        return int(await self.session.scalar(select(func.count(User.id)).where(User.created_at >= since)) or 0)

    async def plans_breakdown(self) -> dict[str, int]:
        stmt = select(User.plan, func.count(User.id)).group_by(User.plan)
        rows = (await self.session.execute(stmt)).all()
        return {str(plan): int(cnt) for plan, cnt in rows}

    async def set_plan(self, user_id: int, plan: str, plan_expires_at: datetime | None = None) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.plan = plan
        user.plan_expires_at = plan_expires_at
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_role(self, user_id: int, role: str) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.role = role
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_blocked(self, user_id: int, is_blocked: bool) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.is_blocked = is_blocked
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_bankroll(self, user_id: int, bankroll_ton: float) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.bankroll_ton = bankroll_ton
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_goal(self, user_id: int, goal_ton: float) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.goal_ton = goal_ton
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_risk_limits(
        self, user_id: int, max_deal_percent: int, max_collection_percent: int, reserve_percent: int
    ) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.max_deal_percent = max_deal_percent
        user.max_collection_percent = max_collection_percent
        user.reserve_percent = reserve_percent
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_language_code(self, telegram_id: int, code: str, *, username: str | None = None) -> User:
        user = await self.get_or_create(telegram_id, username)
        user.language_code = normalize_lang(code)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_check_interval_minutes(self, user_id: int, minutes: int) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.check_interval_minutes = int(minutes)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_universe(self, user_id: int) -> list[UserUniverseCollection]:
        stmt = select(UserUniverseCollection).where(UserUniverseCollection.user_id == user_id).order_by(
            UserUniverseCollection.collection.asc()
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_universe_collection(self, user_id: int, collection: str) -> UserUniverseCollection:
        stmt = select(UserUniverseCollection).where(
            UserUniverseCollection.user_id == user_id,
            UserUniverseCollection.collection == collection,
        )
        row = await self.session.scalar(stmt)
        if row is not None:
            row.is_active = True
            await self.session.commit()
            await self.session.refresh(row)
            return row
        row = UserUniverseCollection(user_id=user_id, collection=collection, is_active=True)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def remove_universe_collection(self, user_id: int, collection: str) -> None:
        await self.session.execute(
            delete(UserUniverseCollection).where(
                UserUniverseCollection.user_id == user_id,
                UserUniverseCollection.collection == collection,
            )
        )
        await self.session.commit()

    async def set_universe_collection_state(self, user_id: int, collection: str, is_active: bool) -> bool:
        stmt = select(UserUniverseCollection).where(
            UserUniverseCollection.user_id == user_id,
            UserUniverseCollection.collection == collection,
        )
        row = await self.session.scalar(stmt)
        if row is None:
            return False
        row.is_active = is_active
        await self.session.commit()
        return True

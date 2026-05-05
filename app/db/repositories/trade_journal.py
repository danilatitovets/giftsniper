from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TradeJournal
from app.services.trade_accuracy import compute_sold_trade_accuracy


class TradeJournalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        collection: str,
        number: int | None,
        nft_address: str | None,
        attributes_json: list | dict | None,
        buy_price_ton: float | None,
        notes: str | None,
        source_url: str | None,
        prediction_snapshot: dict | None,
        signal_snapshot_id: int | None = None,
    ) -> TradeJournal:
        snap = prediction_snapshot or {}
        cc = snap.get("confidence_score")
        pred_conf = int(float(cc)) if cc is not None else None
        row = TradeJournal(
            user_id=user_id,
            collection=collection,
            number=number,
            nft_address=nft_address,
            attributes_json=attributes_json,
            buy_price_ton=buy_price_ton,
            buy_date=datetime.utcnow(),
            status="open",
            notes=notes,
            source_url=source_url,
            signal_snapshot_id=signal_snapshot_id,
            prediction_json=json.dumps(prediction_snapshot) if prediction_snapshot else None,
            decision_type=snap.get("decision_type"),
            predicted_safe_buy_ton=snap.get("safe_buy_price_ton"),
            predicted_max_buy_ton=snap.get("max_buy_price_ton"),
            predicted_list_price_ton=snap.get("normal_list_price_ton"),
            predicted_roi_percent=snap.get("expected_roi_percent"),
            predicted_confidence=pred_conf,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def create_import_row(
        self,
        *,
        user_id: int,
        collection: str,
        number: int | None,
        nft_address: str | None,
        buy_price_ton: float | None,
        buy_date: datetime | None,
        sell_price_ton: float | None,
        sell_date: datetime | None,
        status: str,
        attributes_json: list | dict | None,
        source_url: str | None,
        notes: str | None,
        prediction_snapshot: dict | None,
    ) -> TradeJournal:
        snap = prediction_snapshot or {}
        sd = sell_date or (datetime.utcnow() if status == "sold" and sell_price_ton else None)
        cc = snap.get("confidence_score")
        pred_conf = int(float(cc)) if cc is not None else None
        row = TradeJournal(
            user_id=user_id,
            collection=collection,
            number=number,
            nft_address=nft_address,
            attributes_json=attributes_json,
            buy_price_ton=buy_price_ton,
            buy_date=buy_date or datetime.utcnow(),
            sell_price_ton=sell_price_ton,
            sell_date=sd,
            status=status,
            notes=notes,
            source_url=source_url,
            prediction_json=json.dumps(snap) if snap else None,
            decision_type=snap.get("decision_type") if snap else None,
            predicted_safe_buy_ton=snap.get("safe_buy_price_ton"),
            predicted_max_buy_ton=snap.get("max_buy_price_ton"),
            predicted_list_price_ton=snap.get("normal_list_price_ton"),
            predicted_roi_percent=snap.get("expected_roi_percent"),
            predicted_confidence=pred_conf,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def apply_accuracy_fields(self, trade_id: int, user_id: int, fields: dict[str, Any]) -> None:
        row = await self.get(trade_id, user_id)
        if row is None:
            return
        tags = fields.get("accuracy_tags_json")
        if isinstance(tags, list):
            row.accuracy_tags_json = tags
        if fields.get("realized_profit_ton") is not None:
            row.realized_profit_ton = fields["realized_profit_ton"]
        if fields.get("realized_roi_percent") is not None:
            row.realized_roi_percent = fields["realized_roi_percent"]
        if fields.get("hold_time_hours") is not None:
            row.hold_time_hours = fields["hold_time_hours"]
        if fields.get("prediction_error_json"):
            row.prediction_error_json = fields["prediction_error_json"]
        row.updated_at = datetime.utcnow()
        await self.session.commit()

    async def get(self, trade_id: int, user_id: int) -> TradeJournal | None:
        r = await self.session.execute(
            select(TradeJournal).where(TradeJournal.id == trade_id, TradeJournal.user_id == user_id)
        )
        return r.scalar_one_or_none()

    async def list_for_user(self, user_id: int, limit: int = 50) -> list[TradeJournal]:
        r = await self.session.execute(
            select(TradeJournal).where(TradeJournal.user_id == user_id).order_by(TradeJournal.id.desc()).limit(limit)
        )
        return list(r.scalars().all())

    async def count_open_for_user(self, user_id: int) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(TradeJournal).where(
                TradeJournal.user_id == user_id,
                TradeJournal.status == "open",
            )
        )
        return int(r.scalar_one() or 0)

    async def list_closed_all_users(self, limit: int = 5000) -> list[TradeJournal]:
        r = await self.session.execute(
            select(TradeJournal).where(TradeJournal.status == "sold").order_by(TradeJournal.id.desc()).limit(limit)
        )
        return list(r.scalars().all())

    async def list_all(self, limit: int = 10000) -> list[TradeJournal]:
        r = await self.session.execute(select(TradeJournal).order_by(TradeJournal.id.desc()).limit(limit))
        return list(r.scalars().all())

    async def mark_sold(self, trade_id: int, user_id: int, sell_price: float, notes: str | None) -> TradeJournal | None:
        row = await self.get(trade_id, user_id)
        if row is None:
            return None
        sd = datetime.utcnow()
        row.sell_price_ton = sell_price
        row.sell_date = sd
        row.status = "sold"
        if notes:
            row.notes = (row.notes or "") + "\n" + notes
        acc = compute_sold_trade_accuracy(row, sell_price, sell_date=sd)
        row.realized_profit_ton = acc["realized_profit_ton"]
        row.realized_roi_percent = acc["realized_roi_percent"]
        row.hold_time_hours = acc["hold_time_hours"]
        row.accuracy_tags_json = acc["accuracy_tags_json"]
        row.prediction_error_json = acc["prediction_error_json"]
        row.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def cancel(self, trade_id: int, user_id: int, notes: str | None) -> TradeJournal | None:
        row = await self.get(trade_id, user_id)
        if row is None:
            return None
        row.status = "cancelled"
        if notes:
            row.notes = (row.notes or "") + "\n" + notes
        row.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(row)
        return row

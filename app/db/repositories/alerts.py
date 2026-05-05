from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AlertRule,
    SmartAlertEvent,
    SmartAlertIncident,
    SmartAlertIncidentAction,
    SmartAlertState,
    UserNotificationSettings,
)


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_alert_rule(
        self,
        user_id: int,
        collection: str | None,
        trait_type: str | None = None,
        trait_value: str | None = None,
        max_price_ton: float | None = None,
        min_price_ton: float | None = None,
        is_active: bool = True,
    ) -> AlertRule:
        rule = AlertRule(
            user_id=user_id,
            collection=collection,
            trait_type=trait_type,
            trait_value=trait_value,
            max_price_ton=max_price_ton,
            min_price_ton=min_price_ton,
            is_active=is_active,
        )
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def upsert_smart_alert_rule(
        self,
        user_id: int,
        alert_type: str,
        threshold_value: float | None,
        cooldown_minutes: int | None,
        is_active: bool,
    ) -> AlertRule:
        stmt = select(AlertRule).where(
            AlertRule.user_id == user_id,
            AlertRule.alert_type == alert_type,
            AlertRule.collection.is_(None),
        )
        rule = await self.session.scalar(stmt)
        if rule is None:
            rule = AlertRule(
                user_id=user_id,
                collection=None,
                alert_type=alert_type,
                threshold_value=threshold_value,
                cooldown_minutes=cooldown_minutes,
                is_active=is_active,
            )
            self.session.add(rule)
        else:
            rule.threshold_value = threshold_value
            rule.cooldown_minutes = cooldown_minutes
            rule.is_active = is_active
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def list_user_smart_alert_rules(self, user_id: int) -> list[AlertRule]:
        stmt = (
            select(AlertRule)
            .where(AlertRule.user_id == user_id, AlertRule.alert_type != "price")
            .order_by(AlertRule.alert_type.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_smart_alert_state(self, user_id: int, alert_type: str, collection: str | None = None) -> SmartAlertState | None:
        stmt = select(SmartAlertState).where(
            SmartAlertState.user_id == user_id,
            SmartAlertState.alert_type == alert_type,
            SmartAlertState.collection == collection,
        )
        return await self.session.scalar(stmt)

    async def upsert_smart_alert_state(
        self,
        user_id: int,
        alert_type: str,
        collection: str | None,
        last_regime: str | None = None,
        last_strength_score: float | None = None,
        last_liquidity_score: float | None = None,
        last_payload_hash: str | None = None,
        last_sent_at: datetime | None = None,
    ) -> SmartAlertState:
        state = await self.get_smart_alert_state(user_id, alert_type, collection)
        if state is None:
            state = SmartAlertState(user_id=user_id, alert_type=alert_type, collection=collection)
            self.session.add(state)
        if last_regime is not None:
            state.last_regime = last_regime
        if last_strength_score is not None:
            state.last_strength_score = last_strength_score
        if last_liquidity_score is not None:
            state.last_liquidity_score = last_liquidity_score
        if last_payload_hash is not None:
            state.last_payload_hash = last_payload_hash
        if last_sent_at is not None:
            state.last_sent_at = last_sent_at
        await self.session.commit()
        await self.session.refresh(state)
        return state

    async def create_smart_alert_event(
        self,
        user_id: int,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        payload_hash: str,
        collection: str | None = None,
        is_sent: bool = False,
        is_batched: bool = False,
        sent_at: datetime | None = None,
    ) -> SmartAlertEvent:
        event = SmartAlertEvent(
            user_id=user_id,
            alert_type=alert_type,
            collection=collection,
            severity=severity,
            title=title,
            message=message,
            payload_hash=payload_hash,
            is_sent=is_sent,
            is_batched=is_batched,
            sent_at=sent_at,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def list_pending_batched_events(self, user_id: int | None = None) -> list[SmartAlertEvent]:
        stmt = select(SmartAlertEvent).where(SmartAlertEvent.is_sent.is_(False), SmartAlertEvent.is_batched.is_(True))
        if user_id is not None:
            stmt = stmt.where(SmartAlertEvent.user_id == user_id)
        stmt = stmt.order_by(SmartAlertEvent.created_at.asc())
        return list((await self.session.scalars(stmt)).all())

    async def mark_events_sent(self, event_ids: list[int], sent_at: datetime) -> None:
        if not event_ids:
            return
        stmt = select(SmartAlertEvent).where(SmartAlertEvent.id.in_(event_ids))
        rows = list((await self.session.scalars(stmt)).all())
        for row in rows:
            row.is_sent = True
            row.sent_at = sent_at
        await self.session.commit()

    async def link_event_to_incident(self, event_id: int, incident_id: int | None) -> None:
        row = await self.session.get(SmartAlertEvent, event_id)
        if row is None:
            return
        row.incident_id = incident_id
        await self.session.commit()

    async def list_recent_events(self, user_id: int, limit: int = 10) -> list[SmartAlertEvent]:
        stmt = (
            select(SmartAlertEvent)
            .where(SmartAlertEvent.user_id == user_id)
            .order_by(SmartAlertEvent.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_alert_rules(self, user_id: int | None = None) -> int:
        stmt = select(func.count(AlertRule.id))
        if user_id is not None:
            stmt = stmt.where(AlertRule.user_id == user_id)
        return int(await self.session.scalar(stmt) or 0)

    async def count_incidents(self, user_id: int | None = None) -> int:
        stmt = select(func.count(SmartAlertIncident.id))
        if user_id is not None:
            stmt = stmt.where(SmartAlertIncident.user_id == user_id)
        return int(await self.session.scalar(stmt) or 0)

    async def find_open_incident(self, user_id: int, alert_type: str, collection: str | None) -> SmartAlertIncident | None:
        stmt = select(SmartAlertIncident).where(
            SmartAlertIncident.user_id == user_id,
            SmartAlertIncident.alert_type == alert_type,
            SmartAlertIncident.collection == collection,
            SmartAlertIncident.status == "open",
        )
        return await self.session.scalar(stmt)

    async def create_incident(
        self, user_id: int, alert_type: str, collection: str | None, severity: str, title: str, summary: str, payload_hash: str
    ) -> SmartAlertIncident:
        now = datetime.utcnow()
        row = SmartAlertIncident(
            user_id=user_id,
            alert_type=alert_type,
            collection=collection,
            status="open",
            severity=severity,
            title=title,
            first_seen_at=now,
            last_seen_at=now,
            event_count=1,
            last_payload_hash=payload_hash,
            escalation_level=0,
            summary=summary,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_incident(
        self,
        incident_id: int,
        *,
        severity: str | None = None,
        summary: str | None = None,
        payload_hash: str | None = None,
        event_increment: int = 1,
        escalation_increment: int = 0,
        status: str | None = None,
        recovered_at: datetime | None = None,
    ) -> SmartAlertIncident | None:
        row = await self.session.get(SmartAlertIncident, incident_id)
        if row is None:
            return None
        row.last_seen_at = datetime.utcnow()
        row.event_count += event_increment
        row.escalation_level += escalation_increment
        if severity is not None:
            row.severity = severity
        if summary is not None:
            row.summary = summary
        if payload_hash is not None:
            row.last_payload_hash = payload_hash
        if status is not None:
            row.status = status
        if recovered_at is not None:
            row.recovered_at = recovered_at
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_open_incidents(self, user_id: int) -> list[SmartAlertIncident]:
        stmt = (
            select(SmartAlertIncident)
            .where(SmartAlertIncident.user_id == user_id, SmartAlertIncident.status == "open")
            .order_by(SmartAlertIncident.last_seen_at.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_recovered_incidents(self, user_id: int, limit: int = 10) -> list[SmartAlertIncident]:
        stmt = (
            select(SmartAlertIncident)
            .where(SmartAlertIncident.user_id == user_id, SmartAlertIncident.status == "recovered")
            .order_by(SmartAlertIncident.recovered_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_incident(self, user_id: int, incident_id: int) -> SmartAlertIncident | None:
        stmt = select(SmartAlertIncident).where(SmartAlertIncident.user_id == user_id, SmartAlertIncident.id == incident_id)
        return await self.session.scalar(stmt)

    async def acknowledge_incident(self, user_id: int, incident_id: int) -> SmartAlertIncident | None:
        incident = await self.get_incident(user_id, incident_id)
        if incident is None:
            return None
        incident.acknowledged_at = datetime.utcnow()
        incident.acknowledged_by_user_id = user_id
        self.session.add(SmartAlertIncidentAction(incident_id=incident.id, user_id=user_id, action_type="ack"))
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def mute_incident(self, user_id: int, incident_id: int, minutes: int, reason: str | None) -> SmartAlertIncident | None:
        incident = await self.get_incident(user_id, incident_id)
        if incident is None:
            return None
        incident.muted_until = datetime.utcnow() + timedelta(minutes=minutes)
        incident.mute_reason = reason
        self.session.add(
            SmartAlertIncidentAction(incident_id=incident.id, user_id=user_id, action_type="mute", note=reason)
        )
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def unmute_incident(self, user_id: int, incident_id: int) -> SmartAlertIncident | None:
        incident = await self.get_incident(user_id, incident_id)
        if incident is None:
            return None
        incident.muted_until = None
        self.session.add(SmartAlertIncidentAction(incident_id=incident.id, user_id=user_id, action_type="unmute"))
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def resolve_incident_manually(self, user_id: int, incident_id: int, note: str | None) -> SmartAlertIncident | None:
        incident = await self.get_incident(user_id, incident_id)
        if incident is None:
            return None
        incident.status = "recovered"
        incident.resolved_manually_at = datetime.utcnow()
        incident.recovered_at = datetime.utcnow()
        incident.resolved_note = note
        self.session.add(SmartAlertIncidentAction(incident_id=incident.id, user_id=user_id, action_type="resolve", note=note))
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def mark_incident_false_positive(self, user_id: int, incident_id: int, note: str | None) -> SmartAlertIncident | None:
        incident = await self.get_incident(user_id, incident_id)
        if incident is None:
            return None
        incident.is_false_positive = True
        incident.false_positive_note = note
        self.session.add(
            SmartAlertIncidentAction(incident_id=incident.id, user_id=user_id, action_type="false_positive", note=note)
        )
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def add_incident_note(self, user_id: int, incident_id: int, note: str) -> SmartAlertIncident | None:
        incident = await self.get_incident(user_id, incident_id)
        if incident is None:
            return None
        incident.summary = (incident.summary + "\n" if incident.summary else "") + note
        self.session.add(SmartAlertIncidentAction(incident_id=incident.id, user_id=user_id, action_type="note", note=note))
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def list_incident_actions(self, user_id: int, incident_id: int) -> list[SmartAlertIncidentAction]:
        incident = await self.get_incident(user_id, incident_id)
        if incident is None:
            return []
        stmt = (
            select(SmartAlertIncidentAction)
            .where(SmartAlertIncidentAction.incident_id == incident_id, SmartAlertIncidentAction.user_id == user_id)
            .order_by(SmartAlertIncidentAction.created_at.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_recurring_incidents(self, user_id: int, days: int = 7) -> list[tuple[str, int]]:
        since = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(SmartAlertIncident.alert_type, func.count(SmartAlertIncident.id))
            .where(
                SmartAlertIncident.user_id == user_id,
                SmartAlertIncident.created_at >= since,
                SmartAlertIncident.is_false_positive.is_(False),
            )
            .group_by(SmartAlertIncident.alert_type)
            .order_by(func.count(SmartAlertIncident.id).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [(str(t), int(c)) for t, c in rows]

    async def get_or_create_notification_settings(self, user_id: int) -> UserNotificationSettings:
        stmt = select(UserNotificationSettings).where(UserNotificationSettings.user_id == user_id)
        row = await self.session.scalar(stmt)
        if row is not None:
            return row
        row = UserNotificationSettings(user_id=user_id)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_notification_settings(self, user_id: int, **kwargs) -> UserNotificationSettings:
        row = await self.get_or_create_notification_settings(user_id)
        for key, value in kwargs.items():
            setattr(row, key, value)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_user_alert_rules(self, user_id: int) -> list[AlertRule]:
        stmt = select(AlertRule).where(AlertRule.user_id == user_id).order_by(AlertRule.id.asc())
        return list((await self.session.scalars(stmt)).all())

    async def list_active_alert_rules(self) -> list[AlertRule]:
        stmt = select(AlertRule).where(AlertRule.is_active.is_(True)).order_by(AlertRule.id.asc())
        return list((await self.session.scalars(stmt)).all())

    async def get_user_alert_rule(self, user_id: int, rule_id: int) -> AlertRule | None:
        stmt = select(AlertRule).where(AlertRule.user_id == user_id, AlertRule.id == rule_id)
        return await self.session.scalar(stmt)

    async def delete_user_alert_rule(self, user_id: int, rule_id: int) -> bool:
        stmt = delete(AlertRule).where(AlertRule.user_id == user_id, AlertRule.id == rule_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def set_alert_rule_active(self, user_id: int, rule_id: int, is_active: bool) -> AlertRule | None:
        rule = await self.get_user_alert_rule(user_id, rule_id)
        if rule is None:
            return None
        rule.is_active = is_active
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def update_alert_rule(
        self,
        user_id: int,
        rule_id: int,
        collection: str | None = None,
        trait_type: str | None = None,
        trait_value: str | None = None,
        max_price_ton: float | None = None,
        min_price_ton: float | None = None,
    ) -> AlertRule | None:
        rule = await self.get_user_alert_rule(user_id, rule_id)
        if rule is None:
            return None
        if collection is not None:
            rule.collection = collection
        rule.trait_type = trait_type
        rule.trait_value = trait_value
        rule.max_price_ton = max_price_ton
        rule.min_price_ton = min_price_ton
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def update_alert_rule_state(
        self,
        rule_id: int,
        last_checked_at: datetime,
        last_is_triggered: bool,
        last_value_ton: float | None,
        triggered_now: bool,
    ) -> AlertRule | None:
        stmt = select(AlertRule).where(AlertRule.id == rule_id)
        rule = await self.session.scalar(stmt)
        if rule is None:
            return None
        rule.last_checked_at = last_checked_at
        rule.last_is_triggered = last_is_triggered
        if last_value_ton is not None:
            rule.last_value_ton = last_value_ton
        if triggered_now:
            rule.last_triggered_at = last_checked_at
            rule.trigger_count += 1
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

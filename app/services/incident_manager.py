from __future__ import annotations

from datetime import datetime, timedelta, timezone


def should_suppress_event(incident, event, now: datetime) -> bool:
    if incident is None:
        return False
    # explicit mute suppresses all non-recovery notifications
    muted_until_value = getattr(incident, "muted_until", None)
    if muted_until_value is not None:
        muted_until = muted_until_value if muted_until_value.tzinfo else muted_until_value.replace(tzinfo=timezone.utc)
        if now <= muted_until:
            return True
    if getattr(incident, "is_false_positive", False) and incident.last_payload_hash == event.payload_hash:
        return True
    if getattr(incident, "acknowledged_at", None) is not None and event.severity.lower() != "critical":
        return True
    if incident.last_payload_hash == event.payload_hash:
        return True
    # suppress noisy repeats within 15 minutes for same incident
    last = incident.last_seen_at if incident.last_seen_at.tzinfo else incident.last_seen_at.replace(tzinfo=timezone.utc)
    return now - last < timedelta(minutes=15)


def escalate_incident(incident, event, now: datetime) -> tuple[str, int]:
    severity = event.severity.lower()
    inc = 0
    # WARNING -> CRITICAL escalation rules
    if severity == "warning":
        if incident.event_count >= 3:
            severity = "critical"
            inc += 1
        if event.alert_type == "liquidity_crash" and incident.event_count >= 2:
            severity = "critical"
            inc += 1
        if event.alert_type == "concentration_risk":
            first = incident.first_seen_at if incident.first_seen_at.tzinfo else incident.first_seen_at.replace(tzinfo=timezone.utc)
            if now - first >= timedelta(hours=6):
                severity = "critical"
                inc += 1
    if severity == "info" and incident.event_count >= 2:
        severity = "warning"
        inc += 1
    if getattr(incident, "severity", "").lower() == "critical":
        severity = "critical"
    return severity, inc


def detect_recovery(alert_type: str, current_context: dict) -> tuple[bool, str]:
    if alert_type == "regime_change":
        prev = current_context.get("prev_regime")
        curr = current_context.get("current_regime")
        if prev in {"risk_off", "illiquid", "data_poor"} and curr in {"neutral", "risk_on"}:
            return True, f"Было: {prev}\nСтало: {curr}"
    if alert_type == "liquidity_crash":
        if float(current_context.get("liquidity_score", 0)) > float(current_context.get("threshold", 30)):
            return True, "Ликвидность восстановилась выше порога."
    if alert_type == "concentration_risk":
        if float(current_context.get("exposure_percent", 0)) <= float(current_context.get("limit_percent", 40)):
            return True, "Концентрация вернулась в предел лимита."
    if alert_type == "stay_in_cash":
        if current_context.get("regime") in {"neutral", "risk_on"} and current_context.get("best_tier") in {"A_TIER", "S_TIER"}:
            return True, "Появились более сильные возможности."
    if alert_type == "data_stale":
        if current_context.get("freshness") == "fresh":
            return True, "Данные снова свежие."
    return False, ""


def format_incident_update(incident, event) -> str:
    return (
        f"🔥 Ongoing incident #{incident.id}\n"
        f"{incident.alert_type} ({incident.severity.upper()})\n"
        f"Events: {incident.event_count}\n"
        f"First seen: {incident.first_seen_at}\n"
        f"Last seen: {incident.last_seen_at}\n"
        f"Message: {event.title}"
    )


def format_recovery_message(incident, recovery_summary: str) -> str:
    return (
        f"✅ Recovery: {incident.alert_type}\n\n"
        f"Incident #{incident.id} closed.\n"
        f"{recovery_summary}\n\n"
        "Ситуация улучшилась, но проверяйте сделки вручную."
    )

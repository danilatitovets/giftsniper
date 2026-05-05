from __future__ import annotations

from datetime import datetime, time, timezone


SEVERITY_ORDER = {"info": 1, "warning": 2, "critical": 3}


def classify_severity(signal: str, context: dict | None = None) -> str:
    context = context or {}
    if signal in {"liquidity_crash", "stay_in_cash"}:
        return "critical"
    if signal in {"concentration_risk", "rebalance_needed", "strength_drop"}:
        return "warning"
    if signal == "regime_change":
        regime = context.get("regime", "")
        return "warning" if regime in {"risk_off", "illiquid"} else "info"
    return "info"


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except Exception:
        return None


def is_quiet_hours(user_settings, now: datetime) -> bool:
    if not getattr(user_settings, "quiet_hours_enabled", False):
        return False
    start = _parse_hhmm(getattr(user_settings, "quiet_hours_start", None))
    end = _parse_hhmm(getattr(user_settings, "quiet_hours_end", None))
    if start is None or end is None:
        return False
    now_t = now.astimezone(timezone.utc).time()
    if start <= end:
        return start <= now_t <= end
    return now_t >= start or now_t <= end


def should_send_now(user_settings, event, now: datetime) -> bool:
    severity = event.severity.lower()
    min_sev = getattr(user_settings, "min_severity_to_notify", "warning").lower()
    if SEVERITY_ORDER.get(severity, 0) < SEVERITY_ORDER.get(min_sev, 2):
        return False
    quiet = is_quiet_hours(user_settings, now)
    mode = getattr(user_settings, "delivery_mode", "smart")
    if severity == "critical" and getattr(user_settings, "critical_ignore_quiet_hours", True):
        return True
    if mode == "instant":
        return not quiet
    if mode == "digest":
        return severity == "critical" and not quiet
    # smart
    if severity == "critical":
        return True
    if severity == "warning":
        return not quiet
    return False


def should_batch(user_settings, event, now: datetime) -> bool:
    if should_send_now(user_settings, event, now):
        return False
    severity = event.severity.lower()
    mode = getattr(user_settings, "delivery_mode", "smart")
    if mode == "digest":
        return True
    if mode == "instant":
        return is_quiet_hours(user_settings, now)
    # smart
    return severity in {"info", "warning"} or is_quiet_hours(user_settings, now)


def group_events_for_digest(events: list) -> dict[str, list]:
    grouped = {"critical": [], "warning": [], "info": []}
    for e in events:
        grouped.setdefault(e.severity.lower(), []).append(e)
    return grouped


def format_alert_event(event) -> str:
    icon = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(event.severity.lower(), "ℹ️")
    suffix = f" ({event.collection})" if getattr(event, "collection", None) else ""
    return f"{icon} {event.severity.upper()}: {event.alert_type}{suffix}\n{event.message}"


def format_digest(events: list) -> str:
    grouped = group_events_for_digest(events)
    lines = ["📬 GiftSniper Digest\n"]
    incident_events = [e for e in events if getattr(e, "incident_id", None)]
    if incident_events:
        lines.append("🔥 Ongoing incidents:")
        for idx, e in enumerate(incident_events[:5], start=1):
            lines.append(f"{idx}. {e.severity.upper()} {e.alert_type} — incident #{e.incident_id}")
        lines.append("")
    recovery_events = [e for e in events if getattr(e, "alert_type", "").endswith("_recovery")]
    if recovery_events:
        lines.append("✅ Recoveries:")
        for idx, e in enumerate(recovery_events[:5], start=1):
            lines.append(f"{idx}. {e.title}")
        lines.append("")
    for sev, title in [("critical", "🚨 Critical"), ("warning", "⚠️ Warnings"), ("info", "ℹ️ Info")]:
        if not grouped.get(sev):
            continue
        lines.append(f"{title}:")
        for idx, e in enumerate(grouped[sev], start=1):
            lines.append(f"{idx}. {e.title}")
        lines.append("")
    return "\n".join(lines).strip()

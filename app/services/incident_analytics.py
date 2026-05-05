from __future__ import annotations

from datetime import datetime, timezone


def calculate_time_to_recover(incident) -> float | None:
    if incident.recovered_at is None:
        return None
    start = incident.first_seen_at if incident.first_seen_at.tzinfo else incident.first_seen_at.replace(tzinfo=timezone.utc)
    end = incident.recovered_at if incident.recovered_at.tzinfo else incident.recovered_at.replace(tzinfo=timezone.utc)
    return max(0.0, (end - start).total_seconds() / 60.0)


def calculate_incident_age(incident) -> float:
    now = datetime.now(timezone.utc)
    start = incident.first_seen_at if incident.first_seen_at.tzinfo else incident.first_seen_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - start).total_seconds() / 60.0)


def summarize_incidents(open_incidents: list, recovered_incidents: list) -> dict:
    ttrs = [x for x in (calculate_time_to_recover(i) for i in recovered_incidents) if x is not None]
    avg_ttr = sum(ttrs) / len(ttrs) if ttrs else 0.0
    oldest = max(open_incidents, key=calculate_incident_age) if open_incidents else None
    return {
        "open_count": len(open_incidents),
        "critical_count": len([i for i in open_incidents if i.severity.lower() == "critical"]),
        "recovered_count": len(recovered_incidents),
        "avg_ttr_minutes": avg_ttr,
        "oldest_open": oldest,
        "muted_count": len([i for i in open_incidents if i.muted_until is not None]),
        "ack_count": len([i for i in open_incidents if i.acknowledged_at is not None]),
    }


def find_top_recurring_incidents(recurring_rows: list[tuple[str, int]], top_n: int = 3) -> list[tuple[str, int]]:
    return recurring_rows[:top_n]


def calculate_false_positive_rate(all_incidents: list) -> tuple[int, float]:
    total = len(all_incidents)
    fp = len([i for i in all_incidents if i.is_false_positive])
    rate = (fp / total * 100.0) if total > 0 else 0.0
    return fp, rate


def format_incident_analytics_report(summary: dict, recurring: list[tuple[str, int]], false_positive_count: int, false_positive_rate: float) -> str:
    avg_ttr_h = int(summary["avg_ttr_minutes"] // 60)
    avg_ttr_m = int(summary["avg_ttr_minutes"] % 60)
    oldest = summary["oldest_open"]
    oldest_text = f"{oldest.alert_type} — {int(calculate_incident_age(oldest)//60)}h" if oldest else "n/a"
    recurring_text = "\n".join(f"{idx}. {t} — {c} times" for idx, (t, c) in enumerate(recurring, start=1)) or "none"
    return (
        "📊 Incident Analytics — 7 days\n\n"
        f"Open: {summary['open_count']}\n"
        f"Critical: {summary['critical_count']}\n"
        f"Recovered: {summary['recovered_count']}\n"
        f"Avg time-to-recover: {avg_ttr_h}h {avg_ttr_m}m\n"
        f"Oldest open: {oldest_text}\n\n"
        f"Top recurring:\n{recurring_text}\n\n"
        f"False positives: {false_positive_count} ({false_positive_rate:.1f}%)\n"
        f"Muted: {summary['muted_count']}\n"
        f"Acknowledged open: {summary['ack_count']}"
    )

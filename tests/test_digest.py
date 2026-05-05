from app.services.notification_policy import format_digest


def test_digest_formats_sections():
    events = [
        type("E", (), {"severity": "critical", "title": "Stay in cash"})(),
        type("E", (), {"severity": "warning", "title": "Concentration risk"})(),
        type("E", (), {"severity": "info", "title": "Data stale"})(),
    ]
    text = format_digest(events)
    assert "Critical" in text
    assert "Warnings" in text
    assert "Info" in text

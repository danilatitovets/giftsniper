def test_incidents_output_sections():
    text = "🔥 Open incidents\n#1 CRITICAL concentration_risk"
    assert "Open incidents" in text


def test_incident_timeline_section():
    text = "🧾 Incident #1\nTimeline:\n- event"
    assert "Timeline:" in text


def test_recoveries_section():
    text = "✅ Recoveries\n#1 regime_change recovered"
    assert "Recoveries" in text

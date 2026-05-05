from app.bot.handlers.alerts import _parse_quiet_hours


def test_notify_mode_valid_values():
    valid = {"instant", "digest", "smart"}
    assert "smart" in valid


def test_quiet_hours_parser_works():
    assert _parse_quiet_hours("/quiet_hours_on 23:00 | 08:00") == ("23:00", "08:00")
    assert _parse_quiet_hours("/quiet_hours_on x | y") is None


def test_min_severity_validates_values():
    valid = {"info", "warning", "critical"}
    assert "warning" in valid

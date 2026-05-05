from app.services.feature_limits import can_use_feature, check_usage_limit


def _user(role: str, blocked: bool = False):
    return type("U", (), {"role": role, "is_blocked": blocked, "plan": "free"})()


def test_owner_admin_bypass_limits():
    assert can_use_feature(_user("owner"), "smart_alerts") is True
    assert can_use_feature(_user("admin"), "scan_universe") is True
    ok, limit = check_usage_limit(_user("owner"), "max_gifts", 10_000)
    assert ok is True
    assert limit > 1000


def test_blocked_owner_still_blocked():
    assert can_use_feature(_user("owner", blocked=True), "smart_alerts") is False

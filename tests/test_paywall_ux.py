from app.services.feature_limits import assert_feature_allowed, paywall_message_for


def test_assert_feature_raises_friendly_paywall():
    user = type("U", (), {"plan": "free", "role": "user", "is_blocked": False})()
    try:
        assert_feature_allowed(user, "capital_plan")
    except PermissionError as exc:
        assert "/upgrade" in str(exc)
    else:
        raise AssertionError("expected PermissionError")


def test_paywall_includes_upgrade_and_free_hint():
    user = type("U", (), {"plan": "free", "role": "user", "is_blocked": False})()
    msg = paywall_message_for("capital_plan", user)
    assert "/upgrade" in msg
    assert "/lite_plan" in msg or "lite" in msg.lower()


def test_paywall_scan_universe_suggests_alternative():
    user = type("U", (), {"plan": "free", "role": "user", "is_blocked": False})()
    msg = paywall_message_for("scan_universe", user)
    assert "/upgrade" in msg or "Free" in msg

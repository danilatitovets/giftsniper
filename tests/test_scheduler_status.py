from app.services import runtime_state


def test_scheduler_status_fields_exist():
    assert hasattr(runtime_state, "last_price_alert_check")
    assert hasattr(runtime_state, "last_smart_alert_check")
    assert hasattr(runtime_state, "last_digest_check")
    assert hasattr(runtime_state, "last_accuracy_digest_check")

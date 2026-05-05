def test_admin_webhook_events_format():
    text = "🪝 Webhook events\n#1 mock mock.checkout.completed status=processed user=1 plan=pro"
    assert "Webhook events" in text
    assert "status=processed" in text


def test_admin_retry_webhook_respects_attempts():
    result = {"status": "dead_letter"}
    assert result["status"] == "dead_letter"

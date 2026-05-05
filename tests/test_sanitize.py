from app.utils.sanitize import sanitize_headers, sanitize_payload, sanitize_url


def test_sanitize_removes_secrets():
    payload = {"token": "SECRET", "nested": {"password": "PASS", "ok": 1}}
    result = sanitize_payload(payload)
    assert result["token"] == "***REDACTED***"
    assert result["nested"]["password"] == "***REDACTED***"


def test_sanitize_headers():
    headers = {"Authorization": "Bearer SECRET", "X-Api-Key": "ABC", "Accept": "application/json"}
    cleaned = sanitize_headers(headers)
    assert cleaned["Authorization"] == "***REDACTED***"
    assert cleaned["X-Api-Key"] == "***REDACTED***"
    assert cleaned["Accept"] == "application/json"


def test_sanitize_url_hides_credentials():
    url = "postgresql://user:pass@example.com:5432/db"
    cleaned = sanitize_url(url)
    assert "pass" not in cleaned

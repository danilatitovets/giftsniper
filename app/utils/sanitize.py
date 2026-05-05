from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


SECRET_KEYS = {"authorization", "api-key", "x-api-key", "token", "password", "secret", "database_url", "bot_token"}


def sanitize_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def sanitize_headers(headers: dict | None) -> dict:
    if not headers:
        return {}
    result: dict = {}
    for key, value in headers.items():
        if key.lower() in SECRET_KEYS:
            result[key] = "***REDACTED***"
        else:
            result[key] = value
    return result


def sanitize_payload(payload):
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            if str(key).lower() in SECRET_KEYS:
                out[key] = "***REDACTED***"
            else:
                out[key] = sanitize_payload(value)
        return out
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload

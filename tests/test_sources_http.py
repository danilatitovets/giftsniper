import logging

import pytest

from app.sources.http import (
    MarketHTTPClient,
    MarketSourceNotFound,
    MarketSourceRateLimited,
    MarketSourceUnavailable,
)


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, responses):
        self.responses = responses
        self.idx = -1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers=None, params=None):
        self.idx += 1
        return self.responses[self.idx]


@pytest.mark.asyncio
async def test_http_helper_retries(monkeypatch):
    responses = [_Resp(status_code=500), _Resp(status_code=200, payload={"ok": True})]
    state = {"idx": -1}

    def factory(*args, **kwargs):
        client = _Client(responses)

        async def get(url, headers=None, params=None):
            state["idx"] += 1
            return responses[state["idx"]]

        client.get = get
        return client

    monkeypatch.setattr("httpx.AsyncClient", factory)
    client = MarketHTTPClient(timeout_seconds=1, retries=2, user_agent="GiftSniperBot/1.0")
    data = await client.get_json("https://example.test")
    assert data == {"ok": True}


@pytest.mark.asyncio
async def test_http_helper_404_not_found_no_retry(monkeypatch):
    responses = [_Resp(status_code=404)]

    def factory(*args, **kwargs):
        return _Client(responses)

    monkeypatch.setattr("httpx.AsyncClient", factory)
    client = MarketHTTPClient(timeout_seconds=1, retries=5, user_agent="GiftSniperBot/1.0")
    with pytest.raises(MarketSourceNotFound):
        await client.get_json("https://example.test")
    assert responses  # single response consumed


@pytest.mark.asyncio
async def test_http_helper_rate_limit(monkeypatch):
    responses = [_Resp(status_code=429), _Resp(status_code=429), _Resp(status_code=429)]

    def factory(*args, **kwargs):
        return _Client(responses)

    monkeypatch.setattr("httpx.AsyncClient", factory)
    client = MarketHTTPClient(timeout_seconds=1, retries=2)
    with pytest.raises(MarketSourceRateLimited):
        await client.get_json("https://example.test")


@pytest.mark.asyncio
async def test_http_helper_does_not_log_secrets(caplog, monkeypatch):
    responses = [_Resp(status_code=503), _Resp(status_code=503), _Resp(status_code=503)]

    def factory(*args, **kwargs):
        return _Client(responses)

    monkeypatch.setattr("httpx.AsyncClient", factory)
    client = MarketHTTPClient(timeout_seconds=1, retries=2)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(MarketSourceUnavailable):
            await client.get_json("https://example.test", headers={"Authorization": "Bearer SUPER_SECRET"})
    joined = "\n".join(rec.message for rec in caplog.records)
    assert "SUPER_SECRET" not in joined

from __future__ import annotations

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger

from app.config import Settings
from app.db.models import User
from app.tools import readiness_check


def _alembic_head_revision() -> str:
    script = ScriptDirectory("alembic")
    head = script.get_current_head()
    assert head is not None
    return head


def _settings(**kw: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "PRODUCTION_MODE": True,
        "ENABLE_MOCK_SOURCE": False,
        "ALLOW_MOCK_IN_PRODUCTION": False,
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "key123",
        "FULL_MARKET_SCAN_ENABLED": True,
        "NFT_GLOBAL_INDEX_ENABLED": True,
        "TONCENTER_ENABLED": False,
        "TONCENTER_API_KEY": "",
    }
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_readiness_check_ok(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(readiness_check, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="full-platform")
    assert out["ok"] is True
    assert out["mode"] == "full-platform"
    assert out["errors"] == []
    assert out["tonapi"] == "ok"
    assert out["toncenter"] in {"disabled", "missing"}


@pytest.mark.asyncio
async def test_readiness_check_missing_tonapi_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(readiness_check, "get_settings", lambda: _settings(TONAPI_API_KEY=""))
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="full-platform")
    assert out["ok"] is False
    assert out["tonapi"] == "missing"
    assert out["env"]["tonapi_api_key_set"] is False


@pytest.mark.asyncio
async def test_readiness_check_payments_config_invalid_when_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        readiness_check,
        "get_settings",
        lambda: _settings(
            TON_PAYMENT_ENABLED=True,
            TON_PAYMENT_RECEIVER_ADDRESS="",
            PLAN_PRO_PRICE_TON=0,
            PLAN_SNIPER_PRICE_TON=0,
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="full-platform")
    assert out["payments"]["enabled"] is True
    assert out["payments"]["receiver_address_configured"] is False
    assert out["payments"]["pro_price_configured"] is False
    assert out["ok"] is False


@pytest.mark.asyncio
async def test_no_secrets_in_logs(monkeypatch: pytest.MonkeyPatch):
    secret = "SUPER_SECRET_TONAPI_KEY"
    monkeypatch.setattr(readiness_check, "get_settings", lambda: _settings(TONAPI_API_KEY=secret))
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="full-platform")
    blob = str(out)
    assert secret not in blob


@pytest.mark.asyncio
async def test_readiness_warns_free_plan_bad_scan_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        readiness_check,
        "get_settings",
        lambda: _settings(
            TONAPI_GLOBAL_RPS_LIMIT=1,
            FULL_MARKET_PAGE_LIMIT=10000,
            FULL_MARKET_REQUEST_SLEEP_MS=300,
            NFT_LIVE_DISCOVERY_MAX_PAGES_FREE=5,
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="full-platform")
    warns = " ".join(out.get("warnings") or []).lower()
    assert "tonapi free" in warns
    assert "full_market_page_limit" in warns
    assert "max_pages_free" in warns


def test_users_telegram_id_bigint():
    assert isinstance(User.__table__.c.telegram_id.type, BigInteger)


def test_alembic_head_has_nft_index_tables():
    script = ScriptDirectory("alembic")
    head = script.get_current_head()
    assert head is not None
    assert script.get_revision("0033_nft_global_index") is not None


def test_mock_source_default_false() -> None:
    s = Settings(BOT_TOKEN="x", DATABASE_URL="postgresql+asyncpg://u:p@localhost/db")
    assert s.enable_mock_source is False


@pytest.mark.asyncio
async def test_readiness_nft_check_ok_without_global_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        readiness_check,
        "get_settings",
        lambda: _settings(NFT_GLOBAL_INDEX_ENABLED=False, TON_PAYMENT_ENABLED=False),
    )
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda name: (__import__("asyncio").sleep(0, result=name == "users")),
    )
    out = await readiness_check._run(mode="nft-check")
    assert out["mode"] == "nft-check"
    assert out["ok"] is True
    assert out["errors"] == []
    w = " ".join(out["warnings"]).lower()
    assert "global index" in w or "nft_global" in w


@pytest.mark.asyncio
async def test_readiness_full_platform_requires_global_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        readiness_check,
        "get_settings",
        lambda: _settings(NFT_GLOBAL_INDEX_ENABLED=False),
    )
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="full-platform")
    assert out["ok"] is False
    assert any("NFT_GLOBAL_INDEX" in e for e in out["errors"])


@pytest.mark.asyncio
async def test_readiness_mode_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness_check, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="nft-check")
    assert out["mode"] == "nft-check"
    assert isinstance(out["errors"], list)
    assert isinstance(out["warnings"], list)


@pytest.mark.asyncio
async def test_readiness_fails_if_mock_enabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        readiness_check,
        "get_settings",
        lambda: _settings(ENABLE_MOCK_SOURCE=True, TON_PAYMENT_ENABLED=False),
    )
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda name: (__import__("asyncio").sleep(0, result=name == "users")),
    )
    out = await readiness_check._run(mode="nft-check")
    assert out["ok"] is False
    assert any("ENABLE_MOCK_SOURCE" in e for e in out["errors"])


@pytest.mark.asyncio
async def test_readiness_warns_on_aggressive_free_tonapi_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        readiness_check,
        "get_settings",
        lambda: _settings(
            TONAPI_GLOBAL_RPS_LIMIT=1,
            FULL_MARKET_PAGE_LIMIT=2000,
            FULL_MARKET_REQUEST_SLEEP_MS=800,
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_db_probe",
        lambda: (
            __import__("asyncio").sleep(
                0,
                result={"ok": True, "error": None, "alembic_current": _alembic_head_revision()},
            )
        ),
    )
    monkeypatch.setattr(
        readiness_check,
        "_table_exists",
        lambda _name: (__import__("asyncio").sleep(0, result=True)),
    )
    out = await readiness_check._run(mode="full-platform")
    warns = " ".join(out.get("warnings") or []).lower()
    assert "full_market_page_limit" in warns
    assert "full_market_request_sleep_ms" in warns


def test_env_example_has_tonapi_free_safe_defaults() -> None:
    from pathlib import Path

    raw = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
    assert "TONAPI_GLOBAL_RPS_LIMIT=1" in raw
    assert "TONAPI_GLOBAL_MIN_INTERVAL_MS=1200" in raw
    assert "FULL_MARKET_PAGE_LIMIT=1000" in raw
    assert "FULL_MARKET_PAGE_LIMIT_FALLBACKS=1000,500,200,100" in raw
    assert "FULL_MARKET_REQUEST_SLEEP_MS=1200" in raw
    assert "PRODUCTION_MODE=true" in raw
    assert "ENABLE_MOCK_SOURCE=false" in raw
    assert "ALLOW_MOCK_IN_PRODUCTION=false" in raw

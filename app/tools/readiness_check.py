"""python -m app.tools.readiness_check [--mode nft-check|full-platform]"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any, Literal

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.toncenter_client import ToncenterClient
from app.services.plan_catalog import get_sellable_plan

ReadinessMode = Literal["nft-check", "full-platform"]

_TON_ADDR_RE = re.compile(r"^(?:[EUk]Q[a-zA-Z0-9_-]{20,}|0:[0-9a-fA-F]{64})$")


async def _table_exists(table_name: str) -> bool:
    q = text("SELECT to_regclass(:name)")
    async with SessionLocal() as session:
        val = await session.scalar(q, {"name": table_name})
    return bool(val)


async def _db_probe() -> dict[str, Any]:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            current = await session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except SQLAlchemyError as exc:
        return {"ok": False, "error": str(exc)[:200], "alembic_current": None}
    return {"ok": True, "error": None, "alembic_current": str(current) if current else None}


def _tonapi_free_warnings(settings: Any) -> list[str]:
    w: list[str] = []
    rps = float(getattr(settings, "tonapi_global_rps_limit", 1.0) or 1.0)
    page = int(getattr(settings, "full_market_page_limit", 0) or 0)
    sleep_ms = int(getattr(settings, "full_market_request_sleep_ms", 0) or 0)
    if rps <= 1.0 and page > 1000:
        w.append("TonAPI Free-like: FULL_MARKET_PAGE_LIMIT > 1000 with TONAPI_GLOBAL_RPS_LIMIT <= 1 — consider <=1000.")
    if rps <= 1.0 and sleep_ms < 1200:
        w.append("TonAPI Free-like: FULL_MARKET_REQUEST_SLEEP_MS < 1200 with TONAPI_GLOBAL_RPS_LIMIT <= 1 — consider >=1200.")
    return w


async def _run(*, mode: ReadinessMode = "full-platform") -> dict[str, Any]:
    settings = get_settings()
    db = await _db_probe()
    script = ScriptDirectory("alembic")
    head = script.get_current_head()

    tonapi_key_set = bool((settings.tonapi_api_key or "").strip())
    tonapi_status = "ok" if settings.tonapi_enabled and tonapi_key_set else "missing"
    if not settings.tonapi_enabled:
        tonapi_status = "disabled"

    tc = ToncenterClient(settings)
    toncenter_status = "ok" if tc.configured() else ("disabled" if not settings.toncenter_enabled else "missing")

    users_exists = await _table_exists("users")
    referrals_exists = await _table_exists("user_referrals")
    idx_exists = await _table_exists("nft_collections_index")
    alias_exists = await _table_exists("nft_collection_aliases")
    items_exists = await _table_exists("nft_items_index")
    jobs_exists = await _table_exists("nft_index_jobs")
    pay_exists = await _table_exists("ton_subscription_payments")
    consumed_exists = await _table_exists("ton_payment_consumed_tx")
    recv = (settings.ton_payment_receiver_address or "").strip()
    receiver_configured = bool(recv)
    receiver_valid = bool(_TON_ADDR_RE.match(recv))
    pro_cfg = get_sellable_plan("pro", settings) is not None
    sniper_cfg = get_sellable_plan("sniper", settings) is not None

    bot_token_ok = bool((settings.bot_token or "").strip())

    errors: list[str] = []
    warnings: list[str] = []
    warnings.extend(_tonapi_free_warnings(settings))
    if int(settings.nft_live_discovery_max_pages_free) > 2:
        warnings.append("NFT_LIVE_DISCOVERY_MAX_PAGES_FREE is high for TonAPI Free limits.")
    if settings.ton_payment_enabled and (not receiver_configured or not receiver_valid):
        warnings.append("TON payments enabled but receiver address is missing or invalid.")
    if settings.ton_payment_enabled and (not pro_cfg or not sniper_cfg):
        warnings.append("TON payments enabled but Pro/Sniper plan price or duration is invalid.")

    if mode == "nft-check":
        if not bot_token_ok:
            errors.append("BOT_TOKEN is missing or empty.")
        if not db.get("ok"):
            errors.append(f"DATABASE_URL probe failed: {db.get('error') or 'unknown'}")
        if not (db.get("alembic_current") and head and db.get("alembic_current") == head):
            errors.append("Database migrations are not at Alembic head.")
        if not users_exists:
            errors.append("users table is missing.")
        if not settings.tonapi_enabled or not tonapi_key_set:
            errors.append("TonAPI is disabled or TONAPI_API_KEY is not set.")
        if not settings.full_market_scan_enabled:
            errors.append("FULL_MARKET_SCAN_ENABLED must be true for NFT /check.")
        if settings.production_mode and settings.enable_mock_source:
            errors.append("PRODUCTION_MODE=true but ENABLE_MOCK_SOURCE=true (mock must be off in production).")
        if settings.production_mode and settings.allow_mock_in_production:
            errors.append("PRODUCTION_MODE=true but ALLOW_MOCK_IN_PRODUCTION=true.")
        if not settings.nft_global_index_enabled:
            warnings.append("NFT_GLOBAL_INDEX_ENABLED=false — optional for link-based /check; name# resolve may be limited.")
        if not (idx_exists and alias_exists and items_exists and jobs_exists):
            warnings.append("NFT global index tables missing — optional for nft-check MVP if you only use NFT links/addresses.")
        if not settings.ton_payment_enabled:
            warnings.append("TON_PAYMENT_ENABLED=false — subscription invoices disabled (ok for MVP).")
        elif not (pay_exists and consumed_exists):
            errors.append("TON payments enabled but ton_subscription_payments / ton_payment_consumed_tx tables missing.")
        elif not receiver_configured or not receiver_valid or not pro_cfg or not sniper_cfg:
            errors.append("TON payments enabled but receiver address or Pro/Sniper pricing is misconfigured.")
        if settings.toncenter_enabled and toncenter_status != "ok":
            errors.append("TONCENTER_ENABLED=true but Toncenter is not configured (API key / base URL).")
    else:
        # full-platform (legacy strict gate)
        if not bot_token_ok:
            errors.append("BOT_TOKEN is missing or empty.")
        if not db.get("ok"):
            errors.append(f"DATABASE_URL probe failed: {db.get('error') or 'unknown'}")
        if not settings.production_mode:
            errors.append("PRODUCTION_MODE must be true for full-platform readiness.")
        if settings.enable_mock_source:
            errors.append("ENABLE_MOCK_SOURCE must be false for full-platform readiness.")
        if settings.allow_mock_in_production:
            errors.append("ALLOW_MOCK_IN_PRODUCTION must be false for full-platform readiness.")
        if not settings.tonapi_enabled or not tonapi_key_set:
            errors.append("TonAPI is disabled or TONAPI_API_KEY is not set.")
        if not settings.full_market_scan_enabled:
            errors.append("FULL_MARKET_SCAN_ENABLED must be true.")
        if not settings.nft_global_index_enabled:
            errors.append("NFT_GLOBAL_INDEX_ENABLED must be true for full-platform readiness.")
        if not (idx_exists and alias_exists and items_exists and jobs_exists):
            errors.append("NFT global index tables must exist for full-platform readiness.")
        if not (pay_exists and consumed_exists):
            errors.append("Payment tables ton_subscription_payments and ton_payment_consumed_tx must exist.")
        if settings.ton_payment_enabled and (not receiver_configured or not receiver_valid or not pro_cfg or not sniper_cfg):
            errors.append("TON payments enabled but receiver or plan pricing is misconfigured.")
        if not (db.get("alembic_current") and head and db.get("alembic_current") == head):
            errors.append("Database migrations are not at Alembic head.")
        if settings.production_mode and settings.enable_mock_source:
            errors.append("PRODUCTION_MODE=true but ENABLE_MOCK_SOURCE=true.")
        if settings.production_mode and settings.allow_mock_in_production:
            errors.append("PRODUCTION_MODE=true but ALLOW_MOCK_IN_PRODUCTION=true.")
        if settings.toncenter_enabled and toncenter_status != "ok":
            errors.append("TONCENTER_ENABLED=true but Toncenter is not configured.")

    ok = len(errors) == 0

    out: dict[str, Any] = {
        "mode": mode,
        "ok": ok,
        "errors": list(errors),
        "warnings": list(warnings),
        "env": {
            "production_mode": settings.production_mode,
            "public_bot_access": settings.public_bot_access,
            "enable_mock_source": settings.enable_mock_source,
            "allow_mock_in_production": settings.allow_mock_in_production,
            "tonapi_enabled": settings.tonapi_enabled,
            "tonapi_api_key_set": tonapi_key_set,
            "full_market_scan_enabled": settings.full_market_scan_enabled,
            "nft_global_index_enabled": settings.nft_global_index_enabled,
            "toncenter_enabled": settings.toncenter_enabled,
            "toncenter_api_key_set": bool((settings.toncenter_api_key or "").strip()),
            "tonapi_global_rps_limit": settings.tonapi_global_rps_limit,
            "tonapi_global_min_interval_ms": settings.tonapi_global_min_interval_ms,
            "full_market_page_limit": settings.full_market_page_limit,
            "full_market_request_sleep_ms": settings.full_market_request_sleep_ms,
            "nft_live_discovery_max_pages_free": settings.nft_live_discovery_max_pages_free,
        },
        "db": db,
        "migrations": {
            "head": head,
            "current": db.get("alembic_current"),
            "up_to_date": bool(db.get("alembic_current") and db.get("alembic_current") == head),
        },
        "tonapi": tonapi_status,
        "toncenter": toncenter_status,
        "index": {
            "tables_exist": idx_exists and alias_exists and items_exists and jobs_exists,
            "collections": idx_exists,
            "aliases": alias_exists,
            "items": items_exists,
            "jobs": jobs_exists,
        },
        "payments": {
            "tables_exist": pay_exists and consumed_exists,
            "ton_subscription_payments": pay_exists,
            "ton_payment_consumed_tx": consumed_exists,
            "enabled": bool(settings.ton_payment_enabled),
            "receiver_address_configured": receiver_configured,
            "receiver_address_valid": receiver_valid,
            "pro_price_configured": pro_cfg,
            "sniper_price_configured": sniper_cfg,
        },
        "schema": {
            "users_table": users_exists,
            "users_telegram_id_bigint": True,
        },
        "referrals": {
            "enabled": True,
            "table_ok": referrals_exists,
        },
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="GiftSniper production readiness check")
    parser.add_argument(
        "--mode",
        choices=["nft-check", "full-platform"],
        default="full-platform",
        help="nft-check: TonAPI /check MVP; full-platform: strict stack including global index",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(mode=args.mode)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Поиск входящего перевода на кошелёк по сумме и комментарию (TonAPI)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote

from app.config import Settings
from app.services.ton_transaction_parse import extract_incoming_value_nano, extract_ton_transfer_comment
from app.sources.http import MarketHTTPClient, MarketSourceUnavailable

logger = logging.getLogger(__name__)


def _transactions_list(payload: dict[str, Any] | list | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("transactions", "events", "items"):
            raw = payload.get(key)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
    return []


async def fetch_recent_transactions(settings: Settings, account_address: str, *, limit: int = 100) -> list[dict[str, Any]]:
    base = (settings.tonapi_base_url or "").strip().rstrip("/")
    key = (settings.tonapi_api_key or "").strip()
    if not base or not key:
        return []
    enc = quote(str(account_address).strip(), safe="")
    url = f"{base}/v2/blockchain/accounts/{enc}/transactions"
    http = MarketHTTPClient(
        timeout_seconds=settings.market_http_timeout_seconds,
        retries=settings.market_http_retries,
        user_agent=settings.market_http_user_agent,
    )
    headers = {"Authorization": f"Bearer {key}"}
    try:
        raw = await http.get_json(url, headers=headers, params={"limit": limit})
    except MarketSourceUnavailable as exc:
        logger.info("TonAPI transactions fetch failed: %s", exc)
        return []
    except Exception:
        logger.exception("TonAPI transactions unexpected error")
        return []
    return _transactions_list(raw)


@dataclass(frozen=True)
class TonPaymentMatchResult:
    """Результат поиска входящего платежа (exact / overpay / underpay)."""

    status: Literal["paid", "underpaid", "not_found"]
    tx_hash: str | None = None
    actual_nano: int = 0
    expected_nano: int = 0


async def match_incoming_payment(
    settings: Settings,
    *,
    receiver_address: str,
    expected_nano: int,
    expected_comment: str,
    is_tx_consumed: Callable[[str], Awaitable[bool]] | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> TonPaymentMatchResult:
    """
    Находит входящий перевод с нужным комментарием.
    Успех при actual_nano >= expected_nano; при меньшей сумме — underpaid (без списания tx).
    """
    txs = await fetch_recent_transactions(settings, receiver_address, limit=100)
    exp_c = (expected_comment or "").strip()
    exp = int(expected_nano)
    created = created_at if created_at is None or created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    expires = expires_at if expires_at is None or expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    expires_grace = (expires + timedelta(minutes=10)) if expires is not None else None

    underpaid_max = 0

    for tx in txs:
        if tx.get("success") is False:
            continue
        tx_utime = tx.get("utime")
        tx_dt: datetime | None = None
        if isinstance(tx_utime, (int, float)):
            tx_dt = datetime.fromtimestamp(float(tx_utime), tz=timezone.utc)
        if created is not None and tx_dt is not None and tx_dt < created:
            continue
        if expires_grace is not None and tx_dt is not None and tx_dt > expires_grace:
            continue
        c = extract_ton_transfer_comment(tx)
        if not c or c.strip() != exp_c:
            continue
        val = int(extract_incoming_value_nano(tx) or 0)
        h_raw = tx.get("hash") or tx.get("tx_hash")
        if not isinstance(h_raw, str) or not h_raw.strip():
            continue
        hs = h_raw.strip()
        if val >= exp:
            if is_tx_consumed is not None and await is_tx_consumed(hs):
                logger.info("payment_candidate_consumed tx_hash=%s", hs[:16])
                continue
            return TonPaymentMatchResult(status="paid", tx_hash=hs, actual_nano=val, expected_nano=exp)
        if val > underpaid_max:
            underpaid_max = val

    if underpaid_max > 0:
        return TonPaymentMatchResult(
            status="underpaid",
            tx_hash=None,
            actual_nano=underpaid_max,
            expected_nano=exp,
        )
    return TonPaymentMatchResult(status="not_found", expected_nano=exp)


async def find_incoming_payment_tx_hash(
    settings: Settings,
    *,
    receiver_address: str,
    expected_nano: int,
    expected_comment: str,
    is_tx_consumed: Callable[[str], Awaitable[bool]] | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> str | None:
    """Обратная совместимость: только успешное совпадение (в т.ч. переплата)."""
    r = await match_incoming_payment(
        settings,
        receiver_address=receiver_address,
        expected_nano=expected_nano,
        expected_comment=expected_comment,
        is_tx_consumed=is_tx_consumed,
        created_at=created_at,
        expires_at=expires_at,
    )
    return r.tx_hash if r.status == "paid" else None

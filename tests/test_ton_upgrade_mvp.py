"""MVP: карусель тарифов, TON invoice, проверка оплаты через TonAPI (моки)."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import ton_upgrade
from app.bot.handlers.ton_upgrade import _carousel_keyboard, _finalize_payment_if_matched
from app.bot.mvp_setup import MVP_HELP, MVP_WELCOME
from app.config import Settings
from app.services import nft_check_limits
from app.services import ton_payment_verify
from app.services.ton_payment_verify import TonPaymentMatchResult
from app.services.plan_catalog import PLAN_ORDER, carousel_body, generate_invoice_comment
from app.services.ton_transaction_parse import extract_ton_transfer_comment


def _minimal_settings(**kw: object) -> Settings:
    base = dict(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        tonapi_enabled=True,
        tonapi_api_key="k",
        plan_pro_price_ton=2.0,
        plan_sniper_price_ton=7.0,
        plan_pro_duration_days=30,
        plan_sniper_duration_days=30,
    )
    base.update(kw)
    return Settings(**base)


def test_upgrade_carousel_shows_plans() -> None:
    settings = _minimal_settings()
    for key in PLAN_ORDER:
        body = carousel_body(key, settings)
        if key == "free":
            assert "Free" in body
            assert "бесплатно" in body.lower()
        elif key == "pro":
            assert "Pro" in body
            assert f"{settings.plan_pro_price_ton:g} TON" in body
        else:
            assert "Sniper" in body
            assert f"{settings.plan_sniper_price_ton:g} TON" in body
    kb = _carousel_keyboard("pro", current_user_plan="free", lang="ru")
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Купить" in t for t in labels)
    assert any("➡️" in t for t in labels)
    kb_f = _carousel_keyboard("free", current_user_plan="free", lang="ru")
    lab_f = [b.text for row in kb_f.inline_keyboard for b in row]
    assert any("Текущий план" in t for t in lab_f)
    assert any("➡️" in t for t in lab_f)


@pytest.mark.asyncio
async def test_upgrade_next_prev_callbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ton_upgrade, "get_settings", lambda: _minimal_settings())

    class FakeUserRepo:
        async def get_or_create(self, *_args: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(plan="free")

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(ton_upgrade, "SessionLocal", lambda: CM())
    monkeypatch.setattr(ton_upgrade, "UserRepository", lambda _s: FakeUserRepo())

    msg = MagicMock()
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()
    q = MagicMock()
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.message = msg
    q.data = "upgrade:next:free"
    await ton_upgrade.cb_upgrade_next(q)
    msg.edit_text.assert_awaited()
    assert "Pro" in msg.edit_text.await_args.args[0]

    msg2 = MagicMock()
    msg2.edit_text = AsyncMock(side_effect=RuntimeError("no edit"))
    msg2.answer = AsyncMock()
    q2 = MagicMock()
    q2.from_user = MagicMock(id=1, username="u")
    q2.answer = AsyncMock()
    q2.message = msg2
    q2.data = "upgrade:prev:pro"
    await ton_upgrade.cb_upgrade_prev(q2)
    msg2.answer.assert_awaited()


@pytest.mark.asyncio
async def test_buy_plan_creates_pending_payment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings(
        ton_payment_enabled=True,
        ton_payment_receiver_address="UQRECVTESTADDR01234567890123456789012",
    )
    monkeypatch.setattr(ton_upgrade, "get_settings", lambda: settings)
    created: dict[str, object] = {}

    class FakePayRepo:
        async def create_pending(self, **kw: object) -> SimpleNamespace:
            created.update(kw)
            return SimpleNamespace(id=42, **kw)

    class FakeUserRepo:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=7, plan="free", language_code="ru")

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(ton_upgrade, "SessionLocal", lambda: CM())
    monkeypatch.setattr(ton_upgrade, "UserRepository", lambda _s: FakeUserRepo())
    monkeypatch.setattr(ton_upgrade, "TonSubscriptionPaymentRepository", lambda _s: FakePayRepo())
    monkeypatch.setattr(ton_upgrade.secrets, "token_hex", lambda _n: "abcdef")

    q = MagicMock()
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.data = "upgrade:buy:pro"
    msg = MagicMock()
    msg.answer = AsyncMock()
    q.message = msg
    await ton_upgrade.cb_upgrade_buy(q)

    assert created.get("plan") == "pro"
    assert created.get("amount_ton") == 2.0
    assert str(created.get("comment", "")).startswith("GS-PRO-")
    assert created["receiver_address"] == settings.ton_payment_receiver_address
    assert created.get("expires_at") is not None


@pytest.mark.asyncio
async def test_create_invoice_unknown_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings(
        ton_payment_enabled=True,
        ton_payment_receiver_address="UQRECVTESTADDR01234567890123456789012",
    )
    monkeypatch.setattr(ton_upgrade, "get_settings", lambda: settings)

    class FakePayRepo:
        async def create_pending(self, **_kw: object) -> SimpleNamespace:
            raise AssertionError("must not create invoice for bad plan")

    class FakeUserRepo:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=7, plan="free", language_code="ru")

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(ton_upgrade, "SessionLocal", lambda: CM())
    monkeypatch.setattr(ton_upgrade, "UserRepository", lambda _s: FakeUserRepo())
    monkeypatch.setattr(ton_upgrade, "TonSubscriptionPaymentRepository", lambda _s: FakePayRepo())

    q = MagicMock()
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.data = "upgrade:buy:bad"
    q.message = MagicMock()
    await ton_upgrade.cb_upgrade_buy(q)
    assert q.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_create_invoice_free_plan_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings(
        ton_payment_enabled=True,
        ton_payment_receiver_address="UQRECVTESTADDR01234567890123456789012",
    )
    monkeypatch.setattr(ton_upgrade, "get_settings", lambda: settings)

    class FakeUserRepo:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=7, plan="free", language_code="ru")

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(ton_upgrade, "SessionLocal", lambda: CM())
    monkeypatch.setattr(ton_upgrade, "UserRepository", lambda _s: FakeUserRepo())

    q = MagicMock()
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.data = "upgrade:buy:free"
    q.message = MagicMock()
    await ton_upgrade.cb_upgrade_buy(q)
    assert q.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_create_invoice_missing_wallet_friendly(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings(ton_payment_enabled=True, ton_payment_receiver_address="")
    monkeypatch.setattr(ton_upgrade, "get_settings", lambda: settings)

    class FakeUserRepo:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=7, plan="free", language_code="ru")

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(ton_upgrade, "SessionLocal", lambda: CM())
    monkeypatch.setattr(ton_upgrade, "UserRepository", lambda _s: FakeUserRepo())

    q = MagicMock()
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.data = "upgrade:buy:pro"
    q.message = MagicMock()
    await ton_upgrade.cb_upgrade_buy(q)
    assert "временно недоступна" in q.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_payment_instruction_contains_address_amount_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings(
        ton_payment_enabled=True,
        ton_payment_receiver_address="UQINSTRADDR0000000000000000000001",
    )
    monkeypatch.setattr(ton_upgrade, "get_settings", lambda: settings)

    class FakePayRepo:
        async def create_pending(self, **kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=99, **kw)

    class FakeUserRepo:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=7, plan="free", language_code="ru")

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(ton_upgrade, "SessionLocal", lambda: CM())
    monkeypatch.setattr(ton_upgrade, "UserRepository", lambda _s: FakeUserRepo())
    monkeypatch.setattr(ton_upgrade, "TonSubscriptionPaymentRepository", lambda _s: FakePayRepo())

    q = MagicMock()
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.data = "upgrade:buy:pro"
    msg = MagicMock()
    msg.answer = AsyncMock()
    q.message = msg
    await ton_upgrade.cb_upgrade_buy(q)
    text = msg.answer.await_args.args[0]
    assert "UQINSTRADDR0000000000000000000001" in text
    assert f"{settings.plan_pro_price_ton:g}" in text
    assert "GS-PRO-" in text
    kb = msg.answer.await_args.kwargs.get("reply_markup")
    assert kb is not None
    flat = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Проверить оплату" in t for t in flat)


def _wire_finalize_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: Settings,
    pay: SimpleNamespace,
    find_hash: str | None,
    actual_nano: int | None = None,
) -> AsyncMock:
    exp_nano = int(pay.amount_nano)

    async def _match(*_a: object, **kw: object) -> TonPaymentMatchResult:
        _ = kw.get("is_tx_consumed")
        if not find_hash:
            return TonPaymentMatchResult(status="not_found", expected_nano=exp_nano)
        act = int(actual_nano) if actual_nano is not None else exp_nano
        return TonPaymentMatchResult(status="paid", tx_hash=find_hash, actual_nano=act, expected_nano=exp_nano)

    monkeypatch.setattr(ton_upgrade, "match_incoming_payment", _match)

    class TonR:
        def __init__(self, p: SimpleNamespace) -> None:
            self.p = p

        async def get_by_id_for_user(self, pid: int, uid: int) -> SimpleNamespace | None:
            return self.p if pid == self.p.id and uid == 7 else None

        async def is_tx_consumed(self, h: str) -> bool:
            return h in getattr(self.p, "_consumed", set())

        async def mark_expired(self, row: SimpleNamespace) -> None:
            row.status = "expired"

        async def finalize_paid_and_record_tx(
            self, row: SimpleNamespace, tx_hash: str, paid_at: dt.datetime
        ) -> None:
            row.status = "paid"
            row.tx_hash = tx_hash
            if not hasattr(self.p, "_consumed"):
                self.p._consumed = set()
            self.p._consumed.add(tx_hash)

    class UR:
        async def get_or_create(self, tid: int, uname: str | None) -> SimpleNamespace:
            return SimpleNamespace(id=7, plan="free", plan_expires_at=None, language_code="ru")

        async def get_by_id(self, uid: int) -> SimpleNamespace:
            return SimpleNamespace(id=7, plan="pro", language_code="ru")

    class CM:
        def __init__(self, p: SimpleNamespace) -> None:
            self.pay = p

        async def __aenter__(self) -> CM:
            return self

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(ton_upgrade, "SessionLocal", lambda: CM(pay))
    monkeypatch.setattr(ton_upgrade, "UserRepository", lambda _session: UR())
    monkeypatch.setattr(ton_upgrade, "TonSubscriptionPaymentRepository", lambda session: TonR(session.pay))
    grant = AsyncMock()
    monkeypatch.setattr(ton_upgrade, "grant_entitlement", grant)
    monkeypatch.setattr(
        ton_upgrade,
        "get_effective_entitlement",
        AsyncMock(return_value={"expires_at": None, "plan": "free"}),
    )
    monkeypatch.setattr(ton_upgrade, "sync_user_plan_from_entitlement", AsyncMock())

    class FakeBill:
        async def create_billing_event(self, **kw: object) -> None:
            return None

    monkeypatch.setattr(ton_upgrade, "BillingRepository", lambda _s: FakeBill())
    monkeypatch.setattr(ton_upgrade, "get_settings", lambda: settings)
    return grant


@pytest.mark.asyncio
async def test_check_payment_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    pay = SimpleNamespace(
        id=1,
        status="pending",
        expires_at=exp,
        receiver_address="UQX",
        amount_nano=2_000_000_000,
        comment="GS-PRO-AAA",
        plan="pro",
        amount_ton=2.0,
    )
    grant = _wire_finalize_mocks(monkeypatch, settings=_minimal_settings(), pay=pay, find_hash=None)
    text, _ok = await _finalize_payment_if_matched(1, 1, "u")
    assert "не найдена" in text
    grant.assert_not_called()


@pytest.mark.asyncio
async def test_check_payment_found_activates_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    pay = SimpleNamespace(
        id=2,
        status="pending",
        expires_at=exp,
        receiver_address="UQX",
        amount_nano=2_000_000_000,
        comment="GS-PRO-BBB",
        plan="pro",
        amount_ton=2.0,
    )
    grant = _wire_finalize_mocks(monkeypatch, settings=_minimal_settings(), pay=pay, find_hash="txfound1")
    text, ok = await _finalize_payment_if_matched(2, 1, "u")
    assert ok
    assert "Оплата найдена" in text
    assert "План активирован" in text
    grant.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_payment_overpay_stores_amounts_in_billing_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    pay = SimpleNamespace(
        id=200,
        status="pending",
        expires_at=exp,
        receiver_address="UQX",
        amount_nano=2_000_000_000,
        comment="GS-PRO-OVR",
        plan="pro",
        amount_ton=2.0,
    )
    grant = _wire_finalize_mocks(
        monkeypatch,
        settings=_minimal_settings(),
        pay=pay,
        find_hash="txover",
        actual_nano=5_000_000_000,
    )
    captured: dict[str, object] = {}

    class FakeBill:
        async def create_billing_event(self, **kw: object) -> None:
            captured.update(kw)

    monkeypatch.setattr(ton_upgrade, "BillingRepository", lambda _s: FakeBill())
    text, ok = await _finalize_payment_if_matched(200, 1, "u")
    assert ok
    assert "План активирован" in text
    meta = str(captured.get("metadata_json") or "")
    assert "5000000000" in meta
    assert "2000000000" in meta
    grant.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_payment_underpaid_user_message(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    pay = SimpleNamespace(
        id=201,
        status="pending",
        expires_at=exp,
        receiver_address="UQX",
        amount_nano=2_000_000_000,
        comment="GS-PRO-LOW",
        plan="pro",
        amount_ton=2.0,
    )

    _wire_finalize_mocks(monkeypatch, settings=_minimal_settings(), pay=pay, find_hash=None)

    async def _match(*_a: object, **_kw: object) -> TonPaymentMatchResult:
        return TonPaymentMatchResult(
            status="underpaid",
            actual_nano=1_000_000_000,
            expected_nano=2_000_000_000,
        )

    monkeypatch.setattr(ton_upgrade, "match_incoming_payment", _match)
    text, ok = await _finalize_payment_if_matched(201, 1, "u")
    assert ok is False
    assert "меньше нужной" in text
    assert "Нужно:" in text
    assert "Получено:" in text


@pytest.mark.asyncio
async def test_payment_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    pay = SimpleNamespace(
        id=3,
        status="pending",
        expires_at=exp,
        receiver_address="UQX",
        amount_nano=2_000_000_000,
        comment="GS-PRO-CCC",
        plan="pro",
        amount_ton=2.0,
    )
    grant = _wire_finalize_mocks(monkeypatch, settings=_minimal_settings(), pay=pay, find_hash="txsame")
    await _finalize_payment_if_matched(3, 1, "u")
    assert pay.status == "paid"
    text2, _ok2 = await _finalize_payment_if_matched(3, 1, "u")
    assert grant.call_count == 1
    assert "уже" in text2.lower()


@pytest.mark.asyncio
async def test_payment_tx_replay_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    pay = SimpleNamespace(
        id=33,
        status="pending",
        expires_at=exp,
        receiver_address="UQX",
        amount_nano=2_000_000_000,
        comment="GS-PRO-REPLAY",
        plan="pro",
        amount_ton=2.0,
    )
    grant = _wire_finalize_mocks(monkeypatch, settings=_minimal_settings(), pay=pay, find_hash="txreplay")
    _text1, ok1 = await _finalize_payment_if_matched(33, 1, "u")
    text2, ok2 = await _finalize_payment_if_matched(33, 1, "u")
    assert ok1 is True
    assert ok2 is True
    assert "уже" in text2.lower()
    assert grant.call_count == 1


@pytest.mark.asyncio
async def test_wrong_comment_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings()

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return [
            {
                "success": True,
                "hash": "h1",
                "in_msg": {"value": 4_000_000_000, "comment": "OTHER-COMMENT"},
            }
        ]

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)
    h = await ton_payment_verify.find_incoming_payment_tx_hash(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-PRO-OK",
    )
    assert h is None


@pytest.mark.asyncio
async def test_wrong_amount_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings()

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return [
            {
                "success": True,
                "hash": "h2",
                "in_msg": {"value": 1_000_000_000, "comment": "GS-PRO-OK"},
            }
        ]

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)
    m = await ton_payment_verify.match_incoming_payment(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-PRO-OK",
    )
    assert m.status == "underpaid"
    assert m.actual_nano == 1_000_000_000


@pytest.mark.asyncio
async def test_payment_accepts_exact_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings()

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return [
            {
                "success": True,
                "hash": "hexact",
                "in_msg": {"value": 2_000_000_000, "comment": "GS-PAY-X"},
            }
        ]

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)
    m = await ton_payment_verify.match_incoming_payment(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-PAY-X",
    )
    assert m.status == "paid"
    assert m.tx_hash == "hexact"
    assert m.actual_nano == 2_000_000_000


@pytest.mark.asyncio
async def test_payment_accepts_overpayment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings()

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return [
            {
                "success": True,
                "hash": "hover",
                "in_msg": {"value": 5_000_000_000, "comment": "GS-PAY-Y"},
            }
        ]

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)
    m = await ton_payment_verify.match_incoming_payment(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-PAY-Y",
    )
    assert m.status == "paid"
    assert m.actual_nano == 5_000_000_000
    assert m.expected_nano == 2_000_000_000


@pytest.mark.asyncio
async def test_payment_rejects_underpayment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings()

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return [
            {
                "success": True,
                "hash": "hunder",
                "in_msg": {"value": 1_500_000_000, "comment": "GS-PAY-Z"},
            }
        ]

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)
    m = await ton_payment_verify.match_incoming_payment(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-PAY-Z",
    )
    assert m.status == "underpaid"
    assert m.tx_hash is None


@pytest.mark.asyncio
async def test_payment_overpayment_tx_consumed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings()

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return [
            {
                "success": True,
                "hash": "txdup",
                "in_msg": {"value": 5_000_000_000, "comment": "GS-PAY-DUP"},
            }
        ]

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)

    async def not_consumed(_h: str) -> bool:
        return False

    m1 = await ton_payment_verify.match_incoming_payment(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-PAY-DUP",
        is_tx_consumed=not_consumed,
    )
    assert m1.status == "paid"

    async def consumed_yes(h: str) -> bool:
        return h == "txdup"

    m2 = await ton_payment_verify.match_incoming_payment(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-PAY-DUP",
        is_tx_consumed=consumed_yes,
    )
    assert m2.status == "not_found"


@pytest.mark.asyncio
async def test_payment_no_api_key_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "TOP_SECRET_TONAPI_KEY_NO_LEAK"
    settings = _minimal_settings(tonapi_api_key=secret)

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return []

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)
    out = await ton_payment_verify.match_incoming_payment(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-X",
    )
    blob = str(out)
    assert secret not in blob
    assert out.status == "not_found"


@pytest.mark.asyncio
async def test_expired_invoice_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
    pay = SimpleNamespace(
        id=4,
        status="pending",
        expires_at=past,
        receiver_address="UQX",
        amount_nano=2_000_000_000,
        comment="GS-PRO-DDD",
        plan="pro",
        amount_ton=2.0,
    )
    grant = _wire_finalize_mocks(monkeypatch, settings=_minimal_settings(), pay=pay, find_hash="txneverused")
    text, _ok = await _finalize_payment_if_matched(4, 1, "u")
    assert pay.status == "expired"
    assert "ист" in text.lower()
    grant.assert_not_called()


@pytest.mark.asyncio
async def test_find_skips_consumed_tx(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _minimal_settings()

    async def fetch(*_a: object, **_k: object) -> list[dict]:
        return [
            {"success": True, "hash": "h1", "in_msg": {"value": 4_000_000_000, "comment": "GS-OK"}},
            {"success": True, "hash": "h2", "in_msg": {"value": 4_000_000_000, "comment": "GS-OK"}},
        ]

    monkeypatch.setattr(ton_payment_verify, "fetch_recent_transactions", fetch)

    async def consumed(h: str) -> bool:
        return h == "h1"

    h = await ton_payment_verify.find_incoming_payment_tx_hash(
        settings,
        receiver_address="UQANY",
        expected_nano=2_000_000_000,
        expected_comment="GS-OK",
        is_tx_consumed=consumed,
    )
    assert h == "h2"


def test_no_seed_private_key_texts() -> None:
    settings = _minimal_settings()
    blobs = [MVP_WELCOME, MVP_HELP]
    for k in PLAN_ORDER:
        blobs.append(carousel_body(k, settings))
    blobs.append(
        "💎 Оплата тарифа Pro\n\n"
        "• бот не просит seed, private key или доступ к кошельку.\n"
    )
    positives = (
        "пришли seed",
        "введи seed",
        "отправь seed",
        "your seed phrase",
        "private key:",
        "подключи кошелёк",
        "connect wallet",
    )
    for blob in blobs:
        low = blob.lower()
        for p in positives:
            assert p not in low, (p, blob[:80])


def test_generate_invoice_comment_format() -> None:
    c = generate_invoice_comment("pro", "8F3K2A")
    assert c == "GS-PRO-8F3K2A"


def test_extract_ton_transfer_comment_mock() -> None:
    tx = {"in_msg": {"comment": "GS-PRO-XX"}}
    assert extract_ton_transfer_comment(tx) == "GS-PRO-XX"
    assert extract_ton_transfer_comment({}) is None


@pytest.mark.asyncio
async def test_limits_show_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    class U:
        id = 1
        plan = "free"
        role = ""

    class UC:
        async def get_or_create(self, *_a: object, **_kw: object) -> U:
            return U()

    class NftR:
        async def get_count(self, *_a: object, **_kw: object) -> int:
            return 3

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr(nft_check_limits, "SessionLocal", lambda: CM())
    monkeypatch.setattr(nft_check_limits, "UserRepository", lambda _s: UC())
    monkeypatch.setattr(nft_check_limits, "UserNftCheckDayRepository", lambda _s: NftR())
    monkeypatch.setattr(nft_check_limits, "checks_per_day_limit", lambda _u: 3)
    monkeypatch.setattr(nft_check_limits, "get_bonus_checks", AsyncMock(return_value=0))

    msg = MagicMock()
    msg.answer = AsyncMock()
    ok = await nft_check_limits.assert_nft_daily_check_allowed(msg, 1, "u")
    assert ok is False
    msg.answer.assert_awaited()
    rmk = msg.answer.await_args.kwargs.get("reply_markup")
    assert rmk is not None
    flat = [b.text for row in rmk.inline_keyboard for b in row]
    assert any("Upgrade" in t for t in flat)

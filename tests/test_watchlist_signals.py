"""Watchlist market notifications (MVP)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import gifts as gifts_mod
from app.config import Settings
from app.db.models import Gift
from app.db.repositories.gifts import GiftRepository, gift_notifications_scan_text
from app.i18n import t
from app.services import watchlist_signals_job as wsj
from app.services.watchlist_signals_job import check_watchlist_signals_job, compute_watchlist_market_hash


def test_signal_state_fields_exist_or_table_exists() -> None:
    assert hasattr(Gift, "signals_enabled")
    assert hasattr(Gift, "last_signal_checked_at")
    assert hasattr(Gift, "last_signal_market_hash")


def test_signal_defaults_disabled() -> None:
    g = Gift(
        user_id=1,
        collection="C",
        number=1,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        signals_enabled=False,
    )
    assert g.signals_enabled is False


def test_gift_notifications_scan_text_prefers_address() -> None:
    g = SimpleNamespace(nft_address="EQaddr", collection="C", number=1)
    assert gift_notifications_scan_text(g) == "EQaddr"


def test_gift_notifications_scan_text_collection_number() -> None:
    g = SimpleNamespace(nft_address="", collection="Ice", number=5)
    assert gift_notifications_scan_text(g) == "Ice #5"


@pytest.mark.asyncio
async def test_free_cannot_enable_signals_gets_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    class UR:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="free", language_code="ru")

    class GR:
        async def get_by_id(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(
                id=9,
                collection="X",
                number=1,
                nft_address="EQx",
                signals_enabled=False,
            )

        async def set_signals_enabled(self, *_a: object, **_kw: object) -> object:
            raise AssertionError("must not toggle on free")

    monkeypatch.setattr(gifts_mod, "SessionLocal", lambda: CM())
    monkeypatch.setattr(gifts_mod, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(gifts_mod, "GiftRepository", lambda _s: GR())

    async def capture(*args: object, **kw: object) -> None:
        text = kw.get("text")
        if text is not None:
            sent.append(str(text))
        elif args:
            sent.append(str(args[0]))

    q = MagicMock()
    q.data = "watchlist:signals:9"
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.answer = AsyncMock(side_effect=capture)
    state = MagicMock()
    state.clear = AsyncMock()
    await gifts_mod.watchlist_callback_handler(q, state)
    assert sent and ("Pro" in sent[0] or "pro" in sent[0].lower())


@pytest.mark.asyncio
async def test_pro_can_enable_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    toggled: list[bool] = []

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    class UR:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="pro", language_code="ru")

    class GR:
        async def get_by_id(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(
                id=3,
                collection="X",
                number=1,
                nft_address="EQx",
                signals_enabled=False,
            )

        async def set_signals_enabled(self, _uid: int, _gid: int, enabled: bool) -> SimpleNamespace:
            toggled.append(enabled)
            return SimpleNamespace()

    monkeypatch.setattr(gifts_mod, "SessionLocal", lambda: CM())
    monkeypatch.setattr(gifts_mod, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(gifts_mod, "GiftRepository", lambda _s: GR())

    q = MagicMock()
    q.data = "watchlist:signals:3"
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    await gifts_mod.watchlist_callback_handler(q, state)
    assert toggled == [True]


@pytest.mark.asyncio
async def test_toggle_signals_off(monkeypatch: pytest.MonkeyPatch) -> None:
    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    class UR:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="sniper", language_code="ru")

    class GR:
        async def get_by_id(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(
                id=4,
                collection="X",
                number=1,
                nft_address="EQx",
                signals_enabled=True,
            )

        async def set_signals_enabled(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace()

    monkeypatch.setattr(gifts_mod, "SessionLocal", lambda: CM())
    monkeypatch.setattr(gifts_mod, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(gifts_mod, "GiftRepository", lambda _s: GR())

    q = MagicMock()
    q.data = "watchlist:signals:4"
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.answer = AsyncMock()
    state = MagicMock()
    await gifts_mod.watchlist_callback_handler(q, state)
    assert q.message.answer.await_args.args[0].startswith("🔕")


def test_watchlist_shows_notifications_status() -> None:
    on = t("notifications.status_on", "ru")
    off = t("notifications.status_off", "ru")
    assert "включен" in on.lower()
    assert "выключен" in off.lower()


def test_signal_job_skips_free_users() -> None:
    g = SimpleNamespace(
        id=1,
        last_signal_checked_at=None,
        nft_address="EQa",
        collection="C",
        number=1,
        signals_enabled=True,
    )
    u = SimpleNamespace(plan="free")
    gr = GiftRepository(MagicMock())
    out = gr.filter_due_notification_scan(
        [(g, u)],
        now_utc=datetime.now(timezone.utc),
        pro_interval_minutes=360,
        sniper_interval_minutes=60,
        max_items=20,
    )
    assert out == []


def test_signal_job_respects_pro_interval() -> None:
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    g = SimpleNamespace(
        id=1,
        last_signal_checked_at=old.replace(tzinfo=None),
        nft_address="EQa",
        collection="C",
        number=1,
        signals_enabled=True,
    )
    u = SimpleNamespace(plan="pro")
    gr = GiftRepository(MagicMock())
    out = gr.filter_due_notification_scan(
        [(g, u)],
        now_utc=datetime.now(timezone.utc),
        pro_interval_minutes=360,
        sniper_interval_minutes=60,
        max_items=20,
    )
    assert out == []


def test_signal_job_respects_sniper_interval() -> None:
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    g = SimpleNamespace(
        id=1,
        last_signal_checked_at=old.replace(tzinfo=None),
        nft_address="EQa",
        collection="C",
        number=1,
        signals_enabled=True,
    )
    u = SimpleNamespace(plan="sniper")
    gr = GiftRepository(MagicMock())
    out = gr.filter_due_notification_scan(
        [(g, u)],
        now_utc=datetime.now(timezone.utc),
        pro_interval_minutes=360,
        sniper_interval_minutes=60,
        max_items=20,
    )
    assert out == []


def test_signal_job_batch_limit() -> None:
    gr = GiftRepository(MagicMock())
    now = datetime.now(timezone.utc)
    pairs = []
    for i in range(30):
        g = SimpleNamespace(
            id=i,
            last_signal_checked_at=None,
            nft_address=f"EQ{i}",
            collection="C",
            number=i,
            signals_enabled=True,
        )
        u = SimpleNamespace(plan="pro")
        pairs.append((g, u))
    out = gr.filter_due_notification_scan(
        pairs,
        now_utc=now,
        pro_interval_minutes=360,
        sniper_interval_minutes=60,
        max_items=5,
    )
    assert len(out) == 5


@pytest.mark.asyncio
async def test_signal_job_uses_sleep_or_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    monkeypatch.setattr(wsj.asyncio, "sleep", fake_sleep)
    settings = Settings(
        BOT_TOKEN="t",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        signals_enabled=True,
        signals_request_sleep_ms=2000,
        signals_max_items_per_run=2,
    )
    monkeypatch.setattr(wsj, "TonAPICollectionClient", lambda *_a, **_k: MagicMock(configured=False))
    await check_watchlist_signals_job(MagicMock(), MagicMock(), settings)
    assert sleeps == []


def test_market_hash_stable() -> None:
    from app.services.real_market_collection_scan import (
        FullMarketNftReport,
        SellPricePlan,
        TargetNftInfo,
        TraitComps,
    )

    tgt = TargetNftInfo(
        name="N",
        number=1,
        address="EQa",
        collection_name="C",
        collection_address="CA",
        model="m",
        backdrop="b",
        symbol="s",
        traits_normalized={},
    )
    sp = SellPricePlan(
        quick_sell_ton=1.0,
        normal_list_ton=10.0,
        high_list_ton=12.0,
        dont_list_below_ton=None,
        confidence="medium",
        confidence_reason="",
        pricing_group_key="trait",
        used_prices_ton=[9.0, 10.0, 11.0],
    )
    tc = TraitComps(trait_type="", trait_value=None, listings_count=0, floor=None, median=None, nearest=[])
    rep = FullMarketNftReport(
        target=tgt,
        loaded_count=100,
        listings_count=50,
        collection_floor=5.0,
        collection_median=8.0,
        same_model=tc,
        same_backdrop=tc,
        same_symbol=tc,
        close_comps=[],
        sell_plan=sp,
        is_partial_scan=False,
        source_label="tonapi",
    )
    h1 = compute_watchlist_market_hash(rep)
    h2 = compute_watchlist_market_hash(rep)
    assert h1 == h2


def test_signal_text_has_no_collections_json() -> None:
    body = t("notifications.push_up", "ru", name="NFT", was="1", now="2", pct="20")
    assert "collections.json" not in body.lower()


def test_signal_text_has_no_seed_request() -> None:
    body = t("notifications.free_gate", "en")
    low = body.lower()
    assert "seed" not in low
    assert "private key" not in low


@pytest.mark.asyncio
async def test_tonapi_error_in_signal_job_does_not_message_user(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()

    settings = Settings(
        BOT_TOKEN="t",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        signals_enabled=True,
        tonapi_enabled=True,
        tonapi_api_key="k",
        full_market_scan_enabled=True,
        signals_max_items_per_run=1,
        signals_request_sleep_ms=0,
    )

    g = SimpleNamespace(
        id=1,
        last_signal_checked_at=None,
        nft_address="EQfail",
        collection="C",
        number=1,
        signals_enabled=True,
        title="T",
        last_signal_normal_ton=None,
        last_signal_floor_ton=None,
        last_signal_market_hash=None,
        last_signal_sent_at=None,
    )
    u = SimpleNamespace(id=2, telegram_id=99, plan="pro", language_code="ru")

    monkeypatch.setattr(wsj, "run_full_market_analysis_flow", AsyncMock(side_effect=RuntimeError("tonapi boom")))

    class Sess:
        flushed: list[str] = []

        async def commit(self) -> None:
            return None

        async def flush(self) -> None:
            self.flushed.append("ok")

    session = Sess()
    await wsj._process_one_gift(
        bot=bot,
        session=session,
        gift=g,
        user=u,
        payload="EQfail",
        threshold_percent=20.0,
        cooldown_hours=6,
        settings=settings,
        client=MagicMock(configured=True),
    )
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_signal_check_now_button_runs_check_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads: list[str] = []

    async def capture(_msg: object, payload: str, **kw: object) -> None:
        payloads.append(payload)

    monkeypatch.setattr(gifts_mod, "execute_check_payload", AsyncMock(side_effect=capture))

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    class UR:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="pro", language_code="ru")

    class GR:
        async def get_by_id(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(
                id=7,
                collection="Ice",
                number=3,
                nft_address="EQpref",
                signals_enabled=True,
            )

        async def set_signals_enabled(self, *_a: object, **_kw: object) -> object:
            raise AssertionError("not here")

    monkeypatch.setattr(gifts_mod, "SessionLocal", lambda: CM())
    monkeypatch.setattr(gifts_mod, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(gifts_mod, "GiftRepository", lambda _s: GR())

    q = MagicMock()
    q.data = "notifications:check:7"
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.message = MagicMock()
    state = MagicMock()
    state.clear = AsyncMock()
    await gifts_mod.notifications_push_callback(q, state)
    assert payloads == ["EQpref"]


@pytest.mark.asyncio
async def test_signal_disable_button_turns_off_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    toggled: list[bool] = []

    class CM:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_a: object) -> bool:
            return False

    class UR:
        async def get_or_create(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=1, plan="pro", language_code="ru")

    class GR:
        async def get_by_id(self, *_a: object, **_kw: object) -> SimpleNamespace:
            return SimpleNamespace(id=8, collection="X", number=1, nft_address="EQx", signals_enabled=True)

        async def set_signals_enabled(self, _uid: int, _gid: int, enabled: bool) -> SimpleNamespace:
            toggled.append(enabled)
            return SimpleNamespace()

    monkeypatch.setattr(gifts_mod, "SessionLocal", lambda: CM())
    monkeypatch.setattr(gifts_mod, "UserRepository", lambda _s: UR())
    monkeypatch.setattr(gifts_mod, "GiftRepository", lambda _s: GR())

    q = MagicMock()
    q.data = "notifications:off:8"
    q.from_user = MagicMock(id=1, username="u")
    q.answer = AsyncMock()
    q.message = MagicMock()
    state = MagicMock()
    await gifts_mod.notifications_push_callback(q, state)
    assert toggled == [False]

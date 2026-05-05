"""Периодические уведомления по NFT из «Мой список» (TonAPI + full market, без mock)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.repositories.gifts import GiftRepository, gift_notifications_scan_text
from app.services.feature_limits import normalize_plan_for_limits
from app.services.real_market_collection_scan import FullMarketNftReport, run_full_market_analysis_flow
from app.services.tonapi_collection_client import TonAPICollectionClient

if TYPE_CHECKING:
    from aiogram import Bot

    from app.config import Settings
    from app.db.models import Gift, User

logger = logging.getLogger(__name__)

CB_NOTIFICATIONS_CHECK = "notifications:check"
CB_NOTIFICATIONS_OFF = "notifications:off"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def compute_watchlist_market_hash(report: FullMarketNftReport) -> str:
    sp = report.sell_plan
    addr = (report.target.address or "").strip()
    n = round(float(sp.normal_list_ton or 0.0), 2)
    fl = round(float(report.collection_floor or 0.0), 2)
    grp = (sp.pricing_group_key or "")[:48]
    conf = int(sp.confidence_score or 0)
    tops = sorted(float(x) for x in (sp.used_prices_ton or [])[:8])
    top_s = ",".join(str(round(x, 2)) for x in tops)
    raw = f"{addr}|{n}|{fl}|{grp}|{conf}|{top_s}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _low_confidence_collection_market(report: FullMarketNftReport, settings: Any) -> bool:
    sp = report.sell_plan
    if (sp.pricing_group_key or "") != "collection_market":
        return False
    min_c = int(getattr(settings, "signals_min_confidence_collection_market", 55) or 55)
    return int(sp.confidence_score or 0) < min_c


def _threshold_for_user_plan(user_plan: str, settings: Any) -> float:
    p = normalize_plan_for_limits(user_plan)
    if p == "sniper":
        return float(settings.signals_sniper_threshold_percent)
    return float(settings.signals_pro_threshold_percent)


def notification_signal_keyboard(*, gift_id: int, btn_check: str, btn_off: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=btn_check, callback_data=f"{CB_NOTIFICATIONS_CHECK}:{gift_id}"),
                InlineKeyboardButton(text=btn_off, callback_data=f"{CB_NOTIFICATIONS_OFF}:{gift_id}"),
            ]
        ]
    )


async def check_watchlist_signals_job(bot: "Bot", session_maker: Any, settings: "Settings") -> None:
    if not getattr(settings, "signals_enabled", True):
        return
    if not settings.tonapi_enabled or not str(settings.tonapi_api_key or "").strip():
        logger.debug("signal_job_skipped reason=no_tonapi")
        return
    if not settings.full_market_scan_enabled:
        logger.debug("signal_job_skipped reason=full_market_disabled")
        return

    logger.info("signal_job_started")
    client = TonAPICollectionClient(settings)
    if not client.configured:
        logger.warning("signal_job_skipped reason=tonapi_client_not_configured")
        return

    now = _utcnow()
    max_items = max(1, int(settings.signals_max_items_per_run))
    sleep_ms = max(0, int(settings.signals_request_sleep_ms))

    async with session_maker() as session:
        repo = GiftRepository(session)
        pairs = await repo.list_gifts_for_notifications_scan(prefetch=500)
        due = repo.filter_due_notification_scan(
            pairs,
            now_utc=now,
            pro_interval_minutes=int(settings.signals_pro_interval_minutes),
            sniper_interval_minutes=int(settings.signals_sniper_interval_minutes),
            max_items=max_items,
        )

    if not due:
        logger.debug("signal_job_no_due_items")
        return

    cooldown_h = max(1, int(settings.signals_min_hours_between_notifications))

    to_run: list[tuple[int, int, str, float]] = []
    for gift, user in due:
        py = gift_notifications_scan_text(gift)
        if not py:
            continue
        thr = _threshold_for_user_plan(user.plan, settings)
        to_run.append((user.id, gift.id, py, thr))

    for uid, gid, payload, threshold in to_run:
        if sleep_ms:
            await asyncio.sleep(sleep_ms / 1000.0)
        try:
            async with session_maker() as session3:
                from app.db.repositories.users import UserRepository

                gr = GiftRepository(session3)
                ur = UserRepository(session3)
                g3 = await gr.get_by_id(uid, gid)
                u3 = await ur.get_by_id(uid)
                if g3 is None or u3 is None:
                    continue
                await _process_one_gift(
                    bot=bot,
                    session=session3,
                    gift=g3,
                    user=u3,
                    payload=payload,
                    threshold_percent=threshold,
                    cooldown_hours=cooldown_h,
                    settings=settings,
                    client=client,
                )
                await session3.commit()
        except Exception:
            logger.exception("signal_tonapi_error gift_id=%s", gid)
            try:
                async with session_maker() as session_err:
                    ge = await GiftRepository(session_err).get_by_id(uid, gid)
                    if ge is not None:
                        ge.last_signal_checked_at = _naive_utc(_utcnow())
                        await session_err.commit()
            except Exception:
                logger.exception("signal_checked_touch_failed gift_id=%s", gid)


async def _process_one_gift(
    *,
    bot: "Bot",
    session: Any,
    gift: "Gift",
    user: "User",
    payload: str,
    threshold_percent: float,
    cooldown_hours: int,
    settings: "Settings",
    client: TonAPICollectionClient,
) -> None:
    from app.i18n import normalize_lang, t

    lang = normalize_lang(getattr(user, "language_code", None))

    try:
        report, err = await run_full_market_analysis_flow(payload, user, settings, client, on_progress=None)
    except Exception:
        logger.exception("signal_tonapi_error gift_id=%s", gift.id)
        gift.last_signal_checked_at = _naive_utc(_utcnow())
        await session.flush()
        return

    if err or report is None:
        logger.info("signal_tonapi_error gift_id=%s err=%s", gift.id, (err or "")[:200])
        gift.last_signal_checked_at = _naive_utc(_utcnow())
        await session.flush()
        return

    sp = report.sell_plan
    normal = sp.normal_list_ton
    now = _utcnow()

    gift.last_signal_checked_at = _naive_utc(now)

    if normal is None or float(normal) <= 0:
        logger.info("signal_skipped_low_confidence gift_id=%s reason=no_normal", gift.id)
        await session.flush()
        return

    if _low_confidence_collection_market(report, settings):
        logger.info("signal_skipped_low_confidence gift_id=%s", gift.id)
        await session.flush()
        return

    h = compute_watchlist_market_hash(report)
    prev = gift.last_signal_normal_ton
    floor = report.collection_floor

    if prev is None:
        gift.last_signal_normal_ton = float(normal)
        gift.last_signal_floor_ton = float(floor) if floor is not None else None
        gift.last_signal_market_hash = h
        await session.flush()
        logger.info("signal_baseline_saved gift_id=%s", gift.id)
        return

    if h and gift.last_signal_market_hash and h == gift.last_signal_market_hash:
        logger.info("signal_skipped_duplicate_hash gift_id=%s", gift.id)
        await session.flush()
        return

    prev_f = float(prev)
    cur_f = float(normal)
    if prev_f <= 0:
        await session.flush()
        return

    change_pct = abs(cur_f - prev_f) / prev_f * 100.0
    t_frac = threshold_percent / 100.0
    up_hit = cur_f >= prev_f * (1.0 + t_frac)
    down_hit = cur_f <= prev_f * (1.0 - t_frac)

    if not up_hit and not down_hit:
        logger.info("signal_skipped_threshold gift_id=%s change_pct=%.2f", gift.id, change_pct)
        gift.last_signal_normal_ton = cur_f
        gift.last_signal_floor_ton = float(floor) if floor is not None else gift.last_signal_floor_ton
        gift.last_signal_market_hash = h
        await session.flush()
        return

    sent_at = gift.last_signal_sent_at
    if sent_at is not None:
        sent_u = sent_at if sent_at.tzinfo else sent_at.replace(tzinfo=timezone.utc)
        if (now - sent_u).total_seconds() < cooldown_hours * 3600:
            logger.info("signal_skipped_cooldown gift_id=%s", gift.id)
            gift.last_signal_normal_ton = cur_f
            gift.last_signal_floor_ton = float(floor) if floor is not None else gift.last_signal_floor_ton
            gift.last_signal_market_hash = h
            await session.flush()
            return

    name = (gift.title or "").strip() or f"{gift.collection} #{gift.number}"
    z = change_pct
    x_s = f"{prev_f:.1f}"
    y_s = f"{cur_f:.1f}"
    z_s = f"{z:.0f}"

    if up_hit:
        body = t("notifications.push_up", lang, name=name, was=x_s, now=y_s, pct=z_s)
        log_ev = "signal_sent_up"
    else:
        body = t("notifications.push_down", lang, name=name, was=x_s, now=y_s, pct=z_s)
        log_ev = "signal_sent_down"

    kb = notification_signal_keyboard(
        gift_id=gift.id,
        btn_check=t("notifications.btn_check_now", lang),
        btn_off=t("notifications.btn_turn_off", lang),
    )
    try:
        await bot.send_message(
            chat_id=int(user.telegram_id),
            text=body,
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("signal_send_failed gift_id=%s telegram_id=%s", gift.id, user.telegram_id)
        await session.flush()
        return

    logger.info("%s gift_id=%s user_id=%s pct=%.2f", log_ev, gift.id, user.id, change_pct)
    gift.last_signal_sent_at = _naive_utc(now)
    gift.last_signal_normal_ton = cur_f
    gift.last_signal_floor_ton = float(floor) if floor is not None else gift.last_signal_floor_ton
    gift.last_signal_market_hash = h
    await session.flush()

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.config import get_settings
from app.db.repositories.beta_invites import BetaInviteRepository
from app.db.repositories.billing import BillingRepository
from app.db.repositories.product_events import ProductEventRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.services.beta_access import format_beta_gate_message, should_show_beta_gate
from app.services.entitlements import sync_user_plan_from_entitlement
from app.services.rate_limiter import check_command_rate_limit

EVENT_BY_COMMAND = {
    "/start": "start",
    "/menu": "menu_opened",
    "/home": "home_opened",
    "/examples": "examples_viewed",
    "/how_it_works": "how_it_works_viewed",
    "/quick_start": "quick_start_viewed",
    "/commands": "commands_viewed",
    "/lite_plan": "lite_plan_used",
    "/add": "gift_added",
    "/check": "check_used",
    "/deal": "deal_used",
    "/deals": "deal_used",
    "/scan": "scan_used",
    "/scan_universe": "universe_scan_used",
    "/capital_plan": "plan_viewed",
    "/capital_plan_universe": "plan_viewed",
    "/flip_plan": "flip_plan_used",
    "/budget_deals": "budget_deals_used",
    "/compound_plan": "compound_plan_used",
    "/sell_to_buy": "sell_to_buy_used",
    "/m4_plan": "m4_plan_used",
    "/upgrade": "upgrade_viewed",
    "/pay": "pay_started",
    "/payment_sent": "payment_submitted",
    "/redeem": "invite_redeemed",
    "/feedback": "feedback_created",
    "/ref": "referral_viewed",
}


class SkipEmptyMessagesMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        if isinstance(event, Message) and event.text is None:
            return None
        return await handler(event, data)


class AccessControlMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        if not hasattr(event, "text"):
            return await handler(event, data)
        if getattr(event, "text", None) is None:
            return await handler(event, data)
        if not event.text.startswith("/"):
            return await handler(event, data)

        data.setdefault("user_created_this_request", False)

        settings = get_settings()
        command = event.text.split()[0].lower()
        # /redeem must reach the handler even without beta access (invite activation).
        skip_beta_gate = command == "/redeem"
        user = None
        async with SessionLocal() as session:
            users_repo = UserRepository(session)
            user, user_created_this_request = await users_repo.get_or_create_with_created(
                event.from_user.id, event.from_user.username
            )
            data["user_created_this_request"] = user_created_this_request
            user_id = int(user.id)
            if user.is_blocked:
                await event.answer("Доступ к боту ограничен.")
                return None
            try:
                user.beta_invite_redeemed = await BetaInviteRepository(session).has_user_redemption(user_id)
            except Exception:
                user.beta_invite_redeemed = False
            try:
                entitlement = await BillingRepository(session).get_entitlement(user_id)
                if entitlement is not None:
                    user.entitlement_status = entitlement.status
                    if entitlement.status in {"active", "trialing", "grace"}:
                        user.plan = entitlement.plan
            except Exception:
                pass
            if not skip_beta_gate and should_show_beta_gate(
                user, settings, telegram_id=event.from_user.id
            ):
                await event.answer(format_beta_gate_message(settings))
                return None
            try:
                await sync_user_plan_from_entitlement(session, user)
            except Exception:
                # Billing/entitlement sync must not block command processing.
                pass
            if hasattr(users_repo, "touch_activity"):
                await users_repo.touch_activity(user_id)
            event_type = EVENT_BY_COMMAND.get(command)
            if event_type:
                try:
                    await ProductEventRepository(session).create_event(
                        user_id=user_id,
                        event_type=event_type,
                        command=command,
                        metadata_json=None,
                    )
                except Exception:
                    await session.rollback()
                    # Product analytics should never break command processing.

        ok, retry_after = check_command_rate_limit(
            user_id,
            command,
            per_minute_limit=settings.rate_limit_commands_per_minute,
            heavy_per_hour_limit=settings.rate_limit_heavy_commands_per_hour,
        )
        if not ok:
            await event.answer(f"Слишком много запросов. Подожди {retry_after} секунд.")
            return None
        return await handler(event, data)

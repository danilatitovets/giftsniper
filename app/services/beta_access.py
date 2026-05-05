from __future__ import annotations


def _env_admin_telegram_ids(settings) -> set[int]:
    raw = (getattr(settings, "admin_telegram_ids", None) or "").strip()
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}


def is_beta_access_allowed(user, settings, *, telegram_id: int | None = None) -> bool:
    role = (getattr(user, "role", "user") or "user").lower()
    if role in {"owner", "admin", "tester"}:
        return True
    if telegram_id is not None and telegram_id in _env_admin_telegram_ids(settings):
        return True
    if bool(getattr(settings, "public_bot_access", False)):
        return True
    if not bool(getattr(settings, "beta_mode", True)):
        return True
    if not bool(getattr(settings, "beta_require_invite", True)):
        return True
    # Allow users with non-free plan or known active entitlement statuses.
    if (getattr(user, "plan", "free") or "free").lower() != "free":
        return True
    ent_status = (getattr(user, "entitlement_status", "") or "").lower()
    if ent_status in {"active", "trialing", "grace", "manual"}:
        return True
    if bool(getattr(user, "beta_invite_redeemed", False)):
        return True
    return False


def should_show_beta_gate(user, settings, *, telegram_id: int | None = None) -> bool:
    return not is_beta_access_allowed(user, settings, telegram_id=telegram_id)


def format_beta_gate_message(settings) -> str:
    support = getattr(settings, "beta_support_username", "@support")
    return (
        "🔒 Сейчас закрытая бета.\n"
        "Полный доступ выдается по invite-коду.\n\n"
        "Получи invite-код у владельца и активируй через /redeem <code>.\n"
        f"Поддержка: {support}"
    )

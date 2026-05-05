from __future__ import annotations


def format_next_action(text: str) -> str:
    return f"➡️ Следующий шаг: {text}"


def format_plan_badge(plan: str) -> str:
    p = (plan or "free").lower()
    badges = {"free": "🆓 Free", "starter": "⭐ Starter", "pro": "🚀 Pro", "trader": "💼 Trader"}
    return badges.get(p, p.capitalize())


def format_risk_disclaimer_short() -> str:
    return "⚠️ Это аналитика, не финансовый совет. Прибыль не гарантируется."


def format_beta_badge() -> str:
    return "🧪 Closed Beta"


def format_locked_feature_message(feature: str, upgrade_command: str = "/upgrade") -> str:
    return f"🔒 {feature} доступно на платных планах. Открой возможности через {upgrade_command}."

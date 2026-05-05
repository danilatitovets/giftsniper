"""Stage 35: no aggressive profit guarantees or wallet/seed prompts in UX strings."""

import re

from app.bot.messages import (
    EXAMPLES_TEXT,
    FREE_BUDGET_DEALS_TEASER,
    FREE_FLIP_PLAN_TEASER,
    HOW_IT_WORKS_TEXT,
    QUICK_START_TEXT,
    UNKNOWN_PLAIN_TEXT,
    UNKNOWN_SLASH_COMMAND_TEXT,
    WELCOME_TEXT,
    build_commands_text,
)

FORBIDDEN = (
    r"гарантир.*прибыл",
    r"100%\s*профит",
    r"seed\s*phrase",
    r"private\s*key",
    r"подключи\s*кошел",
    r"wallet\s*connect",
)


def _scan(text: str) -> list[str]:
    low = text.lower()
    bad = []
    for pat in FORBIDDEN:
        if re.search(pat, low, re.I):
            bad.append(pat)
    return bad


def test_stage35_copy_safety():
    chunks = [
        WELCOME_TEXT,
        EXAMPLES_TEXT,
        HOW_IT_WORKS_TEXT,
        QUICK_START_TEXT,
        UNKNOWN_SLASH_COMMAND_TEXT,
        UNKNOWN_PLAIN_TEXT,
        FREE_FLIP_PLAN_TEASER,
        FREE_BUDGET_DEALS_TEASER,
        build_commands_text(is_admin=False),
        build_commands_text(is_admin=True),
    ]
    for c in chunks:
        assert _scan(c) == [], f"unsafe wording in {c[:40]}..."

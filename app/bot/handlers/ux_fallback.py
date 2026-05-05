"""Unknown /command and plain-text hints (registered after passive_gift)."""

from aiogram import F, Router
from aiogram.types import Message

from app.bot.handlers.passive_gift import _smells_like_gift_context
from app.bot.known_commands import KNOWN_BOT_COMMANDS, normalize_command_token
from app.bot.messages import UNKNOWN_PLAIN_TEXT, UNKNOWN_SLASH_COMMAND_TEXT

router = Router()


@router.message(F.text.startswith("/"))
async def unknown_slash_command(message: Message) -> None:
    token = normalize_command_token(message.text or "")
    if not token or token in KNOWN_BOT_COMMANDS:
        return
    await message.answer(UNKNOWN_SLASH_COMMAND_TEXT)


@router.message(F.text, ~F.text.startswith("/"))
async def unknown_plain_text_hint(message: Message) -> None:
    text = (message.text or "").strip()
    if not text or "\n" in text or len(text) > 900:
        return
    if _smells_like_gift_context(text):
        return
    await message.answer(UNKNOWN_PLAIN_TEXT)

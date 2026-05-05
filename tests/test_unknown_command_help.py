import pytest

from app.bot.handlers.ux_fallback import unknown_plain_text_hint, unknown_slash_command


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_unknown_slash_replies():
    msg = _Msg("/totally_unknown_command_xyz")
    await unknown_slash_command(msg)
    assert len(msg.answers) == 1
    assert "/check" in msg.answers[0]


@pytest.mark.asyncio
async def test_known_slash_token_skipped():
    msg = _Msg("/start")
    await unknown_slash_command(msg)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_unknown_plain_hint():
    msg = _Msg("hello what is this")
    await unknown_plain_text_hint(msg)
    assert len(msg.answers) == 1
    assert "/examples" in msg.answers[0]

from pathlib import Path

import pytest

from app.services.gift_intake import GiftInputType, parse_gift_input

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "urls" / "telegram_gift_urls.txt"


def _lines():
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            yield s


@pytest.mark.parametrize("url", list(_lines()))
def test_telegram_urls_recognized(url: str):
    gi = parse_gift_input(url)
    assert gi.input_type == GiftInputType.telegram_gift_url
    assert gi.marketplace == "telegram"

from pathlib import Path

import pytest

from app.services.gift_intake import parse_gift_input

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "urls" / "explorer_urls.txt"


def _lines():
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            yield s


@pytest.mark.parametrize("url", list(_lines()))
def test_explorer_urls_extract_or_safe(url: str):
    gi = parse_gift_input(url)
    assert gi.nft_address or gi.parse_warnings

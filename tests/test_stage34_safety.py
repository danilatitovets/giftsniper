"""Stage 34: no guaranteed-profit phrasing in new modules; no wallet/seed logic."""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "app" / "services" / "capital_multiplier.py",
    ROOT / "app" / "services" / "flip_ladder.py",
    ROOT / "app" / "services" / "sell_to_buy_planner.py",
    ROOT / "app" / "bot" / "handlers" / "flip_handlers.py",
    ROOT / "app" / "services" / "universe_opportunities.py",
]

FORBIDDEN = [
    "точно заработаешь",
    "гарантированно",
    "100%",
    "x2 гарантированно",
    "без риска",
    "точно продашь",
]
FORBIDDEN_EN = ["guaranteed profit", "definitely sell"]

WALLET_MARKERS = ["seed phrase", "private key", "wallet connect", "connect wallet"]


@pytest.mark.parametrize("path", FILES)
def test_stage34_files_avoid_forbidden_phrases(path: pathlib.Path):
    text = path.read_text(encoding="utf-8").lower()
    for phrase in FORBIDDEN:
        assert phrase.lower() not in text, f"{path.name} contains {phrase}"
    for phrase in FORBIDDEN_EN:
        assert phrase not in text, f"{path.name} contains {phrase}"


@pytest.mark.parametrize("path", FILES)
def test_stage34_no_wallet_secrets_handlers(path: pathlib.Path):
    t = path.read_text(encoding="utf-8").lower()
    for m in WALLET_MARKERS:
        assert m not in t

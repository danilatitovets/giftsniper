from pathlib import Path


def test_stage28_gift_modules_no_seed_language():
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    for name in ("gift_intake.py", "gift_resolver.py", "gift_cards.py"):
        text = (root / name).read_text(encoding="utf-8").lower()
        for needle in ("seed phrase", "private key", "mnemonic"):
            assert needle not in text

import json
from pathlib import Path

from app.config import Settings
from app.bot.handlers.settings import render_collections_report
from app.sources.collections import get_source_identifier, load_collection_registry, resolve_collection


def test_resolve_ice_cream_by_alias(tmp_path: Path):
    path = tmp_path / "collections.json"
    path.write_text(
        json.dumps(
            {
                "Ice Cream": {
                    "aliases": ["icecream", "ice cream"],
                    "getgems": {"collection_address": "EQ_TEST"},
                    "tonnel": {"slug": ""},
                    "fragment": {"slug": ""},
                }
            }
        ),
        encoding="utf-8",
    )
    registry = load_collection_registry(str(path))
    canonical, payload = resolve_collection("IceCream", registry)
    assert canonical == "Ice Cream"
    assert payload is not None
    assert get_source_identifier("Ice Cream", "getgems", "collection_address", registry) == "EQ_TEST"


def test_collections_report_works_with_example_registry():
    settings = Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        COLLECTION_REGISTRY_PATH="data/collections.example.json",
    )
    text = render_collections_report(settings)
    assert "Ice Cream" in text

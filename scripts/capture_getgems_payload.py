from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.sources.collections import get_source_identifier, load_collection_registry, resolve_collection
from app.sources.getgems import GetGemsSource
from app.sources.http import MarketHTTPClient
from app.utils.sanitize import sanitize_payload


async def run_capture(collection_name: str) -> None:
    settings = get_settings()
    registry = load_collection_registry(settings.collection_registry_path)
    canonical, _ = resolve_collection(collection_name, registry)
    if not canonical:
        print(f"Collection not found in registry: {collection_name}")
        return
    address = get_source_identifier(canonical, "getgems", "collection_address", registry=registry)
    if not address:
        print(f"collection_address missing for '{canonical}'")
        return

    source = GetGemsSource(
        settings,
        http_client=MarketHTTPClient(
            timeout_seconds=settings.market_http_timeout_seconds,
            retries=settings.market_http_retries,
            user_agent=settings.market_http_user_agent,
        ),
        registry=registry,
    )
    on_sale = await source._request(f"/v1/nfts/on-sale/{address}")  # noqa: SLF001
    history = await source._request(f"/v1/collection/history/{address}")  # noqa: SLF001

    out_dir = Path("tests/fixtures/getgems/real")
    out_dir.mkdir(parents=True, exist_ok=True)
    if on_sale:
        on_sale_path = out_dir / f"on_sale_{canonical.lower().replace(' ', '_')}.json"
        on_sale_path.write_text(json.dumps(sanitize_payload(on_sale), ensure_ascii=False, indent=2)[:800000], encoding="utf-8")
        print(f"Saved: {on_sale_path}")
    else:
        print("On-sale payload not available.")
    if history:
        history_path = out_dir / f"history_{canonical.lower().replace(' ', '_')}.json"
        history_path.write_text(json.dumps(sanitize_payload(history), ensure_ascii=False, indent=2)[:800000], encoding="utf-8")
        print(f"Saved: {history_path}")
    else:
        print("History payload not available.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True, help="Collection human name, e.g. Ice Cream")
    args = parser.parse_args()
    asyncio.run(run_capture(args.collection))


if __name__ == "__main__":
    main()

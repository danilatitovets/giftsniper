from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.sources.collections import get_source_identifier, load_collection_registry
from app.sources.getgems import GetGemsSource
from app.sources.http import MarketHTTPClient


async def inspect_registry(settings) -> list[str]:
    registry = load_collection_registry(settings.collection_registry_path)
    lines = [f"Registry path: {settings.collection_registry_path}"]
    if not registry:
        lines.append("No collections found.")
        return lines
    source = GetGemsSource(
        settings,
        http_client=MarketHTTPClient(
            timeout_seconds=settings.market_http_timeout_seconds,
            retries=settings.market_http_retries,
            user_agent=settings.market_http_user_agent,
        ),
        registry=registry,
    )
    for name, payload in registry.items():
        getgems_address = get_source_identifier(name, "getgems", "collection_address", registry=registry) or ""
        status = "missing"
        if getgems_address:
            try:
                floor = await source.get_collection_floor(name)
                status = "ok" if floor else "failed"
            except Exception:
                status = "failed"
        lines.append(f"- {name}: getgems_address={'set' if getgems_address else 'missing'}, check={status}")
    return lines


async def main() -> None:
    settings = get_settings()
    lines = await inspect_registry(settings)
    for line in lines:
        print(line)


if __name__ == "__main__":
    asyncio.run(main())

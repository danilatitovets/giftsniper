"""CLI: python -m app.tools.resolve_nft_name \"Bunny Muffin #974\""""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.services.tonapi_collection_client import TonAPICollectionClient
from app.services.universal_nft_resolver import get_last_discovery_trace, resolve_universal_nft


async def _run(payload: str, *, live_discovery: bool, max_pages: int | None) -> dict:
    settings = get_settings()
    client = TonAPICollectionClient(settings)
    user = type("U", (), {"plan": "pro"})()
    toncenter_enabled = bool(
        getattr(settings, "toncenter_enabled", False)
        and getattr(settings, "nft_global_resolver_use_toncenter", True)
        and bool((getattr(settings, "toncenter_api_key", "") or "").strip())
    )
    tgt, err = await resolve_universal_nft(
        payload,
        user,
        settings,
        client,
        learn=False,
        live_discovery=live_discovery,
        max_pages=max_pages,
    )
    if err:
        trace = get_last_discovery_trace() or {}
        return {
            "ok": False,
            "error": err,
            "source": "not_found",
            "toncenter_enabled": toncenter_enabled,
            "toncenter_probe_source": "tried" if toncenter_enabled else "disabled",
            "toncenter_probe_error": trace.get("final_reason") or "not_found_no_match",
            "collection_discovery_trace": trace,
        }
    if not tgt:
        trace = get_last_discovery_trace() or {}
        return {
            "ok": False,
            "hint": "not_in_local_index_try_tonapi_resolve",
            "source": "not_found",
            "toncenter_enabled": toncenter_enabled,
            "toncenter_probe_source": "tried" if toncenter_enabled else "disabled",
            "toncenter_probe_error": trace.get("final_reason") or "not_found_no_match",
            "collection_discovery_trace": trace,
        }
    trace = getattr(tgt, "resolver_trace", None) or get_last_discovery_trace()
    return {
        "ok": True,
        "source": tgt.source,
        "nft_address": tgt.nft_address,
        "collection_address": tgt.collection_address,
        "collection_name": tgt.collection_name,
        "nft_name": tgt.nft_name,
        "item_number": tgt.item_number,
        "learned": bool(tgt.learned),
        "toncenter_enabled": toncenter_enabled,
        "trace": trace,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("payload", help='e.g. Bunny Muffin #974')
    p.add_argument("--live-discovery", action="store_true", default=False)
    p.add_argument("--max-pages", type=int, default=None)
    args = p.parse_args()
    out = asyncio.run(_run(args.payload, live_discovery=args.live_discovery, max_pages=args.max_pages))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

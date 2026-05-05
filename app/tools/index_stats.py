"""python -m app.tools.index_stats"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from sqlalchemy.exc import ProgrammingError

from app.config import get_settings
from app.db.repositories import nft_global_index_repo as repo
from app.db.session import SessionLocal


async def _run() -> dict:
    settings = get_settings()
    try:
        async with SessionLocal() as session:
            nc = await repo.count_collections(session)
            na = await repo.count_aliases(session)
            ni = await repo.count_items(session)
            nf = await repo.count_failed_jobs(session)
            mx = await repo.max_collection_indexed_at(session)
    except ProgrammingError as exc:
        # Local/dev DB may not have 0033 migration applied yet.
        if "UndefinedTableError" in str(exc) or "does not exist" in str(exc):
            return {
                "ok": False,
                "skipped": True,
                "reason": "nft_index_tables_missing",
                "hint": "run: alembic upgrade head",
                "nft_global_index_enabled": getattr(settings, "nft_global_index_enabled", False),
            }
        raise
    return {
        "ok": True,
        "nft_global_index_enabled": getattr(settings, "nft_global_index_enabled", False),
        "collections_indexed": nc,
        "aliases_count": na,
        "items_indexed": ni,
        "failed_jobs": nf,
        "last_collection_indexed_at": mx.isoformat() if isinstance(mx, datetime) else mx,
    }


def main() -> None:
    print(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

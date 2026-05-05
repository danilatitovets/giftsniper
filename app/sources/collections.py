from __future__ import annotations

import difflib
import json
from pathlib import Path

from app.sources.normalization import normalize_collection_name


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_collection_registry(registry_path: str = "data/collections.json") -> dict:
    local = _load_json(Path(registry_path))
    if local:
        return local
    example_path = Path("data/collections.example.json")
    return _load_json(example_path)


def resolve_collection(collection_name: str, registry: dict | None = None) -> tuple[str | None, dict | None]:
    data = registry or {}
    normalized = normalize_collection_name(collection_name)
    for canonical, payload in data.items():
        aliases = payload.get("aliases", [])
        alias_set = {normalize_collection_name(canonical)}
        alias_set.update(normalize_collection_name(alias) for alias in aliases)
        if normalize_collection_name(collection_name) in alias_set:
            return canonical, payload
    return (normalized if normalized in data else None), data.get(normalized)


def suggest_collections_with_scores(
    raw: str, registry: dict | None = None, *, limit: int = 3, min_score: float = 0.45
) -> list[tuple[str, float]]:
    """Return up to `limit` (canonical_name, similarity 0..1) suggestions for typos / fuzzy aliases."""
    data = registry or {}
    if not raw or not data:
        return []
    variants: dict[str, str] = {}
    for canonical, payload in data.items():
        variants[normalize_collection_name(canonical)] = canonical
        for alias in payload.get("aliases") or []:
            variants[normalize_collection_name(alias)] = canonical
    target = normalize_collection_name(raw)
    if target in variants:
        return []
    target_l = target.lower()
    by_canon: dict[str, float] = {}
    for key, canonical in variants.items():
        ratio = difflib.SequenceMatcher(None, target_l, key.lower()).ratio()
        if ratio < min_score:
            continue
        prev = by_canon.get(canonical, 0.0)
        if ratio > prev:
            by_canon[canonical] = ratio
    scored = [(c, round(r, 3)) for c, r in by_canon.items()]
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


def suggest_collection(raw: str, registry: dict | None = None, *, cutoff: float = 0.72) -> str | None:
    top = suggest_collections_with_scores(raw, registry=registry, limit=1, min_score=cutoff)
    return top[0][0] if top else None


def get_source_identifier(
    collection_name: str, source_name: str, field: str, registry: dict | None = None
) -> str | None:
    canonical, payload = resolve_collection(collection_name, registry=registry or {})
    if not canonical or not payload:
        return None
    source_bucket = payload.get(source_name.lower(), {})
    value = source_bucket.get(field)
    if value is None:
        return None
    return str(value).strip() or None


def get_tonapi_collection_address(collection_name: str, registry: dict | None = None) -> str | None:
    """On-chain collection address for TonAPI /v2/nfts/collections/{address}/items."""
    canonical, payload = resolve_collection(collection_name, registry=registry or {})
    if not payload:
        return None
    tonapi_block = payload.get("tonapi") or {}
    addr = str(tonapi_block.get("collection_address") or "").strip()
    if addr:
        return addr
    gg = str((payload.get("getgems") or {}).get("collection_address") or "").strip()
    return gg or None

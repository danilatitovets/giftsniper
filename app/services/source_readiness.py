"""Market source readiness from config only (no live API calls)."""

from __future__ import annotations

from dataclasses import dataclass

from app.sources.factory import describe_sources


@dataclass
class SourceReadinessSummary:
    mock_only_mode: bool
    collections_in_registry: int
    manual_fallback_available: bool
    tonapi_key_set: bool
    getgems_key_set: bool
    tonapi_enabled: bool
    getgems_enabled: bool
    warnings: list[str]


def build_source_readiness_summary(settings) -> SourceReadinessSummary:
    desc = describe_sources(settings)
    mock_only = bool(desc.get("mock_enabled"))
    ncols = int(desc.get("collections_count") or 0)
    manual_fb = bool((desc.get("manual") or {}).get("enabled"))
    tonapi = desc.get("tonapi") or {}
    gg = desc.get("getgems") or {}
    tonapi_key = bool(tonapi.get("has_api_key"))
    gg_key = bool(gg.get("has_api_key"))
    tonapi_on = bool(tonapi.get("enabled"))
    gg_on = bool(gg.get("enabled"))

    warns: list[str] = []
    prod = bool(getattr(settings, "production_mode", False))
    if prod and mock_only:
        warns.append("ENABLE_MOCK_SOURCE=true: only mock aggregator in production (no live marketplace stack).")
    if tonapi_on and not tonapi_key:
        warns.append("TonAPI enabled but TONAPI_API_KEY missing — quality may be limited.")
    if gg_on and not gg_key:
        warns.append("Getgems enabled but GETGEMS_API_KEY missing — some endpoints may fail.")
    if not mock_only and not manual_fb:
        warns.append("Manual source not reported as available — unexpected; check factory.")
    if ncols == 0 and not mock_only:
        warns.append("Collection registry empty — add data/collections or enable mock for tests.")

    return SourceReadinessSummary(
        mock_only_mode=mock_only,
        collections_in_registry=ncols,
        manual_fallback_available=manual_fb,
        tonapi_key_set=tonapi_key,
        getgems_key_set=gg_key,
        tonapi_enabled=tonapi_on,
        getgems_enabled=gg_on,
        warnings=warns,
    )

"""Build calibration JSON scenarios from trade_journal (Stage 32)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.db.models import TradeJournal


@dataclass
class DatasetBuildResult:
    written: int = 0
    skipped: list[tuple[int, str]] = field(default_factory=list)


def build_scenarios_from_trade_journal(rows: list[TradeJournal]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Returns (scenarios, skipped trade_id reasons)."""
    out: list[dict] = []
    skipped: list[tuple[int, str]] = []
    for r in rows:
        if r.status != "sold" or not r.buy_price_ton or not r.sell_price_ton:
            skipped.append((r.id, "not closed or missing prices"))
            continue
        snap = {}
        if r.prediction_json:
            try:
                snap = json.loads(r.prediction_json)
            except json.JSONDecodeError:
                snap = {}
        sales = snap.get("recent_sales") if isinstance(snap.get("recent_sales"), list) else []
        if not sales and not r.predicted_list_price_ton:
            skipped.append((r.id, "incomplete: no sales snapshot and no predicted list"))
            continue
        attrs = r.attributes_json if isinstance(r.attributes_json, list) else []
        floor_guess = float(r.buy_price_ton) * 0.92
        scenario = {
            "name": f"journal_{r.id}_{r.collection.replace(' ', '_')[:24]}",
            "collection": r.collection,
            "number": r.number,
            "attributes": attrs if isinstance(attrs, list) else [],
            "listing_price_ton": float(r.buy_price_ton),
            "collection_floor_ton": floor_guess,
            "trait_floor_ton": None,
            "recent_sales": [float(x) for x in sales]
            if sales
            else [float(r.sell_price_ton) * 0.95, float(r.sell_price_ton)],
            "trait_recent_sales": [],
            "expected_decision": r.decision_type,
            "notes": f"generated from trade_journal #{r.id}; verify floor/sales before relying on ranges",
        }
        out.append(scenario)
    return out, skipped


def export_calibration_scenarios_json(
    scenarios: list[dict],
    out_dir: Path,
    *,
    prefix: str = "gen_",
) -> DatasetBuildResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    res = DatasetBuildResult()
    for s in scenarios:
        name = str(s.get("name") or "scenario").replace("/", "_")
        path = out_dir / f"{prefix}{name}.json"
        raw = json.dumps(s, ensure_ascii=False, indent=2)
        if len(raw) < 40:
            res.skipped.append((0, f"too short: {name}"))
            continue
        path.write_text(raw, encoding="utf-8")
        res.written += 1
    return res


def format_dataset_builder_report(
    res: DatasetBuildResult,
    out_dir: Path,
    *,
    extra_skipped: list[tuple[int, str]] | None = None,
) -> str:
    lines = [
        "📦 Calibration dataset",
        f"Written: {res.written} → {out_dir}",
        f"Skipped (export): {len(res.skipped)}",
    ]
    for _, reason in res.skipped[:10]:
        lines.append(f"  - {reason}")
    if extra_skipped:
        lines.append(f"Skipped (source rows): {len(extra_skipped)}")
        for tid, reason in extra_skipped[:12]:
            lines.append(f"  - trade #{tid}: {reason}")
    return "\n".join(lines)

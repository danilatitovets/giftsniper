"""Export reviewed signals for beta calibration datasets (Stage 33)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedbackItem, SignalSnapshot

GENERATED_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "calibration" / "signals" / "generated"


def _snapshot_to_row(s: SignalSnapshot) -> dict[str, Any]:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "source_command": s.source_command,
        "collection": s.collection,
        "number": s.number,
        "decision_type": s.decision_type,
        "recommendation": s.recommendation,
        "confidence_score": s.confidence_score,
        "risk_score": s.risk_score,
        "liquidity_score": s.liquidity_score,
        "freshness_label": s.freshness_label,
        "has_trait_sales": s.has_trait_sales,
        "warning_flags_json": s.warning_flags_json,
        "analysis_json": s.analysis_json,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def build_beta_dataset_summary(session: AsyncSession) -> dict[str, int]:
    snaps = int(await session.scalar(select(func.count(SignalSnapshot.id))) or 0)
    reviewed = int(
        await session.scalar(
            select(func.count(func.distinct(FeedbackItem.signal_snapshot_id))).where(
                FeedbackItem.signal_snapshot_id.is_not(None),
                FeedbackItem.signal_rating.is_not(None),
            )
        )
        or 0
    )
    bad = int(
        await session.scalar(
            select(func.count(func.distinct(FeedbackItem.signal_snapshot_id))).where(
                FeedbackItem.signal_snapshot_id.is_not(None),
                FeedbackItem.signal_rating == "bad",
            )
        )
        or 0
    )
    good = int(
        await session.scalar(
            select(func.count(func.distinct(FeedbackItem.signal_snapshot_id))).where(
                FeedbackItem.signal_snapshot_id.is_not(None),
                FeedbackItem.signal_rating == "good",
            )
        )
        or 0
    )
    return {
        "signal_snapshots_total": snaps,
        "snapshots_with_review_rating": reviewed,
        "snapshots_bad_rated": bad,
        "snapshots_good_rated": good,
    }


async def _fetch_distinct_snapshots_for_rating(session: AsyncSession, rating: str) -> list[SignalSnapshot]:
    raw = (
        await session.scalars(
            select(FeedbackItem.signal_snapshot_id).where(
                FeedbackItem.signal_snapshot_id.is_not(None),
                FeedbackItem.signal_rating == rating,
            )
        )
    ).all()
    ids = list({i for i in raw if i})
    if not ids:
        return []
    r = await session.scalars(select(SignalSnapshot).where(SignalSnapshot.id.in_(ids)))
    return list(r.all())


async def _fetch_reviewed_snapshots(session: AsyncSession) -> list[SignalSnapshot]:
    raw = (
        await session.scalars(
            select(FeedbackItem.signal_snapshot_id).where(
                FeedbackItem.signal_snapshot_id.is_not(None),
                FeedbackItem.signal_rating.is_not(None),
            )
        )
    ).all()
    ids = list({i for i in raw if i})
    if not ids:
        return []
    r = await session.scalars(select(SignalSnapshot).where(SignalSnapshot.id.in_(ids)))
    return list(r.all())


def _ensure_dir() -> Path:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    return GENERATED_DIR


async def export_bad_signals_dataset(session: AsyncSession) -> tuple[Path, Path]:
    rows = await _fetch_distinct_snapshots_for_rating(session, "bad")
    d = _ensure_dir()
    jsonl = d / "bad_signals.jsonl"
    csv_path = d / "bad_signals.csv"
    with jsonl.open("w", encoding="utf-8") as fj:
        for s in rows:
            fj.write(json.dumps(_snapshot_to_row(s), ensure_ascii=False) + "\n")
    if rows:
        fieldnames = list(_snapshot_to_row(rows[0]).keys())
        with csv_path.open("w", encoding="utf-8", newline="") as fc:
            w = csv.DictWriter(fc, fieldnames=fieldnames)
            w.writeheader()
            for s in rows:
                w.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in _snapshot_to_row(s).items()})
    else:
        csv_path.write_text("", encoding="utf-8")
    return jsonl, csv_path


async def export_good_signals_dataset(session: AsyncSession) -> tuple[Path, Path]:
    rows = await _fetch_distinct_snapshots_for_rating(session, "good")
    d = _ensure_dir()
    jsonl = d / "good_signals.jsonl"
    csv_path = d / "good_signals.csv"
    with jsonl.open("w", encoding="utf-8") as fj:
        for s in rows:
            fj.write(json.dumps(_snapshot_to_row(s), ensure_ascii=False) + "\n")
    if rows:
        fieldnames = list(_snapshot_to_row(rows[0]).keys())
        with csv_path.open("w", encoding="utf-8", newline="") as fc:
            w = csv.DictWriter(fc, fieldnames=fieldnames)
            w.writeheader()
            for s in rows:
                w.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in _snapshot_to_row(s).items()})
    else:
        csv_path.write_text("", encoding="utf-8")
    return jsonl, csv_path


async def export_reviewed_signals_dataset(session: AsyncSession) -> tuple[Path, Path]:
    rows = await _fetch_reviewed_snapshots(session)
    d = _ensure_dir()
    jsonl = d / "reviewed_signals.jsonl"
    csv_path = d / "reviewed_signals.csv"
    with jsonl.open("w", encoding="utf-8") as fj:
        for s in rows:
            fj.write(json.dumps(_snapshot_to_row(s), ensure_ascii=False) + "\n")
    if rows:
        fieldnames = list(_snapshot_to_row(rows[0]).keys())
        with csv_path.open("w", encoding="utf-8", newline="") as fc:
            w = csv.DictWriter(fc, fieldnames=fieldnames)
            w.writeheader()
            for s in rows:
                w.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in _snapshot_to_row(s).items()})
    else:
        csv_path.write_text("", encoding="utf-8")
    return jsonl, csv_path


def format_beta_dataset_report(summary: dict[str, int], *, jsonl_path: Path | None = None) -> str:
    lines = [
        "🗂 Beta dataset workflow",
        f"Total snapshots: {summary.get('signal_snapshots_total', 0)}",
        f"With review rating: {summary.get('snapshots_with_review_rating', 0)}",
        f"Good-rated distinct: {summary.get('snapshots_good_rated', 0)}",
        f"Bad-rated distinct: {summary.get('snapshots_bad_rated', 0)}",
    ]
    if jsonl_path:
        lines.append(f"Last export: {jsonl_path}")
    lines.append(f"Output directory: {GENERATED_DIR}")
    return "\n".join(lines)

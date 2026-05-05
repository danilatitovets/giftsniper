"""CSV import for trade_journal (Stage 32)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TradeJournal
from app.db.repositories.trade_journal import TradeJournalRepository
from app.services.trade_accuracy import compute_sold_trade_accuracy


def _fee_net(price: float, fee_pct: float) -> float:
    return price * (1 - fee_pct / 100.0)


@dataclass
class TradeImportResult:
    imported: int = 0
    skipped: int = 0
    row_errors: list[tuple[int, str]] = field(default_factory=list)
    ids: list[int] = field(default_factory=list)


def parse_trade_csv(content: str) -> tuple[list[str], list[dict[str, str]]]:
    """Returns (fieldnames, rows as dicts with string values)."""
    buf = io.StringIO(content.strip())
    reader = csv.DictReader(buf)
    if not reader.fieldnames:
        return [], []
    fields = [f.strip() for f in reader.fieldnames if f]
    rows: list[dict[str, str]] = []
    for r in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in r.items() if k})
    return fields, rows


def _parse_float(val: str | None) -> float | None:
    if val is None or val == "":
        return None
    try:
        x = float(val.replace(",", "."))
        return x
    except ValueError:
        return None


def _parse_int(val: str | None) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    val = val.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(val[:19], fmt)
        except ValueError:
            continue
    return None


def _soft_parse_attributes(raw: str | None) -> list | dict | None:
    if not raw:
        return None
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return v
    except json.JSONDecodeError:
        pass
    return None


def validate_trade_row(row: dict[str, str], line_no: int) -> tuple[bool, list[str]]:
    errs: list[str] = []
    coll = (row.get("collection") or "").strip()
    if not coll:
        errs.append("collection required")
    bp = _parse_float(row.get("buy_price_ton"))
    if bp is None or bp <= 0:
        errs.append("buy_price_ton must be positive")
    sp = _parse_float(row.get("sell_price_ton"))
    if sp is not None and sp < 0:
        errs.append("sell_price_ton invalid")
    st = (row.get("status") or "").strip().lower()
    if st and st not in ("sold", "open", "watching", "cancelled", ""):
        errs.append("unknown status")
    if (sp is None or sp <= 0) and st == "sold":
        errs.append("sold status requires sell_price_ton")
    return (len(errs) == 0, [f"line {line_no}: {e}" for e in errs])


def format_trade_import_preview(fields: list[str], rows: list[dict[str, str]], errors: list[tuple[int, str]]) -> str:
    lines = [
        "📥 Import preview",
        f"Columns: {', '.join(fields) if fields else '(none)'}",
        f"Rows: {len(rows)}",
    ]
    if errors:
        lines.append("Issues:")
        lines.extend(f"- {e}" for _, e in errors[:20])
        if len(errors) > 20:
            lines.append(f"... +{len(errors) - 20} more")
    lines.append("\nПроверьте данные. /trade_import_commit с тем же CSV для записи.")
    return "\n".join(lines)


def format_trade_import_result(res: TradeImportResult) -> str:
    lines = [
        f"✅ Импорт: записано {res.imported}, пропущено {res.skipped}.",
    ]
    if res.ids:
        lines.append("IDs: " + ", ".join(str(i) for i in res.ids[:30]) + (" …" if len(res.ids) > 30 else ""))
    if res.row_errors:
        lines.append("Ошибки строк:")
        lines.extend(f"- {e}" for _, e in res.row_errors[:25])
    return "\n".join(lines)


def _row_to_trade_kwargs(row: dict[str, str], user_id: int) -> dict[str, Any]:
    sell = _parse_float(row.get("sell_price_ton"))
    st = (row.get("status") or "").strip().lower()
    if sell is not None and sell > 0:
        status = "sold"
    elif st in ("open", "watching", "cancelled"):
        status = st
    else:
        status = "open"
    buy_d = _parse_dt(row.get("buy_date"))
    sell_d = _parse_dt(row.get("sell_date"))
    attrs = _soft_parse_attributes(row.get("attributes_json"))
    snap = None
    if any(
        row.get(k)
        for k in (
            "decision_type",
            "predicted_safe_buy_ton",
            "predicted_max_buy_ton",
            "predicted_list_price_ton",
            "predicted_roi_percent",
            "predicted_confidence",
        )
    ):
        snap = {
            "decision_type": row.get("decision_type") or None,
            "safe_buy_price_ton": _parse_float(row.get("predicted_safe_buy_ton")),
            "max_buy_price_ton": _parse_float(row.get("predicted_max_buy_ton")),
            "normal_list_price_ton": _parse_float(row.get("predicted_list_price_ton")),
            "expected_roi_percent": _parse_float(row.get("predicted_roi_percent")),
            "confidence_score": _parse_int(row.get("predicted_confidence")),
        }
        snap = {k: v for k, v in snap.items() if v is not None}
        if not snap:
            snap = None

    return {
        "user_id": user_id,
        "collection": (row.get("collection") or "").strip(),
        "number": _parse_int(row.get("number")),
        "nft_address": (row.get("nft_address") or "").strip() or None,
        "buy_price_ton": _parse_float(row.get("buy_price_ton")),
        "buy_date": buy_d or datetime.utcnow(),
        "sell_price_ton": sell if sell and sell > 0 else None,
        "sell_date": sell_d,
        "status": status,
        "attributes_json": attrs,
        "source_url": (row.get("source_url") or "").strip() or None,
        "notes": (row.get("notes") or "").strip() or None,
        "prediction_snapshot": snap,
    }


def format_trade_export_csv(rows: list[TradeJournal], *, fee_percent: float = 5.0) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "collection",
            "number",
            "nft_address",
            "buy_price_ton",
            "sell_price_ton",
            "status",
            "realized_profit_ton",
            "realized_roi_percent",
            "decision_type",
            "predicted_max_buy_ton",
            "predicted_list_price_ton",
            "predicted_confidence",
            "created_at",
        ]
    )
    for r in rows:
        buy = float(r.buy_price_ton) if r.buy_price_ton else 0.0
        net = _fee_net(float(r.sell_price_ton), fee_percent) if r.sell_price_ton else None
        pnl = (net - buy) if net is not None and buy > 0 else r.realized_profit_ton
        roi = r.realized_roi_percent
        if roi is None and net is not None and buy > 0:
            roi = round((net - buy) / buy * 100.0, 2)
        w.writerow(
            [
                r.id,
                r.collection,
                r.number or "",
                r.nft_address or "",
                r.buy_price_ton or "",
                r.sell_price_ton or "",
                r.status,
                pnl if pnl is not None else "",
                roi if roi is not None else "",
                r.decision_type or "",
                r.predicted_max_buy_ton or "",
                r.predicted_list_price_ton or "",
                r.predicted_confidence or "",
                r.created_at.isoformat() if r.created_at else "",
            ]
        )
    return buf.getvalue()


async def import_trades_for_user(session: AsyncSession, user_id: int, rows: list[dict[str, str]]) -> TradeImportResult:
    repo = TradeJournalRepository(session)
    out = TradeImportResult()
    for i, row in enumerate(rows, start=2):
        ok, errs = validate_trade_row(row, i)
        if not ok:
            out.skipped += 1
            out.row_errors.extend((i, e) for e in errs)
            continue
        kw = _row_to_trade_kwargs(row, user_id)
        tj = await repo.create_import_row(**kw)
        if tj.status == "sold" and tj.sell_price_ton and tj.buy_price_ton:
            acc = compute_sold_trade_accuracy(tj, float(tj.sell_price_ton), sell_date=tj.sell_date or datetime.utcnow())
            await repo.apply_accuracy_fields(tj.id, user_id, acc)
        out.imported += 1
        out.ids.append(tj.id)
    return out

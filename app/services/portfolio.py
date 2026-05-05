from app.schemas.analysis import FlipAnalysisResult


def aggregate_portfolio(estimates: list[FlipAnalysisResult], purchase_prices: list[float | None]) -> dict:
    quick = sum(item.quick_sell_price_ton for item in estimates)
    fair = sum(item.fair_price_ton for item in estimates)
    list_total = sum(item.list_price_ton for item in estimates)
    net_total = sum(item.expected_net_sale_ton for item in estimates)
    spent = sum(p for p in purchase_prices if p is not None)
    pnl = net_total - spent if spent else None
    avg_risk = sum(item.risk_score for item in estimates) / len(estimates) if estimates else 0.0
    avg_conf = sum(item.confidence_score for item in estimates) / len(estimates) if estimates else 0.0
    return {
        "count": len(estimates),
        "quick_sell_total": round(quick, 2),
        "fair_price_total": round(fair, 2),
        "list_total": round(list_total, 2),
        "estimated_net_total": round(net_total, 2),
        "pnl": round(pnl, 2) if pnl is not None else None,
        "avg_risk_score": round(avg_risk, 1),
        "avg_confidence_score": round(avg_conf, 1),
    }

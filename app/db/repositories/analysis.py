from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisResult
from app.schemas.analysis import FlipAnalysisResult


class AnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, gift_id: int, estimate: FlipAnalysisResult) -> AnalysisResult:
        row = AnalysisResult(
            gift_id=gift_id,
            quick_sell_price_ton=estimate.quick_sell_price_ton,
            fair_price_ton=estimate.fair_price_ton,
            optimistic_price_ton=estimate.optimistic_price_ton,
            max_buy_price_ton=estimate.buy_zone_max_ton,
            buy_zone_min_ton=estimate.buy_zone_min_ton,
            buy_zone_max_ton=estimate.buy_zone_max_ton,
            list_price_ton=estimate.list_price_ton,
            stop_price_ton=estimate.stop_price_ton,
            marketplace_fee_percent=estimate.marketplace_fee_percent,
            expected_net_sale_ton=estimate.expected_net_sale_ton,
            expected_profit_ton=estimate.expected_profit_ton,
            expected_roi_percent=estimate.expected_roi_percent,
            liquidity_score=estimate.liquidity_score,
            risk_score=estimate.risk_score,
            confidence_score=estimate.confidence_score,
            recommendation=estimate.recommendation,
            reasons_json=estimate.reasons,
            safe_buy_price_ton=getattr(estimate, "safe_buy_price_ton", None),
            aggressive_buy_price_ton=getattr(estimate, "aggressive_buy_price_ton", None),
            quick_flip_list_price_ton=getattr(estimate, "quick_flip_list_price_ton", None),
            normal_list_price_ton=getattr(estimate, "normal_list_price_ton", None),
            high_list_price_ton=getattr(estimate, "high_list_price_ton", None),
            downside_price_ton=getattr(estimate, "downside_price_ton", None),
            upside_price_ton=getattr(estimate, "upside_price_ton", None),
            time_to_sell_estimate=getattr(estimate, "time_to_sell_estimate", None),
            decision_type=getattr(estimate, "decision_type", None),
            decision_summary=getattr(estimate, "decision_summary", None),
            rarity_score=getattr(estimate, "rarity_score", None),
            liquidity_adjusted_rarity_score=getattr(estimate, "liquidity_adjusted_rarity_score", None),
            trait_opportunity_score=getattr(estimate, "trait_opportunity_score", None),
            market_intelligence_json=getattr(estimate, "market_intelligence_json", None),
            precision_plan_json=getattr(estimate, "precision_plan_json", None),
            decision_json=getattr(estimate, "decision_json", None),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_latest_for_gift(self, gift_id: int) -> AnalysisResult | None:
        stmt = (
            select(AnalysisResult)
            .where(AnalysisResult.gift_id == gift_id)
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

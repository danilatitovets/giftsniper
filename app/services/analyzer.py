from datetime import datetime, timezone

from app.config import get_settings
from app.schemas.analysis import FlipAnalysisResult, SourcePricingContext
from app.schemas.gift import GiftCard
from app.schemas.market import MarketDataQuality
from app.schemas.market_brain import DecisionResult
from app.services.decision_engine import make_unified_decision, recommendation_for_decision
from app.services.important_traits import format_important_trait_notes, score_important_trait_keyword
from app.services.market_data_validity import evaluate_market_data_validity
from app.services.market_intelligence import build_collection_market_profile, build_trait_market_profile
from app.services.price_sanity import apply_price_sanity_caps
from app.services.pricing import calculate_precision_price_plan, estimate_gift_price, roi_targets_from_settings
from app.services.rarity import calculate_combined_rarity_score, calculate_trait_rarity_profile
from app.services.trait_opportunity import detect_mispriced_rare_listing
from app.sources.base import MarketSource
from app.sources.collections import load_collection_registry, resolve_collection

REAL_MARKET_SOURCES = frozenset({"getgems", "tonnel", "fragment"})
PRICING_SOURCES = frozenset({"getgems", "tonnel", "fragment", "manual"})


def _src_lower(x: str | None) -> str:
    return (x or "").lower()


def _estimate_max_trait_sales(gift: GiftCard, sales: list, *, allow_mock: bool) -> int:
    def _sale_ok(s) -> bool:
        sl = _src_lower(getattr(s, "source", None))
        if sl in PRICING_SOURCES:
            return True
        return bool(allow_mock and sl == "mock")

    priced = [s for s in sales if _sale_ok(s)]
    if not gift.attributes:
        return len(priced)

    def _blob_matches(blob: object, trait_type: str, trait_value: str) -> bool:
        if not isinstance(blob, dict):
            return False
        attrs = blob.get("attributes")
        if not isinstance(attrs, list):
            return False
        for it in attrs:
            if not isinstance(it, dict):
                continue
            tt = it.get("trait_type") or it.get("traitType") or it.get("type")
            tv = it.get("trait_value") or it.get("traitValue") or it.get("value")
            if tt == trait_type and tv == trait_value:
                return True
        return False

    best = 0
    for attr in gift.attributes:
        cnt = sum(
            1
            for s in priced
            if _blob_matches(getattr(s, "attributes_json", None) or {}, attr.trait_type, attr.trait_value)
        )
        best = max(best, cnt)
    return best


class AnalyzerService:
    def __init__(self, source: MarketSource) -> None:
        self.source = source
        self.settings = get_settings()
        self.last_data_quality = MarketDataQuality()
        self.last_market_stats: dict = {}

    def _mock_as_pricing_source(self) -> bool:
        if bool(self.settings.production_mode):
            return bool(self.settings.allow_mock_in_production)
        return bool(self.settings.mock_allowed_for_dev)

    def _is_pricing_source(self, source: str | None) -> bool:
        s = _src_lower(source)
        if s in PRICING_SOURCES:
            return True
        if s == "mock" and self._mock_as_pricing_source():
            return True
        return False

    def _capture_quality(self, bucket: list[MarketDataQuality]) -> None:
        quality = getattr(self.source, "last_quality", None)
        if quality is not None:
            bucket.append(quality)

    def _merge_quality(self, chunks: list[MarketDataQuality]) -> MarketDataQuality:
        used: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        penalty = 0
        for item in chunks:
            used.extend(item.sources_used)
            failed.extend(item.sources_failed)
            warnings.extend(item.warnings)
            penalty += item.confidence_penalty
        used = list(dict.fromkeys(used))
        failed = list(dict.fromkeys(failed))
        warnings = list(dict.fromkeys(warnings))
        merged = MarketDataQuality(
            sources_used=used,
            sources_failed=failed,
            confidence_penalty=min(60, penalty),
            warnings=warnings,
            is_mock_data=any(src == "mock" for src in used),
            is_partial_data=any(item.is_partial_data for item in chunks) or bool(failed),
        )
        self.last_data_quality = merged
        return merged

    def _age_minutes(self, dt: datetime | None) -> int | None:
        if dt is None:
            return None
        now = datetime.now(timezone.utc)
        source_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return max(0, int((now - source_dt).total_seconds() // 60))

    def _freshness_label(self, age_minutes: int | None) -> str:
        if age_minutes is None:
            return "unknown"
        if age_minutes <= self.settings.fresh_floor_max_minutes:
            return "fresh"
        if age_minutes <= self.settings.stale_floor_max_minutes:
            return "stale"
        return "old"

    def _build_source_pricing_context(
        self,
        *,
        quality: MarketDataQuality,
        validity_source: str,
        has_tonapi: bool,
        has_manual: bool,
    ) -> SourcePricingContext:
        meta = "tonapi" if has_tonapi else ("manual" if has_manual else "unknown")
        warns = list(quality.warnings or [])[:5]
        return SourcePricingContext(
            pricing_source=validity_source if validity_source in {"real", "manual", "mock", "unavailable", "mixed"} else "unavailable",
            metadata_source=meta,
            market_source_names=list(quality.sources_used or []),
            warnings=warns,
        )

    def _suppressed_flip_result(
        self,
        *,
        validity,
        quality: MarketDataQuality,
        ctx: SourcePricingContext,
    ) -> FlipAnalysisResult:
        dec = DecisionResult(
            decision="NEED_MORE_DATA",
            action_label_ru="Недостаточно рыночных данных для цен",
            confidence_score=0.0,
            risk_score=70.0,
            reasons=[validity.user_message_ru],
            warnings=["Mock/test floor отключён для production."] if validity.reason_code == "mock_blocked_production" else [],
        )
        return FlipAnalysisResult(
            buy_zone_min_ton=0.0,
            buy_zone_max_ton=0.0,
            quick_sell_price_ton=0.0,
            fair_price_ton=0.0,
            list_price_ton=0.0,
            optimistic_price_ton=0.0,
            stop_price_ton=0.0,
            marketplace_fee_percent=float(self.settings.default_marketplace_fee_percent),
            expected_net_sale_ton=0.0,
            expected_profit_ton=0.0,
            expected_roi_percent=0.0,
            liquidity_score=0,
            risk_score=75,
            confidence_score=0,
            recommendation="HOLD",
            roi_based_on_estimated_buy_zone=True,
            reasons=[validity.user_message_ru],
            decision_type="NEED_MORE_DATA",
            decision_summary=dec.action_label_ru,
            pricing_suppressed=True,
            market_validity_message_ru=validity.user_message_ru,
            price_source_label=validity.source_type,
            source_pricing_context=ctx,
            decision_json=dec.model_dump_json(),
        )

    async def analyze_gift(
        self,
        gift: GiftCard,
        risk_mode: str = "normal",
        buy_price_ton: float | None = None,
        market_regime: str | None = None,
        owns_asset: bool = False,
    ) -> FlipAnalysisResult:
        quality_chunks: list[MarketDataQuality] = []
        floor = await self.source.get_collection_floor(gift.collection)
        self._capture_quality(quality_chunks)
        trait_floors: list[float] = []
        trait_ages: list[int] = []
        trait_floor_detail: list[tuple[str, str, float | None]] = []
        for attr in gift.attributes:
            tf = await self.source.get_trait_floor(gift.collection, attr.trait_type, attr.trait_value)
            self._capture_quality(quality_chunks)
            tf_val = tf.floor_ton if tf is not None else None
            trait_floor_detail.append((attr.trait_type, attr.trait_value, tf_val))
            if tf is not None:
                trait_floors.append(tf.floor_ton)
                age = self._age_minutes(tf.created_at)
                if age is not None:
                    trait_ages.append(age)
        sales = await self.source.get_recent_sales(gift.collection, limit=20)
        self._capture_quality(quality_chunks)
        listings = await self.source.get_similar_listings(gift.collection, gift.attributes, limit=20)
        self._capture_quality(quality_chunks)
        floor_age = self._age_minutes(floor.created_at) if floor else None
        trait_age = min(trait_ages) if trait_ages else None
        listings_age = self._age_minutes(listings[0].created_at) if listings else None
        sales_age = self._age_minutes(sales[0].sold_at) if sales else None
        floor_freshness = self._freshness_label(floor_age)
        trait_freshness = self._freshness_label(trait_age)
        listings_freshness = self._freshness_label(listings_age)
        sales_freshness = self._freshness_label(sales_age)
        sales_old_by_days = bool(sales_age is not None and sales_age > self.settings.recent_sales_max_days * 24 * 60)

        quality = self._merge_quality(quality_chunks)
        source_names = {s.lower() for s in quality.sources_used}
        has_manual = "manual" in source_names
        has_tonapi = "tonapi" in source_names
        has_mock = "mock" in source_names
        floor_src = _src_lower(floor.source) if floor else ""
        has_pricing_floor = bool(floor and self._is_pricing_source(floor.source))
        real_floor = bool(floor and floor_src in REAL_MARKET_SOURCES)
        manual_floor_stat = bool(floor and floor_src == "manual")
        real_listings_count = sum(1 for l in listings if _src_lower(getattr(l, "source", None)) in REAL_MARKET_SOURCES)
        pricing_listings_count = sum(1 for l in listings if self._is_pricing_source(getattr(l, "source", None)))
        real_sales_count = sum(1 for s in sales if _src_lower(getattr(s, "source", None)) in REAL_MARKET_SOURCES)
        pricing_sales_count = sum(1 for s in sales if self._is_pricing_source(getattr(s, "source", None)))
        manual_sales_count = sum(1 for s in sales if _src_lower(getattr(s, "source", None)) == "manual")
        has_real_adapter = bool(source_names & REAL_MARKET_SOURCES) or real_floor or real_listings_count > 0 or real_sales_count > 0
        has_manual_data = has_manual or manual_floor_stat or manual_sales_count > 0
        manual_floor = manual_floor_stat
        manual_trait_count = len(trait_floors) if has_manual_data else 0
        price_source_present = has_real_adapter or has_manual_data
        trait_attrs_available = any(bool(item.attributes_json.get("attributes")) for item in listings) if listings else False
        mixed_real_mock = price_source_present and has_mock
        registry = load_collection_registry(self.settings.collection_registry_path)
        _, coll_payload = resolve_collection(gift.collection, registry=registry)
        collection_known = bool(coll_payload)
        max_trait_sales_pre = _estimate_max_trait_sales(gift, sales, allow_mock=self._mock_as_pricing_source())
        self.last_market_stats = {
            "real_floor": real_floor,
            "real_listings_count": real_listings_count,
            "real_sales_count": real_sales_count,
            "manual_floor": manual_floor,
            "manual_trait_count": manual_trait_count,
            "manual_sales_count": manual_sales_count,
            "has_pricing_floor": has_pricing_floor,
            "pricing_listings_count": pricing_listings_count,
            "pricing_sales_count": pricing_sales_count,
            "has_tonapi": has_tonapi,
            "trait_attributes_available": trait_attrs_available,
            "mixed_real_mock": mixed_real_mock,
            "confidence_cap_reason": "",
            "floor_age_minutes": floor_age,
            "trait_age_minutes": trait_age,
            "listings_age_minutes": listings_age,
            "sales_age_minutes": sales_age,
            "floor_freshness": floor_freshness,
            "trait_freshness": trait_freshness,
            "listings_freshness": listings_freshness,
            "sales_freshness": sales_freshness,
            "collection_known": collection_known,
        }

        validity0 = evaluate_market_data_validity(
            settings=self.settings,
            quality=quality,
            stats=self.last_market_stats,
            has_floor=has_pricing_floor,
            listings_count=pricing_listings_count,
            sales_count=pricing_sales_count,
            max_trait_sales=max_trait_sales_pre,
        )
        self.last_market_stats["pricing_allowed"] = validity0.pricing_allowed
        self.last_market_stats["market_validity_reason"] = validity0.reason_code
        if not validity0.pricing_allowed:
            ctx = self._build_source_pricing_context(
                quality=quality,
                validity_source=validity0.source_type,
                has_tonapi=has_tonapi,
                has_manual=has_manual_data,
            )
            return self._suppressed_flip_result(validity=validity0, quality=quality, ctx=ctx)

        market_data = {
            "collection_floor": floor.floor_ton if floor else 0.0,
            "listed_count": floor.listed_count if floor else None,
            "trait_floors": trait_floors,
            "recent_sales": [s.price_ton for s in sales],
            "similar_listings": [l.price_ton for l in listings],
        }
        result = estimate_gift_price(
            gift=gift,
            market_data=market_data,
            risk_mode=risk_mode,
            buy_price_ton=buy_price_ton,
            marketplace_fee_percent=self.settings.default_marketplace_fee_percent,
            estimated_extra_costs_ton=self.settings.estimated_extra_costs_ton,
            min_profit_ton=self.settings.min_profit_ton,
            settings=self.settings,
        )
        is_mock_context = (
            quality.is_mock_data or _src_lower(getattr(self.source, "name", "")) == "mock"
        ) and not has_real_adapter
        if is_mock_context:
            result.reasons.append("Оценка рассчитана на mock-данных, реальные источники еще не подключены.")
        self.last_market_stats["dev_mock_labeled"] = bool(is_mock_context and not self.settings.production_mode)
        if quality.is_partial_data:
            result.confidence_score = max(20, result.confidence_score - 12)
            result.reasons.append("Данные частичные, confidence дополнительно снижен.")
        if quality.confidence_penalty:
            result.confidence_score = max(20, result.confidence_score - quality.confidence_penalty)
        if quality.sources_failed:
            result.reasons.append("Часть источников не ответила: " + ", ".join(quality.sources_failed))
        if not sales:
            result.confidence_score = max(20, result.confidence_score - 10)
            result.reasons.append("Нет recent sales, confidence снижен.")
        elif sales_old_by_days:
            result.confidence_score = max(20, result.confidence_score - 12)
            result.risk_score = min(95, (result.risk_score or 35) + 10)
            result.reasons.append("Последние продажи старше 7 дней")
        if len(quality.sources_used) >= 2 and not quality.is_mock_data:
            result.confidence_score = min(95, result.confidence_score + 4)
            result.reasons.append("Данные подтверждены несколькими источниками.")
        if has_tonapi and not (real_floor or real_listings_count or real_sales_count or manual_floor_stat):
            result.reasons.append("Есть on-chain данные TonAPI, но нет live marketplace prices.")
        # Hard confidence caps by data quality.
        cap = 95
        cap_reason = ""
        if is_mock_context:
            cap = 60
            cap_reason = "confidence capped: mock data"
        elif manual_floor and not manual_trait_count and not manual_sales_count:
            cap = 65
            cap_reason = "confidence capped: manual floor only"
        elif manual_floor and manual_trait_count and not manual_sales_count:
            cap = 70
            cap_reason = "confidence capped: manual floor + trait floors"
        elif manual_floor and manual_trait_count and manual_sales_count:
            cap = 75
            cap_reason = "confidence capped: manual floor + trait floors + sales"
        elif real_floor and real_listings_count and not real_sales_count:
            cap = 75
            cap_reason = "confidence capped: no real sales"
        elif real_floor and not real_sales_count:
            cap = 70
            cap_reason = "confidence capped: real floor only"
        if floor_freshness == "stale":
            result.confidence_score = max(20, result.confidence_score - 8)
            result.risk_score = min(95, (result.risk_score or 35) + 6)
            result.reasons.append("Floor устарел, уверенность снижена")
        elif floor_freshness == "old":
            result.confidence_score = max(20, result.confidence_score - 15)
            result.risk_score = min(95, (result.risk_score or 35) + 12)
            result.reasons.append("Floor устарел, уверенность снижена")
            cap = min(cap, 55 if has_manual else 60)
            cap_reason = "confidence capped: old floor data"
        if trait_freshness in {"stale", "old"} and has_manual:
            result.reasons.append("Trait floor введен вручную и может быть неактуален")
        if floor_freshness == "fresh" and (sales_freshness == "fresh" or not sales):
            result.reasons.append("Данные свежие")
        if result.confidence_score > cap:
            result.confidence_score = cap
            result.reasons.append(cap_reason)
        if (floor_freshness == "old" or sales_old_by_days) and not real_sales_count and result.recommendation == "BUY_FOR_FLIP":
            result.recommendation = "BUY_ONLY_CHEAP"
            result.reasons.append("Старые данные блокируют BUY_FOR_FLIP без актуальных продаж.")
        if buy_price_ton is not None and market_regime:
            base_targets = roi_targets_from_settings(self.settings)
            regime_adj = {"risk_on": 0.0, "neutral": 3.0, "risk_off": 8.0, "illiquid": 12.0, "data_poor": 10.0}
            required_roi = base_targets.get(risk_mode, base_targets["normal"]) + regime_adj.get(market_regime, 0.0)
            self.last_market_stats["required_roi_percent"] = required_roi
            self.last_market_stats["market_regime"] = market_regime
            if result.expected_roi_percent < required_roi and result.recommendation == "BUY_FOR_FLIP":
                result.recommendation = "BUY_ONLY_CHEAP"
                result.reasons.append(
                    f"Режим {market_regime} повышает target ROI до {required_roi:.1f}%, BUY_FOR_FLIP понижен."
                )
        if not trait_attrs_available:
            result.reasons.append("Trait attributes unavailable, trait floor may be incomplete.")
        if mixed_real_mock:
            result.reasons.append("Смешанные real/mock данные.")
        self.last_market_stats["confidence_cap_reason"] = cap_reason

        source_q = getattr(self.source, "name", "unknown") or "unknown"
        coll_profile = build_collection_market_profile(
            gift.collection,
            floor,
            listings,
            sales,
            self.settings,
            source_quality=source_q,
            freshness_label=floor_freshness,
        )
        self.last_market_stats["spread_percent"] = float(coll_profile.spread_percent or 0)
        tprofiles = {}
        for attr in gift.attributes:
            tf_ton = next((t for tt, tv, t in trait_floor_detail if tt == attr.trait_type and tv == attr.trait_value), None)
            tp = build_trait_market_profile(
                gift.collection,
                attr.trait_type,
                attr.trait_value,
                tf_ton,
                coll_profile,
                listings,
                sales,
                attr.rarity_percent,
                self.settings,
            )
            tprofiles[(attr.trait_type, attr.trait_value)] = tp

        rarity_profiles = []
        for attr in gift.attributes:
            tp = tprofiles.get((attr.trait_type, attr.trait_value))
            imp = score_important_trait_keyword(attr.trait_type, attr.trait_value, self.settings)
            rarity_profiles.append(calculate_trait_rarity_profile(attr, tp, float(floor.floor_ton) if floor else 0.0, important_bonus=imp))

        comb_raw, comb_adj = calculate_combined_rarity_score(gift.attributes, rarity_profiles)
        trait_notes = format_important_trait_notes(
            gift.attributes,
            self.settings,
            trait_sales_count=max((p.sale_count or 0) for p in rarity_profiles) if rarity_profiles else 0,
            trait_floor_ton=max((v.trait_floor_ton for v in tprofiles.values() if v.trait_floor_ton), default=None),
        )
        for note in trait_notes[:3]:
            result.reasons.append(note)

        trait_opp_scores: list[float] = []
        ref_price = buy_price_ton if buy_price_ton is not None else float(result.buy_zone_max_ton or 0)
        for attr in gift.attributes:
            tp = tprofiles.get((attr.trait_type, attr.trait_value))
            if tp is None:
                continue
            imp = score_important_trait_keyword(attr.trait_type, attr.trait_value, self.settings)
            sc, opp_reasons = detect_mispriced_rare_listing(
                ref_price,
                tp.trait_floor_ton,
                tp.trait_median_sale_price_ton,
                coll_profile.collection_floor_ton,
                trait_sales_n=tp.trait_recent_sales_count,
                listing_count_trait=tp.trait_listing_count,
                important_score=imp,
                liquidity=coll_profile.liquidity_score,
            )
            trait_opp_scores.append(sc)
            for r in opp_reasons[:1]:
                if sc >= 50:
                    result.reasons.append(r)
        trait_opp_score = max(trait_opp_scores) if trait_opp_scores else None

        pricing_sales_list = [s for s in sales if self._is_pricing_source(getattr(s, "source", None))]
        max_trait_slot = (
            max((v.trait_recent_sales_count for v in tprofiles.values()), default=0) if gift.attributes else len(pricing_sales_list)
        )
        result = apply_price_sanity_caps(
            result,
            listing_hint_ton=buy_price_ton,
            floor_ton=float(floor.floor_ton) if floor else None,
            sales_count=len(pricing_sales_list),
            max_trait_sales=max_trait_slot,
            collection_known=collection_known,
        )

        listing_low = min((float(l.price_ton) for l in listings), default=None)
        is_mock_or_stale = is_mock_context or floor_freshness in {"stale", "old"} or quality.is_partial_data
        plan = calculate_precision_price_plan(
            result,
            coll_profile,
            risk_mode=risk_mode,
            marketplace_fee_percent=self.settings.default_marketplace_fee_percent,
            estimated_extra_costs_ton=self.settings.estimated_extra_costs_ton,
            min_profit_ton=self.settings.min_profit_ton,
            floor=float(floor.floor_ton) if floor else 0.0,
            median_sale=coll_profile.median_sale_price_ton,
            sales_count=len(sales),
            listing_low=listing_low,
            combined_liquidity_adj_rarity=comb_adj,
            is_mock_or_stale=is_mock_or_stale,
            settings=self.settings,
        )
        max_trait_sales = max((v.trait_recent_sales_count for v in tprofiles.values()), default=0)
        max_trait_sales_reported = max_trait_sales if gift.attributes else None
        strong_buy_trait_ok = (not gift.attributes) or (comb_adj < 40) or (max_trait_sales >= 1)
        apply_decision = buy_price_ton is not None or owns_asset
        if apply_decision:
            decision = make_unified_decision(
                buy_price=None if owns_asset else buy_price_ton,
                plan=plan,
                base=result,
                trait_opp_score=trait_opp_score,
                combined_rarity_adj=comb_adj,
                sales_count=len(sales),
                market_regime=market_regime,
                owns_asset=owns_asset,
                purchase_price=buy_price_ton if owns_asset else None,
                settings=self.settings,
                strong_buy_trait_ok=strong_buy_trait_ok,
                spread_percent=coll_profile.spread_percent,
            )
            rec2 = recommendation_for_decision(decision.decision)
            result = result.model_copy(update={"recommendation": rec2})
            pricing_sales_n = len(pricing_sales_list)
            if decision.decision == "STRONG_BUY":
                if pricing_sales_n < int(self.settings.min_real_sales_for_strong_buy):
                    decision = decision.model_copy(
                        update={
                            "decision": "BUY_IF_UNDER",
                            "action_label_ru": "Мало недавних продаж — без STRONG_BUY",
                            "reasons": list(decision.reasons)
                            + ["Недостаточно недавних продаж для STRONG_BUY."],
                        }
                    )
                    rec2 = recommendation_for_decision(decision.decision)
                    result = result.model_copy(update={"recommendation": rec2})
                elif int(result.confidence_score or 0) < int(self.settings.min_real_market_confidence_for_buy):
                    decision = decision.model_copy(
                        update={
                            "decision": "BUY_IF_UNDER",
                            "action_label_ru": "Confidence ниже порога для STRONG_BUY",
                        }
                    )
                    rec2 = recommendation_for_decision(decision.decision)
                    result = result.model_copy(update={"recommendation": rec2})
        else:
            decision = DecisionResult(
                decision="HOLD",
                action_label_ru="Укажите цену в /deal для торгового вердикта",
                confidence_score=float(result.confidence_score),
                risk_score=float(result.risk_score),
                reasons=["Без цены входа сохраняем классическую оценку fair/list."],
            )
        sp_ctx = self._build_source_pricing_context(
            quality=quality,
            validity_source=validity0.source_type,
            has_tonapi=has_tonapi,
            has_manual=has_manual_data,
        )
        result = result.model_copy(
            update={
                "safe_buy_price_ton": plan.safe_buy_price_ton,
                "aggressive_buy_price_ton": plan.aggressive_buy_price_ton,
                "quick_flip_list_price_ton": plan.quick_flip_list_price_ton,
                "normal_list_price_ton": plan.normal_list_price_ton,
                "high_list_price_ton": plan.high_list_price_ton,
                "downside_price_ton": plan.downside_price_ton,
                "upside_price_ton": plan.upside_price_ton,
                "time_to_sell_estimate": plan.time_to_sell_estimate,
                "decision_type": decision.decision,
                "decision_summary": decision.action_label_ru,
                "rarity_score": comb_raw,
                "liquidity_adjusted_rarity_score": comb_adj,
                "trait_opportunity_score": trait_opp_score,
                "max_trait_recent_sales": max_trait_sales_reported,
                "market_intelligence_json": coll_profile.model_dump_json(),
                "precision_plan_json": plan.model_dump_json(),
                "decision_json": decision.model_dump_json(),
                "quick_sell_price_ton": plan.quick_sell_price_ton,
                "stop_price_ton": plan.stop_loss_price_ton,
                "price_source_label": validity0.source_type,
                "source_pricing_context": sp_ctx,
            }
        )
        for w in plan.warnings[:4]:
            if w not in result.reasons:
                result.reasons.append(w)
        for w in decision.warnings[:3]:
            if w not in result.reasons:
                result.reasons.append(w)
        return result

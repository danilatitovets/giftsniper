from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.db.models import Listing, MarketSnapshot, Sale, TraitFloor
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.schemas.gift import GiftAttributeSchema, GiftCard
from app.services.analyzer import AnalyzerService
from app.services.audit import log_audit
from app.services.gift_cards import format_gift_deal_card, format_unknown_gift_input_help
from app.services.gift_intake import (
    GiftInputType,
    extract_buy_price_from_text,
    normalize_deal_subject,
    parse_gift_input,
    parse_nft_address,
)
from app.services.gift_analysis_flow import gift_attrs_for_demo
from app.services.gift_resolver import resolve_gift_identity
from app.services.market_intelligence import (
    build_collection_market_profile,
    build_trait_market_profile,
    format_market_intelligence_report,
    format_trait_intel_report,
)
from app.services.opportunity_scoring import calculate_opportunity_score, format_score_breakdown
from app.services.confidence_calibration import format_confidence_explanation
from app.services.market_cache import TTL_COLLECTION_PROFILE, TTL_TRAIT_PROFILE, get_cached, set_cached
from app.services.pricing import format_precision_price_plan_extended
from app.services.signal_snapshots import (
    build_snapshot_seed_from_flip_analysis,
    build_snapshot_seed_from_trait_opportunity,
    signal_feedback_footer,
)
from app.services.trait_opportunity import (
    format_trait_opportunity_report,
    rank_trait_opportunities,
    scan_trait_opportunities,
)
from app.sources.factory import create_market_source
from app.sources.manual import ManualSource

router = Router()


def _parts_pipe(text: str, cmd: str) -> list[str]:
    payload = text.removeprefix(cmd).strip()
    return [p.strip() for p in payload.split("|")]


def _to_price(v: str) -> float | None:
    try:
        x = float(v.replace(",", "."))
        if x <= 0:
            return None
        return x
    except ValueError:
        return None


def _age_text(ts: datetime | None) -> tuple[str, str]:
    if ts is None:
        return "unknown", "дата неизвестна"
    now = datetime.now(timezone.utc)
    dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    age_min = max(0, int((now - dt).total_seconds() // 60))
    if age_min < 60:
        return "fresh", f"{age_min} мин назад"
    if age_min <= 720:
        return "stale", f"{age_min // 60} ч назад"
    if age_min >= 1440:
        return "old", f"{age_min // 1440} дней назад"
    return "old", f"{age_min} мин назад"


@router.message(Command("market_set_floor"))
async def market_set_floor(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/market_set_floor")
    if len(parts) != 2:
        await message.answer("Используйте: /market_set_floor Ice Cream | 186")
        return
    price = _to_price(parts[1])
    if price is None:
        await message.answer("Цена должна быть положительным числом.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = MarketSnapshot(user_id=user.id, collection=parts[0], source="Manual", floor_ton=price)
        session.add(row)
        await session.commit()
    await message.answer("✅ Manual floor сохранен.")


@router.message(Command("market_set_trait_floor"))
async def market_set_trait_floor(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/market_set_trait_floor")
    if len(parts) != 4:
        await message.answer("Используйте: /market_set_trait_floor Ice Cream | Symbol | Moon | 240")
        return
    price = _to_price(parts[3])
    if price is None:
        await message.answer("Цена должна быть положительным числом.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = TraitFloor(
            user_id=user.id,
            collection=parts[0],
            trait_type=parts[1],
            trait_value=parts[2],
            source="Manual",
            floor_ton=price,
        )
        session.add(row)
        await session.commit()
    await message.answer("✅ Manual trait floor сохранен.")


@router.message(Command("market_set_sale"))
async def market_set_sale(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/market_set_sale")
    if len(parts) != 3 or not parts[1].isdigit():
        await message.answer("Используйте: /market_set_sale Ice Cream | 217467 | 230")
        return
    price = _to_price(parts[2])
    if price is None:
        await message.answer("Цена должна быть положительным числом.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = Sale(
            user_id=user.id,
            external_id=f"manual_sale_{user.id}_{int(datetime.now(timezone.utc).timestamp())}",
            source="Manual",
            collection=parts[0],
            number=int(parts[1]),
            price_ton=price,
            sold_at=datetime.now(timezone.utc),
            attributes_json={},
        )
        session.add(row)
        await session.commit()
    await message.answer("✅ Manual sale сохранен.")


@router.message(Command("market_set_listing"))
async def market_set_listing(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/market_set_listing")
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Используйте: /market_set_listing Ice Cream | 217467 | 220 | https://...")
        return
    price = _to_price(parts[2])
    if price is None:
        await message.answer("Цена должна быть положительным числом.")
        return
    url = parts[3] if len(parts) > 3 else ""
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = Listing(
            user_id=user.id,
            external_id=f"manual_listing_{user.id}_{int(datetime.now(timezone.utc).timestamp())}",
            source="Manual",
            collection=parts[0],
            number=int(parts[1]),
            price_ton=price,
            url=url,
            attributes_json={},
        )
        session.add(row)
        await session.commit()
    await message.answer("✅ Manual listing сохранен.")


@router.message(Command("market_data"))
async def market_data(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: /market_data <collection>")
        return
    collection = parts[1]
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    source = ManualSource(user.id)
    floor = await source.get_collection_floor(collection)
    sales = await source.get_recent_sales(collection, limit=5)
    listings = await source.get_similar_listings(collection, [], limit=5)
    trait_rows = []
    async with SessionLocal() as session:
        from sqlalchemy import select

        stmt = (
            select(TraitFloor)
            .where(TraitFloor.user_id == user.id, TraitFloor.source == "Manual", TraitFloor.collection == collection)
            .order_by(TraitFloor.created_at.desc())
            .limit(10)
        )
        trait_rows = list((await session.scalars(stmt)).all())
    if floor:
        label, age = _age_text(floor.created_at)
        icon = "✅" if label == "fresh" else ("⚠️" if label == "stale" else "🧊")
        floor_text = f"{floor.floor_ton:.2f} TON — {age} {icon} {label}"
    else:
        floor_text = "нет"
    traits_text = (
        "\n".join(
            (
                f"- {t.trait_type}={t.trait_value}: {t.floor_ton:.2f} TON — "
                f"{_age_text(t.created_at)[1]} "
                f"{'✅' if _age_text(t.created_at)[0]=='fresh' else ('⚠️' if _age_text(t.created_at)[0]=='stale' else '🧊')} "
                f"{_age_text(t.created_at)[0]}"
            )
            for t in trait_rows
        )
        if trait_rows
        else "- нет"
    )
    sales_text = (
        "\n".join(
            (
                f"- Sale #{s.number}: {s.price_ton:.2f} TON — {_age_text(s.sold_at)[1]} "
                f"{'✅' if _age_text(s.sold_at)[0]=='fresh' else ('⚠️' if _age_text(s.sold_at)[0]=='stale' else '🧊')} {_age_text(s.sold_at)[0]}"
            )
            for s in sales
        )
        if sales
        else "- нет"
    )
    listings_text = (
        "\n".join(
            (
                f"- Listing #{l.number}: {l.price_ton:.2f} TON — {_age_text(l.created_at)[1]} "
                f"{'✅' if _age_text(l.created_at)[0]=='fresh' else ('⚠️' if _age_text(l.created_at)[0]=='stale' else '🧊')} {_age_text(l.created_at)[0]}"
            )
            for l in listings
        )
        if listings
        else "- нет"
    )
    await message.answer(
        f"📊 Manual market data: {collection}\n\n"
        f"Floor: {floor_text}\n"
        f"Trait floors:\n{traits_text}\n"
        f"Recent sales:\n{sales_text}\n"
        f"Listings:\n{listings_text}\n\n"
        "⚠️ Ручные данные могут устареть."
    )


@router.message(Command("market_quick"))
async def market_quick_handler(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/market_quick")
    if len(parts) < 2:
        await message.answer(
            "Используйте: /market_quick Коллекция | floor=7.5 | sale=8 | listing=7.77 | num=57234\n"
            "num= нужен, если задаёте sale или listing для конкретного #."
        )
        return
    collection = parts[0].strip()
    kv: dict[str, str] = {}
    for p in parts[1:]:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        kv[k.strip().lower()] = v.strip()
    num_raw = kv.get("num") or kv.get("number")
    num = int(num_raw) if num_raw and str(num_raw).isdigit() else 0
    floor_v = _to_price(kv["floor"]) if "floor" in kv else None
    sale_v = _to_price(kv["sale"]) if "sale" in kv else None
    listing_v = _to_price(kv["listing"]) if "listing" in kv else None
    if floor_v is None and sale_v is None and listing_v is None:
        await message.answer("Укажите хотя бы одно из: floor=, sale=, listing=")
        return
    if (sale_v is not None or listing_v is not None) and num <= 0:
        await message.answer("Для sale=/listing= укажите num=<номер NFT> (например num=57234).")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        if floor_v is not None:
            session.add(MarketSnapshot(user_id=user.id, collection=collection, source="Manual", floor_ton=floor_v))
        if sale_v is not None:
            session.add(
                Sale(
                    user_id=user.id,
                    external_id=f"manual_sale_{user.id}_{int(datetime.now(timezone.utc).timestamp())}",
                    source="Manual",
                    collection=collection,
                    number=num,
                    price_ton=sale_v,
                    sold_at=datetime.now(timezone.utc),
                    attributes_json={},
                )
            )
        if listing_v is not None:
            session.add(
                Listing(
                    user_id=user.id,
                    external_id=f"manual_listing_{user.id}_{int(datetime.now(timezone.utc).timestamp())}",
                    source="Manual",
                    collection=collection,
                    number=num,
                    price_ton=listing_v,
                    url="",
                    attributes_json={},
                )
            )
        await session.commit()
    bits = []
    if floor_v is not None:
        bits.append(f"floor={floor_v}")
    if sale_v is not None:
        bits.append(f"sale={sale_v} (#{num})")
    if listing_v is not None:
        bits.append(f"listing={listing_v} (#{num})")
    await message.answer("✅ Manual market (quick): " + ", ".join(bits) + "\nТеперь /check и /deal используют эти данные.")


@router.message(Command("market_clear"))
async def market_clear(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: /market_clear <collection>")
        return
    collection = parts[1]
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        await log_audit(
            session,
            user_id=user.id,
            action="market_clear",
            entity_type="collection",
            entity_id=collection,
        )
    source = ManualSource(user.id)
    await source.clear_collection_data(collection)
    await message.answer("🧹 Manual данные по коллекции очищены.")


@router.message(Command("deal"))
async def deal_check(message: Message) -> None:
    full_text = message.text or ""
    parts = _parts_pipe(full_text, "/deal")
    buy_from_message = extract_buy_price_from_text(full_text)
    if len(parts) < 1:
        await message.answer("Используйте: /deal Ice Cream | 170 или /deal Ice Cream #217467 | 180 или ссылку | цена")
        return
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)

    identity_nft: str | None = None
    identity_url: str | None = None
    deal_input_text: str = parts[0] if parts else ""

    gift: GiftCard
    buy: float | None
    attrs: list[GiftAttributeSchema] = []

    legacy_trait_block = (
        len(parts) >= 4
        and _to_price(parts[1]) is not None
        and "#" not in parts[0]
        and not parts[0].lower().startswith("http")
        and not parse_nft_address(parts[0])
    )
    legacy_collection_only = (
        len(parts) >= 2
        and _to_price(parts[1]) is not None
        and not legacy_trait_block
        and "#" not in parts[0]
        and not parts[0].lower().startswith("http")
        and not parse_nft_address(parts[0])
        and parse_gift_input(parts[0]).input_type == GiftInputType.unknown
    )

    if legacy_trait_block:
        collection = parts[0]
        buy = _to_price(parts[1])
        attrs = [GiftAttributeSchema(trait_type=parts[2], trait_value=parts[3])]
        gift = GiftCard(collection=collection, number=0, attributes=attrs)
    elif legacy_collection_only:
        buy = _to_price(parts[1])
        gift = GiftCard(collection=parts[0], number=0, attributes=[])
    else:
        gift_ref = normalize_deal_subject(parts[0])
        buy = _to_price(parts[1]) if len(parts) >= 2 else None
        if buy is None:
            buy = buy_from_message
        gi, identity = await resolve_gift_identity(user, gift_ref, settings)
        if gi.input_type == GiftInputType.unknown or identity.collection in ("Unknown", "") or identity.number is None:
            if identity.nft_address:
                identity.collection = identity.normalized_collection or "On-chain NFT"
                identity.number = 0
            else:
                await message.answer(format_unknown_gift_input_help(gift_ref, [], context="deal"))
                return
        if buy is None:
            buy = gi.listing_price_ton
        if buy is None:
            await message.answer(
                "Нужна цена покупки (в ссылке не нашёл). Формат: /deal <ссылка или подарок> | <цена TON>"
            )
            return
        identity_nft = identity.nft_address
        identity_url = identity.source_url
        deal_input_text = gift_ref
        if len(parts) >= 4:
            attrs = [GiftAttributeSchema(trait_type=parts[2], trait_value=parts[3])]
        gift = GiftCard(collection=identity.collection, number=identity.number or 0, attributes=attrs)

    if buy is None or buy <= 0:
        await message.answer("Цена покупки должна быть положительным числом.")
        return

    analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
    est = await analyzer.analyze_gift(gift, risk_mode=user.risk_mode, buy_price_ton=buy)
    quality = analyzer.last_data_quality
    stats = analyzer.last_market_stats
    freshness_label = "old" if "old" in [stats.get("floor_freshness"), stats.get("sales_freshness")] else (
        "stale" if "stale" in [stats.get("floor_freshness"), stats.get("sales_freshness"), stats.get("listings_freshness")] else "fresh"
    )
    freshness_warning = (
        "⚠️ Расчет опирается на старые данные." if freshness_label == "old" else (
            "⚠️ Расчет опирается на stale данные." if freshness_label == "stale" else "✅ Данные для расчета свежие."
        )
    )
    score = calculate_opportunity_score(
        est,
        quality,
        {
            "label": freshness_label,
            "has_recent_sales": bool(stats.get("sales_age_minutes") is not None and stats.get("sales_age_minutes") <= 7 * 24 * 60),
            "listing_price_ton": float(buy),
            "real_sales_count": int(stats.get("real_sales_count") or 0),
            "spread_percent": float(stats.get("spread_percent") or 0),
        },
    )
    card = format_gift_deal_card(gift, est, quality, stats, buy)
    seed = build_snapshot_seed_from_flip_analysis(
        source_command="deal",
        gift=gift,
        estimate=est,
        stats=stats,
        quality=quality,
        score=score,
        input_text=deal_input_text,
        nft_address=identity_nft,
        source_url=identity_url,
        settings=settings,
    )
    footer = ""
    async with SessionLocal() as session:
        u = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        snap = await SignalSnapshotRepository(session).create(user_id=u.id, **seed)
        footer = signal_feedback_footer(snap.id)
    await message.answer(
        card
        + f"\n{freshness_warning}\n\n"
        + f"{format_score_breakdown(score)}\n\n"
        f"Рекомендация: {est.recommendation} · {getattr(est, 'decision_type', '')}\n"
        "⚠️ Сценарный расчёт, не live-исполнение сделки."
        + footer
    )


@router.message(Command("market_intel"))
async def market_intel_handler(message: Message) -> None:
    col = (message.text or "").removeprefix("/market_intel").strip()
    if not col:
        await message.answer("Используйте: /market_intel Ice Cream")
        return
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    src = create_market_source(settings, user_id=user.id)
    sname = getattr(src, "name", "unknown") or "unknown"
    ckey = col.strip().lower()
    cached = get_cached(ckey, sname, "collection")
    if cached is not None:
        await message.answer(format_market_intelligence_report(cached))
        return
    floor = await src.get_collection_floor(col)
    listings = await src.get_similar_listings(col, [], limit=40)
    sales = await src.get_recent_sales(col, limit=40)
    profile = build_collection_market_profile(
        col,
        floor,
        listings,
        sales,
        settings,
        source_quality=sname,
        freshness_label="unknown",
    )
    set_cached(ckey, sname, "collection", profile, TTL_COLLECTION_PROFILE)
    await message.answer(format_market_intelligence_report(profile))


@router.message(Command("trait_intel"))
async def trait_intel_handler(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/trait_intel")
    if len(parts) < 3:
        await message.answer("Используйте: /trait_intel Ice Cream | Backdrop | Monochrome")
        return
    collection, ttype, tvalue = parts[0], parts[1], parts[2]
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    src = create_market_source(settings, user_id=user.id)
    sname = getattr(src, "name", "unknown") or "unknown"
    tkey = f"{collection.strip().lower()}|{ttype.strip().lower()}|{tvalue.strip().lower()}"
    tcached = get_cached(tkey, sname, "trait")
    if tcached is not None:
        await message.answer(format_trait_intel_report(tcached))
        return
    floor = await src.get_collection_floor(collection)
    listings = await src.get_similar_listings(collection, [], limit=40)
    sales = await src.get_recent_sales(collection, limit=40)
    coll = build_collection_market_profile(
        collection,
        floor,
        listings,
        sales,
        settings,
        source_quality=sname,
        freshness_label="unknown",
    )
    tf = await src.get_trait_floor(collection, ttype, tvalue)
    tp = build_trait_market_profile(
        collection,
        ttype,
        tvalue,
        tf.floor_ton if tf else None,
        coll,
        listings,
        sales,
        None,
        settings,
    )
    set_cached(tkey, sname, "trait", tp, TTL_TRAIT_PROFILE)
    await message.answer(format_trait_intel_report(tp))


@router.message(Command("rare_deals"))
async def rare_deals_handler(message: Message) -> None:
    col = (message.text or "").removeprefix("/rare_deals").strip()
    if not col:
        await message.answer("Используйте: /rare_deals Ice Cream")
        return
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    src = create_market_source(settings, user_id=user.id)
    opps = await scan_trait_opportunities(col, src, settings)
    ranked = rank_trait_opportunities(opps)
    text = format_trait_opportunity_report(ranked)
    if ranked:
        seed = build_snapshot_seed_from_trait_opportunity(ranked[0], settings=settings)
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
            snap = await SignalSnapshotRepository(session).create(user_id=u.id, **seed)
            text = text + signal_feedback_footer(snap.id)
    await message.answer(text)


@router.message(Command("price_plan"))
async def price_plan_handler(message: Message) -> None:
    raw = (message.text or "").removeprefix("/price_plan").strip()
    if not raw:
        await message.answer("Используйте: /price_plan Ice Cream #217467 | 180")
        return
    settings = get_settings()
    parts = [p.strip() for p in raw.split("|")]
    buy_hint = _to_price(parts[1]) if len(parts) >= 2 else extract_buy_price_from_text(raw)
    subj = parts[0].strip() if parts else raw
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    gi, identity = await resolve_gift_identity(user, subj, settings)
    if gi.input_type == GiftInputType.unknown or identity.collection in ("Unknown", "") or identity.number is None:
        if identity.nft_address:
            identity.collection = identity.normalized_collection or "On-chain NFT"
            identity.number = 0
        else:
            await message.answer(format_unknown_gift_input_help(subj, [], context="price_plan"))
            return
    gift = gift_attrs_for_demo(GiftCard(collection=identity.collection, number=identity.number or 0))
    analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
    est = await analyzer.analyze_gift(
        gift,
        risk_mode=user.risk_mode,
        buy_price_ton=buy_hint,
        owns_asset=False,
    )
    if getattr(est, "pricing_suppressed", False):
        await message.answer(
            (getattr(est, "market_validity_message_ru", None) or "Недостаточно real/manual данных для price plan.")
            + "\n/market_quick … или /sources"
        )
        return
    if est.precision_plan_json:
        from app.schemas.market_brain import PrecisionPricePlan

        plan = PrecisionPricePlan.model_validate_json(est.precision_plan_json)
        stats = analyzer.last_market_stats or {}
        dq = analyzer.last_data_quality
        srcs = list(dq.sources_used) if dq and dq.sources_used else [getattr(analyzer.source, "name", "unknown") or "unknown"]
        fresh = str(stats.get("floor_freshness") or stats.get("sales_freshness") or "unknown")
        conf_txt = format_confidence_explanation(
            sources_used=srcs,
            sales_count=int(stats.get("real_sales_count") or 0),
            trait_sales_max=getattr(est, "max_trait_recent_sales", None),
            spread_percent=float(stats.get("spread_percent") or 0),
            freshness_label=fresh,
            capped_reason=(stats.get("confidence_cap_reason") or None) or None,
        )
        seed = build_snapshot_seed_from_flip_analysis(
            source_command="price_plan",
            gift=gift,
            estimate=est,
            stats=stats,
            quality=dq,
            input_text=subj,
            nft_address=identity.nft_address,
            source_url=identity.source_url,
            settings=settings,
        )
        footer = ""
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
            snap = await SignalSnapshotRepository(session).create(user_id=u.id, **seed)
            footer = signal_feedback_footer(snap.id)
        await message.answer(
            format_precision_price_plan_extended(
                plan,
                listing_price_ton=buy_hint,
                confidence_explanation=conf_txt,
            )
            + footer
        )
        return
    await message.answer("Не удалось построить precision plan.")

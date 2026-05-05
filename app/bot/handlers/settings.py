from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards import settings_stub_inline_keyboard
from app.config import get_settings
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.i18n import t, text_lang_from_user
from app.sources.collections import (
    load_collection_registry,
    resolve_collection,
    suggest_collection,
    suggest_collections_with_scores,
)
from app.sources.factory import describe_sources
from app.sources.getgems import GetGemsSource
from app.sources.http import MarketHTTPClient

router = Router()


async def send_mvp_settings_screen(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        lang = text_lang_from_user(user)
    await message.answer(t("settings.main", lang), reply_markup=settings_stub_inline_keyboard(lang=lang))


@router.message(Command("settings"))
async def settings_handler(message: Message) -> None:
    await send_mvp_settings_screen(message)


def render_sources_report(settings) -> str:
    info = describe_sources(settings)

    def status_line(title: str, data: dict, *, usable_key: str | None = None) -> str:
        if not data["enabled"]:
            return f"{title}: ❌ выключен"
        if data["has_base_url"]:
            if not data["has_api_key"]:
                return f"{title}: ⚠️ включен, endpoint настроен, ключ не задан"
            line = f"{title}: ✅ включен"
        else:
            line = f"{title}: ⚠️ включен, endpoint не настроен"
        if usable_key and usable_key in data:
            line += f" · usable: {'yes' if data[usable_key] else 'no'}"
        return line

    warnings: list[str] = []
    prod = bool(info.get("production_mode"))
    mock_blocked = bool(info.get("mock_trading_blocked"))
    if prod and info.get("mock_enabled") and not info.get("allow_mock_in_production"):
        warnings.append("⚠️ Production warning: mock data is enabled. Trading verdicts from mock are blocked.")
    elif not info["mock_enabled"] and not any(
        [info["getgems"].get("usable"), info["tonnel"].get("usable"), info["fragment"].get("usable")]
    ):
        if not info["manual"].get("usable"):
            warnings.append("Нет ни одного usable real source и manual выключен — цен не будет.")
        else:
            warnings.append("Real маркетплейсы не настроены; остаётся manual MVP.")
    if info["mock_enabled"] and not prod:
        warnings.append("Mock включён — только для dev/test.")

    warn_text = "\n".join(f"- {w}" for w in warnings) if warnings else "- нет"
    mock_trade = "yes" if info.get("mock_allowed_for_trading") else "no"
    return (
        "📡 Источники данных (Stage 37)\n\n"
        "Pricing sources:\n"
        f"- Getgems: {status_line('Getgems', info['getgems'], usable_key='usable')}\n"
        f"- Tonnel: {status_line('Tonnel', info['tonnel'], usable_key='usable')}\n"
        f"- Fragment: {status_line('Fragment', info['fragment'], usable_key='usable')}\n"
        f"- Manual: {'✅ user-scoped' if info['manual']['enabled'] else '❌ выключен'} · usable: "
        f"{'yes' if info['manual'].get('usable') else 'no'}\n"
        f"- Mock: {'✅ enabled' if info['mock_enabled'] else '❌ disabled'} · allowed_for_trading: {mock_trade}\n\n"
        "Metadata sources:\n"
        f"- TonAPI: {status_line('TonAPI', info['tonapi'])} · metadata only (не цена)\n\n"
        "Production guard:\n"
        f"- PRODUCTION_MODE: {'true' if prod else 'false'}\n"
        f"- Mock trading blocked: {'yes' if mock_blocked else 'no'}\n"
        f"- Real/manual required for trading: {'yes' if info.get('require_real_or_manual') else 'no'}\n\n"
        f"Registry path: {info['registry_path']}\n"
        f"Коллекций в registry: {info['collections_count']}\n"
        f"Ice Cream address: {'configured' if info['ice_cream_getgems_address_configured'] else 'missing'}\n\n"
        "API keys: скрыты (показывается только факт наличия)\n\n"
        f"Предупреждения:\n{warn_text}"
    )


def render_collections_report(settings) -> str:
    registry = load_collection_registry(settings.collection_registry_path)
    if not registry:
        return "Коллекции не найдены в registry."
    lines = ["📚 Коллекции из registry\n"]
    for name, payload in registry.items():
        has_getgems = bool((payload.get("getgems") or {}).get("collection_address"))
        has_tonnel = bool((payload.get("tonnel") or {}).get("slug"))
        has_fragment = bool((payload.get("fragment") or {}).get("slug"))
        lines.append(
            f"- {name}: Getgems={'✅' if has_getgems else '❌'}, "
            f"Tonnel={'✅' if has_tonnel else '❌'}, Fragment={'✅' if has_fragment else '❌'}"
        )
    return "\n".join(lines)


def render_collection_info_report(
    settings,
    collection_name: str,
    getgems_status: str = "not checked",
    getgems_warning: str = "not checked",
) -> str:
    registry = load_collection_registry(settings.collection_registry_path)
    canonical, payload = resolve_collection(collection_name, registry=registry)
    if not payload:
        multi = suggest_collections_with_scores(collection_name, registry=registry, limit=3, min_score=0.5)
        if multi:
            lines = "\n".join(f"{i}. {name} (score {sc})" for i, (name, sc) in enumerate(multi, start=1))
            hint = f"\n\nВозможно, ты имел в виду:\n{lines}"
        else:
            guess = suggest_collection(collection_name, registry=registry)
            hint = f"\n\nВозможно, ты имел в виду: {guess}." if guess else ""
        return f"Коллекция '{collection_name}' не найдена в registry.{hint}"
    aliases = payload.get("aliases", [])
    getgems = payload.get("getgems", {})
    tonnel = payload.get("tonnel", {})
    fragment = payload.get("fragment", {})
    parser_ok = bool(canonical)
    return (
        f"📦 Collection info: {canonical}\n\n"
        f"Aliases: {', '.join(aliases) if aliases else '-'}\n"
        f"Parser/registry: {'распознаётся' if parser_ok else 'нет'}\n"
        f"Примеры: /check {canonical} #217467 · /add {canonical} 217467\n"
        f"Getgems collection_address: {getgems.get('collection_address') or 'missing'}\n"
        f"Getgems status: {getgems_status}\n"
        f"Getgems warning: {getgems_warning}\n"
        f"Getgems slug: {getgems.get('slug') or 'missing'}\n"
        f"Tonnel slug: {tonnel.get('slug') or 'missing'}\n"
        f"Fragment slug: {fragment.get('slug') or 'missing'}"
    )


@router.message(Command("sources"))
async def sources_handler(message: Message) -> None:
    settings = get_settings()
    await message.answer(render_sources_report(settings))


@router.message(Command("collections"))
async def collections_handler(message: Message) -> None:
    settings = get_settings()
    await message.answer(render_collections_report(settings))


@router.message(Command("collection_info"))
async def collection_info_handler(message: Message) -> None:
    settings = get_settings()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: /collection_info <name>")
        return
    name = parts[1]
    registry = load_collection_registry(settings.collection_registry_path)
    canonical, payload = resolve_collection(name, registry=registry)
    status = "missing"
    warning = "not checked"
    if payload and (payload.get("getgems") or {}).get("collection_address"):
        try:
            source = GetGemsSource(
                settings,
                http_client=MarketHTTPClient(
                    timeout_seconds=settings.market_http_timeout_seconds,
                    retries=settings.market_http_retries,
                    user_agent=settings.market_http_user_agent,
                ),
                registry=registry,
            )
            floor = await source.get_collection_floor(canonical or name)
            q = getattr(source, "last_quality", None)
            status = "ok" if floor is not None else "failed"
            if q and q.warnings:
                warning = q.warnings[0]
        except Exception:
            status = "failed"
            warning = "status check failed"
    await message.answer(render_collection_info_report(settings, name, getgems_status=status, getgems_warning=warning))

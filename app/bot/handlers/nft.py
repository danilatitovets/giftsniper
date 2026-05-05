from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.services.gift_intake import GiftInputType, parse_gift_input
from app.services.gift_resolver import resolve_gift_identity
from app.services.nft_metadata import check_nft_metadata, format_nft_check_result

router = Router()


@router.message(Command("nft_check"))
async def nft_check_handler(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: /nft_check <что угодно: address | Ice Cream #1 | ссылка>")
        return
    payload = parts[1].strip()
    settings = get_settings()
    gi = parse_gift_input(payload)

    if gi.input_type == GiftInputType.nft_address and gi.nft_address:
        result = await check_nft_metadata(address=gi.nft_address)
        await message.answer(format_nft_check_result(result))
        return

    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    _, identity = await resolve_gift_identity(user, payload, settings)

    if identity.nft_address:
        result = await check_nft_metadata(address=identity.nft_address)
        await message.answer(format_nft_check_result(result))
        return

    if identity.collection and identity.number is not None:
        result = await check_nft_metadata(collection=identity.collection, number=identity.number)
        extra = (
            "\n\nДля on-chain деталей лучше прислать NFT address. "
            "Можно сделать рыночный /check без address."
        )
        await message.answer(format_nft_check_result(result) + extra)
        return

    await message.answer(
        "Не смог выделить NFT address. Примеры:\n"
        "/nft_check EQ...\n"
        "/nft_check Ice Cream #217467\n"
        "/nft_check https://..."
    )

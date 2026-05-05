"""MVP: список slash-команд в Telegram и тексты read-only бота."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault

# Текст /start (UX)
MVP_WELCOME = (
    "🎯 Привет! Я GiftSniper.\n\n"
    "Я помогаю быстро понять, за сколько можно выставить NFT / Telegram Gift по реальному рынку.\n\n"
    "Что я делаю:\n"
    "• нахожу NFT по адресу, ссылке или названию;\n"
    "• смотрю активные листинги через TonAPI;\n"
    "• сравниваю с похожими NFT в этой же коллекции;\n"
    "• показываю ориентир цены: быстро / нормально / дорого;\n"
    "• объясняю, насколько оценке можно доверять.\n\n"
    "Как проверить NFT:\n\n"
    "1️⃣ По названию\n"
    "Например:\n"
    "Ice Cream #217467\n\n"
    "2️⃣ По ссылке\n"
    "Просто отправь ссылку на NFT.\n\n"
    "3️⃣ По адресу\n"
    "Можно отправить NFT address.\n\n"
    "Я не покупаю и не продаю NFT.\n"
    "Я не прошу seed, private key или доступ к кошельку.\n"
    "Бот только анализирует рынок и помогает принять решение.\n\n"
    "Нажми кнопку ниже или отправь NFT прямо в чат 👇"
)

MVP_HELP = (
    "❓ Как пользоваться GiftSniper\n\n"
    "Отправь NFT одним из трёх способов:\n\n"
    "1️⃣ Название:\n"
    "Ice Cream #217467\n\n"
    "2️⃣ Ссылка:\n"
    "https://...\n\n"
    "3️⃣ NFT address:\n"
    "EQ...\n\n"
    "Команды:\n"
    "/check — проверить NFT\n"
    "/watch — добавить в отслеживание\n"
    "/watchlist — мои отслеживания\n"
    "/settings — настройки\n"
    "/upgrade — тарифы и оплата TON\n"
    "/billing — подписка и лимиты\n"
    "/ref — пригласить друзей и бонусные проверки\n"
    "/help — помощь\n\n"
    "Важно:\n"
    "GiftSniper показывает рыночный ориентир по активным листингам TonAPI.\n"
    "Это не гарантия продажи и не финансовый совет.\n\n"
    "Бот не покупает, не продаёт и не просит доступ к кошельку."
)

NFT_CHECK_PROMPT = (
    "🔎 Отправь NFT, который хочешь проверить.\n\n"
    "Можно отправить одним из трёх способов:\n\n"
    "1️⃣ Название:\n"
    "Ice Cream #217467\n\n"
    "2️⃣ Ссылку:\n"
    "https://...\n\n"
    "3️⃣ NFT address:\n"
    "EQ...\n\n"
    "Я проверю рынок через TonAPI и покажу ориентир по активным листингам TonAPI."
)

NFT_EXAMPLE_INTRO = (
    "Попробуй так:\n\n"
    "Ice Cream #217467\n\n"
    "Или просто нажми, чтобы я запустил пример проверки."
)

EMPTY_WATCHLIST_MESSAGE = (
    "👀 У тебя пока нет отслеживаний.\n\n"
    "Добавь NFT или коллекцию, и я помогу следить за рынком.\n\n"
    "Примеры:\n"
    "• /watch Ice Cream #217467\n"
    "• /watch Whip Cupcake #57234\n"
    "• /watch Ice Cream"
)

SETTINGS_STUB_MESSAGE = (
    "⚙️ Настройки\n\n"
    "Сейчас доступны базовые проверки NFT через TonAPI.\n\n"
    "Скоро здесь появятся:\n"
    "• уведомления о дешёвых листингах;\n"
    "• настройка минимальной скидки;\n"
    "• частота проверки рынка.\n\n"
    "Пока можешь использовать:\n"
    "• /check — проверить NFT\n"
    "• /watch — добавить в отслеживание\n"
    "• /watchlist — мои отслеживания"
)

MVP_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="check", description="Проверить NFT"),
    BotCommand(command="watch", description="Добавить в отслеживание"),
    BotCommand(command="watchlist", description="Мой список"),
    BotCommand(command="mylist", description="Мой список"),
    BotCommand(command="settings", description="Настройки"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="upgrade", description="Тарифы и оплата TON"),
    BotCommand(command="billing", description="Подписка и лимиты"),
    BotCommand(command="ref", description="Реферальная программа"),
)


async def setup_mvp_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(list(MVP_COMMANDS), scope=BotCommandScopeDefault())

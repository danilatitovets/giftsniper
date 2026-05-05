from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.alerts import router as alerts_router
from app.bot.handlers.analysis import router as analysis_router
from app.bot.handlers.flip_handlers import router as flip_handlers_router
from app.bot.handlers.gifts import router as gifts_router
from app.bot.handlers.market import router as market_router
from app.bot.handlers.nft import router as nft_router
from app.bot.handlers.passive_gift import router as passive_gift_router
from app.bot.handlers.portfolio import router as portfolio_router
from app.bot.handlers.sell_price import router as sell_price_router
from app.bot.handlers.language import router as language_router
from app.bot.handlers.settings import router as settings_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.ton_upgrade import router as ton_upgrade_router
from app.bot.handlers.trades import router as trades_router
from app.bot.handlers.ux_fallback import router as ux_fallback_router

routers = [
    language_router,
    start_router,
    ton_upgrade_router,
    admin_router,
    gifts_router,
    market_router,
    trades_router,
    analysis_router,
    sell_price_router,
    alerts_router,
    nft_router,
    portfolio_router,
    flip_handlers_router,
    settings_router,
    passive_gift_router,
    ux_fallback_router,
]

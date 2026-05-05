import asyncio
import logging
import subprocess
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import routers
from app.bot.middlewares import AccessControlMiddleware, SkipEmptyMessagesMiddleware
from app.bot.mvp_setup import setup_mvp_bot_commands
from app.config import get_settings
from app.db.session import SessionLocal
from app.services.scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    log.info("Full market page limit: %s", settings.full_market_page_limit)
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(SkipEmptyMessagesMiddleware())
    dp.message.middleware(AccessControlMiddleware())
    for router in routers:
        dp.include_router(router)

    scheduler = setup_scheduler(bot=bot, session_maker=SessionLocal, settings=settings)
    scheduler.start()
    await setup_mvp_bot_commands(bot)
    await dp.start_polling(bot)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_reload() -> None:
    """Restart child process when files under app/ change. Run: python -m app.main --reload"""
    from watchfiles import watch

    root = _project_root()
    app_dir = root / "app"
    cmd = [sys.executable, "-m", "app.main"]

    while True:
        proc = subprocess.Popen(cmd, cwd=root)
        try:
            for _ in watch(app_dir):
                break
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise SystemExit(0) from None
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    if "--reload" in sys.argv:
        run_reload()
    else:
        asyncio.run(main())

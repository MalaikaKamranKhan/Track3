"""Runs the API server and whichever bots have tokens, all in one process: python -m squadbot.main"""
from __future__ import annotations

import asyncio
import logging

import uvicorn

from . import config, runner
from .api import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("squad")


async def main() -> None:
    bots = []
    if config.DISCORD_TOKEN:
        from .adapters.discord_bot import DiscordAdapter
        bots.append(DiscordAdapter(config.DISCORD_TOKEN))
    if config.TELEGRAM_TOKEN:
        from .adapters.telegram_bot import TelegramAdapter
        bots.append(TelegramAdapter(config.TELEGRAM_TOKEN))
    if not bots:
        log.warning("No DISCORD_TOKEN or TELEGRAM_TOKEN set: running the API server only.")
    for bot in bots:
        runner.register(bot)
    log.info("LLM provider: %s", config.LLM_PROVIDER)

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=config.PORT, log_level="info"))
    tasks = [asyncio.create_task(server.serve(), name="api")]
    tasks += [asyncio.create_task(bot.start(), name=bot.platform) for bot in bots]
    tasks.append(asyncio.create_task(runner.scheduler(), name="scheduler"))
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            if task.exception():
                raise task.exception()
    finally:
        for bot in bots:
            try:
                await bot.stop()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    asyncio.run(main())

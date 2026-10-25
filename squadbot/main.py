"""Runs the API server and whichever bots have tokens, all in one process: python -m squadbot.main"""
from __future__ import annotations

import asyncio
import logging

import uvicorn

from . import config, runner
from .api import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s") 
logging.getLogger("httpx").setLevel(logging.WARNING)  # its request log lines include the Telegram token
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

    # Don't wait forever for open connections on Ctrl+C: tunnels like ngrok keep them alive.
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=config.PORT, log_level="info",
                                           timeout_graceful_shutdown=2))
    tasks = [asyncio.create_task(server.serve(), name="api")]
    tasks += [asyncio.create_task(bot.start(), name=bot.platform) for bot in bots]
    tasks.append(asyncio.create_task(runner.scheduler(), name="scheduler"))
    try:
        # Stop everything as soon as any part stops (Ctrl+C ends the API server normally, without an exception).
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if not task.cancelled() and task.exception():
                raise task.exception()
    finally:
        log.info("Shutting down...")
        for bot in bots:
            try:
                await asyncio.wait_for(bot.stop(), timeout=5)
            except Exception:  # noqa: BLE001
                pass
        for task in tasks:
            task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    log.info("Stopped.")

import asyncio
import logging
import os
import sys

from app.bot.bot import main
from config.config import Config, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

config: Config = load_config()

logging.getLogger().setLevel(getattr(logging, config.log.level.upper()))
for handler in logging.getLogger().handlers:
    handler.setFormatter(
        logging.Formatter(config.log.format, datefmt="%Y-%m-%d %H:%M:%S")
    )

if sys.platform.startswith("win") or os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    try:
        asyncio.run(main(config))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by signal")
    except Exception:
        logger.exception("Bot crashed with unhandled exception")
        sys.exit(1)

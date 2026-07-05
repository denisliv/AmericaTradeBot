import logging
import os
from dataclasses import dataclass

from environs import Env


@dataclass
class BotSettings:
    token: str
    admin_ids: list[int]


@dataclass
class DatabaseSettings:
    db: str
    host: str
    port: int
    user: str
    password: str
    pool_min_size: int
    pool_max_size: int


@dataclass
class RedisSettings:
    db: int
    promo_db: int
    host: str
    port: int
    username: str
    password: str


@dataclass
class LogSettings:
    level: str
    format: str


@dataclass
class CopartSettings:
    url: str


@dataclass
class BitrixSettings:
    webhook_url: str


@dataclass
class SchedulerSettings:
    timezone: str
    csv_interval_minutes: int
    newsletter_hour: int
    newsletter_minute: int
    posts_day_of_week: str
    posts_hour: int
    posts_minute: int


@dataclass
class Config:
    bot: BotSettings
    db: DatabaseSettings
    redis: RedisSettings
    log: LogSettings
    copart: CopartSettings
    bitrix: BitrixSettings
    scheduler: SchedulerSettings


def load_config(path: str | None = None) -> Config:
    env = Env()
    logger = logging.getLogger(__name__)

    if path:
        if not os.path.exists(path):
            logger.warning(".env file not found at '%s', skipping...", path)
        else:
            logger.info("Loading .env from '%s'", path)

    env.read_env(path)

    bot = BotSettings(
        token=env("BOT_TOKEN"), admin_ids=list(map(int, env.list("ADMIN_IDS")))
    )

    db = DatabaseSettings(
        db=env("POSTGRES_DB"),
        host=env("POSTGRES_HOST"),
        port=env.int("POSTGRES_PORT"),
        user=env("POSTGRES_USER"),
        password=env("POSTGRES_PASSWORD"),
        pool_min_size=env.int("POSTGRES_POOL_MIN_SIZE", default=5),
        pool_max_size=env.int("POSTGRES_POOL_MAX_SIZE", default=20),
    )

    redis_primary_db = env.int("REDIS_DATABASE")
    redis_promo_db = env.int("REDIS_PROMO_DATABASE", default=None)
    if redis_promo_db is None:
        logger.warning(
            "REDIS_PROMO_DATABASE is not set; using REDIS_DATABASE + 1 for promo Redis"
        )
        redis_promo_db = redis_primary_db + 1

    redis = RedisSettings(
        db=redis_primary_db,
        promo_db=redis_promo_db,
        host=env("REDIS_HOST"),
        port=env.int("REDIS_PORT"),
        username=env("REDIS_USERNAME", default=""),
        password=env("REDIS_PASSWORD", default=""),
    )

    copart = CopartSettings(url=env("COPART_URL"))

    bitrix = BitrixSettings(webhook_url=env("BITRIX_WEBHOOK_URL", default=""))

    scheduler = SchedulerSettings(
        timezone=env("SCHEDULER_TIMEZONE", default="Europe/Moscow"),
        csv_interval_minutes=env.int("SCHEDULER_CSV_INTERVAL_MINUTES", default=60),
        newsletter_hour=env.int("SCHEDULER_NEWSLETTER_HOUR", default=9),
        newsletter_minute=env.int("SCHEDULER_NEWSLETTER_MINUTE", default=20),
        posts_day_of_week=env("SCHEDULER_POSTS_DAY_OF_WEEK", default="wed"),
        posts_hour=env.int("SCHEDULER_POSTS_HOUR", default=19),
        posts_minute=env.int("SCHEDULER_POSTS_MINUTE", default=0),
    )

    log_settings = LogSettings(
        level=env("LOG_LEVEL", default="INFO"),
        format=env(
            "LOG_FORMAT",
            default="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
        ),
    )

    logger.info("Configuration loaded successfully")

    return Config(
        bot=bot,
        db=db,
        redis=redis,
        log=log_settings,
        copart=copart,
        bitrix=bitrix,
        scheduler=scheduler,
    )

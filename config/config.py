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


@dataclass
class RedisSettings:
    db: int
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
class OpenAISettings:
    api_key: str
    base_url: str
    model_name: str


@dataclass
class Config:
    bot: BotSettings
    db: DatabaseSettings
    redis: RedisSettings
    log: LogSettings
    copart: CopartSettings
    openai: OpenAISettings


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
    )

    redis = RedisSettings(
        db=env.int("REDIS_DATABASE"),
        host=env("REDIS_HOST"),
        port=env.int("REDIS_PORT"),
        username=env("REDIS_USERNAME", default=""),
        password=env("REDIS_PASSWORD", default=""),
    )

    copart = CopartSettings(url=env("COPART_URL"))

    openai = OpenAISettings(
        api_key=env("API_KEY", default="your-openai-api-key-here"),
        base_url=env("BASE_URL", default="https://api.openai.com/v1"),
        model_name=env("MODEL_NAME", default="gpt-3.5-turbo"),
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
        bot=bot, db=db, redis=redis, log=log_settings, copart=copart, openai=openai
    )

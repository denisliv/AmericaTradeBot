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
class OpenAISettings:
    api_key: str
    base_url: str
    model_name: str


@dataclass
class EmbeddingsSettings:
    api_key: str
    base_url: str
    model_name: str


@dataclass
class BitrixSettings:
    webhook_url: str
    source: str


@dataclass
class AIManagerSettings:
    max_history_messages: int
    rag_top_k: int
    rag_score_threshold: float
    faiss_index_path: str
    knowledge_file_path: str
    lead_confidence_threshold: float
    search_result_count: int


@dataclass
class Config:
    bot: BotSettings
    db: DatabaseSettings
    redis: RedisSettings
    log: LogSettings
    copart: CopartSettings
    openai: OpenAISettings
    embeddings: EmbeddingsSettings
    bitrix: BitrixSettings
    ai_manager: AIManagerSettings


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

    openai = OpenAISettings(
        api_key=env("API_KEY", default="your-openai-api-key-here"),
        base_url=env("BASE_URL", default="https://api.openai.com/v1"),
        model_name=env("MODEL_NAME", default="gpt-5-mini"),
    )

    embeddings = EmbeddingsSettings(
        api_key=env("EMBEDDINGS_API_KEY", default=openai.api_key),
        base_url=env("EMBEDDINGS_BASE_URL", default=openai.base_url),
        model_name=env("EMBEDDINGS_MODEL_NAME", default="text-embedding-3-small"),
    )

    bitrix = BitrixSettings(
        webhook_url=env(
            "BITRIX_WEBHOOK_URL",
            default="",
        ),
        source=env("BITRIX_SOURCE", default="AI Manager (Telegram)"),
    )

    ai_manager = AIManagerSettings(
        max_history_messages=env.int("AI_MANAGER_MAX_HISTORY_MESSAGES", default=20),
        rag_top_k=env.int("AI_MANAGER_RAG_TOP_K", default=4),
        # Cosine relevance score on [0,1]; OpenAI embeddings usually cluster around 0.3–0.8.
        rag_score_threshold=env.float("AI_MANAGER_RAG_SCORE_THRESHOLD", default=0.3),
        faiss_index_path=env(
            "AI_MANAGER_FAISS_INDEX_PATH",
            default="data/vectorstore/ai_manager",
        ),
        knowledge_file_path=env(
            "AI_MANAGER_KNOWLEDGE_FILE",
            default="data/ai_manager/agent.md",
        ),
        lead_confidence_threshold=env.float(
            "AI_MANAGER_LEAD_CONFIDENCE_THRESHOLD", default=0.75
        ),
        search_result_count=env.int("AI_MANAGER_SEARCH_RESULT_COUNT", default=3),
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
        openai=openai,
        embeddings=embeddings,
        bitrix=bitrix,
        ai_manager=ai_manager,
    )

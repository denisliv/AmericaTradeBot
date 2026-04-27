"""Top-level AI manager service: glue between config, LLM, tools and the graph."""

import logging
from pathlib import Path

from langchain_openai import ChatOpenAI
from psycopg import AsyncConnection

from app.infrastructure.services.ai_manager.agent_graph import AIManagerGraphService
from app.infrastructure.services.ai_manager.knowledge_base import KnowledgeBaseService
from app.infrastructure.services.ai_manager.metrics import AIManagerMetrics
from app.infrastructure.services.ai_manager.schemas import AIReply
from app.infrastructure.services.ai_manager.tools import AIManagerTools
from app.infrastructure.services.ai_manager.user_context import UserContextService
from config.config import Config

logger = logging.getLogger(__name__)


def _chat_openai_kwargs(config: Config) -> dict:
    kwargs = {
        "openai_api_key": config.openai.api_key,
        "base_url": config.openai.base_url,
        "model_name": config.openai.model_name,
        "temperature": 0.4,
        "max_tokens": 4800,
    }
    if config.openai.model_name.startswith("gpt-5"):
        kwargs["reasoning_effort"] = "low"
    return kwargs


class AIManagerService:
    def __init__(self, config: Config):
        self.config = config
        self.llm = ChatOpenAI(**_chat_openai_kwargs(config))
        self.metrics = AIManagerMetrics()
        self.knowledge_base = KnowledgeBaseService(
            knowledge_file_path=config.ai_manager.knowledge_file_path,
            index_path=config.ai_manager.faiss_index_path,
            embeddings_api_key=config.embeddings.api_key,
            embeddings_base_url=config.embeddings.base_url,
            embeddings_model_name=config.embeddings.model_name,
            score_threshold=config.ai_manager.rag_score_threshold,
        )
        self.tools = AIManagerTools()
        self.user_context_service = UserContextService()
        cars_md = Path(config.ai_manager.knowledge_file_path).parent / "cars.md"
        self.graph = AIManagerGraphService(
            llm=self.llm,
            rag=self.knowledge_base,
            tools=self.tools,
            context_service=self.user_context_service,
            metrics=self.metrics,
            rag_top_k=config.ai_manager.rag_top_k,
            search_result_count=config.ai_manager.search_result_count,
            lead_confidence_threshold=config.ai_manager.lead_confidence_threshold,
            max_history_messages=config.ai_manager.max_history_messages,
            cars_catalog_path=cars_md,
        )

        try:
            self.knowledge_base.ensure_index()
        except Exception as exc:
            logger.exception("Failed to initialize AI manager index: %s", exc)

    def is_valid_api_key(self) -> bool:
        """Checks if AI manager LLM key is configured."""
        api_key = self.config.openai.api_key.strip()
        return api_key != "" and api_key != "your-openai-api-key-here"

    async def get_reply(
        self,
        conn: AsyncConnection,
        *,
        user_id: int,
        username: str | None,
        message: str,
    ) -> AIReply:
        """Structured response: text + optional list of CarCard + lead flag."""
        reply = await self.graph.run(
            conn=conn,
            user_id=user_id,
            username=username,
            message=message,
        )
        self.metrics.log_snapshot()
        return reply

    async def get_response(
        self,
        conn: AsyncConnection,
        *,
        user_id: int,
        username: str | None,
        message: str,
    ) -> str:
        """Backward-compatible helper that returns only the textual reply."""
        reply = await self.get_reply(
            conn, user_id=user_id, username=username, message=message
        )
        return reply.text

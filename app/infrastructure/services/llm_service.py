import logging
from typing import Any, Dict, List, Optional

from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.llm = ChatOpenAI(
            openai_api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            temperature=0.7,
            max_tokens=1000,
        )

        # Максимальное количество сообщений в истории для предотвращения превышения лимитов
        self.max_history_messages = 20

        # Системный промпт для бота
        self.system_prompt = """Ты - AI-ассистент компании AmericaTrade, специализирующейся на подборе и покупке автомобилей из США.

Твоя роль:
- Помогать пользователям с вопросами о покупке автомобилей из США и доставке в Беларусь
- Объяснять процесс покупки, доставки и таможенного оформления
- Давать советы по выбору автомобиля
- Отвечать на вопросы о компании и услугах
- Быть дружелюбным и профессиональным

Информация о компании:
- AmericaTrade работает в Республике Беларусь
- AmericaTrade работает более 10 лет
- Специализируется на автомобилях из США с экономией до 40%
- Специализируется на доставке автомобилей из США в Беларусь
- Предоставляет полное сопровождение от подбора до постановки на учет
- Работает только по договору с оплатой через банк

Всегда отвечай на русском языке, будь полезным и информативным. 
Если вопрос не относится к компании AmericaTrade или автомобильной тематике, то отвечай, что ты не специалист в этой области.
Если не знаешь ответа на вопрос, честно скажи об этом и предложи обратиться к менеджерам компании."""

    def _validate_conversation_history(
        self, history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Валидирует и очищает историю разговора

        Args:
            history: История разговора

        Returns:
            Валидированная история разговора
        """
        if not history:
            return []

        validated_history = []
        for msg in history:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                if msg["role"] in ["user", "assistant"] and isinstance(
                    msg["content"], str
                ):
                    validated_history.append(
                        {"role": msg["role"], "content": msg["content"].strip()}
                    )

        return validated_history

    def _limit_conversation_history(
        self, history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Ограничивает количество сообщений в истории для предотвращения превышения лимитов

        Args:
            history: История разговора

        Returns:
            Ограниченная история разговора
        """
        if len(history) <= self.max_history_messages:
            return history

        # Оставляем последние N сообщений
        return history[-self.max_history_messages :]

    async def get_response(
        self,
        user_id: int,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Получает ответ от LLM модели с учетом истории разговора

        Args:
            user_id: ID пользователя
            message: Сообщение пользователя
            conversation_history: История разговора

        Returns:
            Ответ от LLM модели
        """
        try:
            # Валидируем и ограничиваем историю
            validated_history = self._validate_conversation_history(
                conversation_history or []
            )
            limited_history = self._limit_conversation_history(validated_history)

            # Формируем сообщения для модели
            messages = [SystemMessage(content=self.system_prompt)]

            # Добавляем историю разговора
            for msg in limited_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

            # Добавляем текущее сообщение пользователя
            messages.append(HumanMessage(content=message.strip()))

            # Получаем ответ от модели
            response = await self.llm.ainvoke(messages)

            logger.info(
                f"LLM response generated for user {user_id} (history: {len(limited_history)} messages)"
            )
            return response.content

        except Exception as e:
            logger.error(f"Error getting LLM response for user {user_id}: {e}")
            return "Извините, произошла ошибка при обработке вашего сообщения. Попробуйте позже или обратитесь к менеджеру."

    def is_valid_api_key(self) -> bool:
        """Проверяет, является ли API ключ валидным (не заглушкой)"""
        return self.api_key != "your-openai-api-key-here" and self.api_key.strip() != ""

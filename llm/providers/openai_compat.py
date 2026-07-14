"""OpenAI 兼容接口 Provider — 支持千问、DeepSeek 等所有 OpenAI 兼容 API"""

import os
from openai import AsyncOpenAI
from ..base import LLMMessage, LLMResponse, LLMConfig, BaseLLMProvider
from utils.logger import get_logger

logger = get_logger(__name__)


class OpenAICompatProvider(BaseLLMProvider):
    """通过 OpenAI 兼容接口调用任意 LLM"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        api_key = os.path.expandvars(config.api_key) if "$" in config.api_key else config.api_key
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.base_url or None,
        )
        self.model_id = config.model

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 1.0,
        top_p: float = 0.8,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        logger.info(
            "LLM [%s] calling model=%s, messages=%d, temp=%.1f",
            self.name, self.model_id, len(messages), temperature,
        )
        response = await self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        content = choice.message.content or ""

        return LLMResponse(
            content=content,
            model=self.model_id,
            provider_name=self.name,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

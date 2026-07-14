"""LLM 路由器 — 按优先级自动 fallback"""

import os
import asyncio
from pathlib import Path
from typing import Optional
import yaml

from .base import LLMConfig, LLMMessage, LLMResponse, BaseLLMProvider
from .providers.openai_compat import OpenAICompatProvider
from utils.logger import get_logger

logger = get_logger(__name__)

# Provider factory
_PROVIDER_TYPES = {
    "openai_compat": OpenAICompatProvider,
    # "anthropic": AnthropicProvider,  # 后续扩展
}


def _resolve_env(value: str) -> str:
    """解析 ${ENV_VAR} 占位符"""
    # 确保 dotenv 已加载
    from config.settings import PROJECT_ROOT
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.getenv(env_var, "")
    return value


def load_providers(config_path: Optional[Path] = None) -> list[BaseLLMProvider]:
    """从 YAML 配置文件加载所有 Provider 实例，按 priority 排序"""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "llm_providers.yaml"

    if not config_path.exists():
        logger.warning("LLM config not found at %s, using empty provider list", config_path)
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    providers = []
    for item in data.get("providers", []):
        config = LLMConfig(
            name=item["name"],
            type=item["type"],
            base_url=_resolve_env(item.get("base_url", "")),
            api_key=_resolve_env(item.get("api_key", "")),
            model=item.get("model", ""),
            priority=item.get("priority", 1),
            params=item.get("params", {}),
        )
        provider_cls = _PROVIDER_TYPES.get(config.type)
        if provider_cls is None:
            logger.warning("Unknown provider type '%s', skipping '%s'", config.type, config.name)
            continue
        if not config.api_key:
            logger.info("Provider '%s' has no API key configured, skipping", config.name)
            continue
        providers.append(provider_cls(config))

    providers.sort(key=lambda p: p.config.priority)
    logger.info("Loaded %d LLM providers: %s", len(providers), [p.name for p in providers])
    return providers


class LLMRouter:
    """多 LLM 路由器：按 priority 依次尝试，失败自动 fallback"""

    def __init__(self, config_path: Optional[Path] = None):
        self.providers = load_providers(config_path)

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 1.0,
        top_p: float = 0.8,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """发送消息，按优先级尝试所有 Provider，全部失败则抛出 RuntimeError"""
        errors = []
        for provider in self.providers:
            if not provider.is_available():
                logger.info("Provider '%s' unavailable (no API key), skipping", provider.name)
                continue
            try:
                response = await provider.chat(messages, temperature, top_p, max_tokens)
                logger.info("LLM [%s] succeeded (model=%s, tokens=%s)", provider.name, response.model, response.usage)
                return response
            except Exception as e:
                logger.warning("LLM [%s] failed: %s", provider.name, e)
                errors.append(f"{provider.name}: {e}")
                continue

        raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")

    def chat_sync(
        self,
        messages: list[LLMMessage],
        temperature: float = 1.0,
        top_p: float = 0.8,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """同步包装器"""
        return asyncio.run(self.chat(messages, temperature, top_p, max_tokens))


# 全局单例
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router

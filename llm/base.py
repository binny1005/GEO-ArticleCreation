"""LLM 适配器基类 — 所有 Provider 必须实现此接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMMessage:
    """一条对话消息"""
    role: str           # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """LLM 调用响应"""
    content: str
    model: str
    provider_name: str
    usage: dict = field(default_factory=dict)  # {"prompt_tokens": N, "completion_tokens": N}


@dataclass
class LLMConfig:
    """单个 Provider 的配置"""
    name: str
    type: str               # "openai_compat" | "anthropic"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    priority: int = 1
    params: dict = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.name = config.name

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 1.0,
        top_p: float = 0.8,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """发送消息，返回 LLMResponse。失败时抛出异常"""
        ...

    def is_available(self) -> bool:
        """检查 Provider 是否可用（API Key 存在 + 网络可达）"""
        return bool(self.config.api_key)

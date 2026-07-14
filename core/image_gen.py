"""配图提示词生成 — 标题图 + 2张插图（行业风格驱动，纯输出不嵌入）"""

import json
import re
from dataclasses import dataclass, field

from prompts.image_styles import (
    get_style,
    TITLE_IMAGE_SYSTEM, TITLE_IMAGE_USER,
    INSERT_IMAGE_SYSTEM, INSERT_IMAGE_USER,
)
from llm.router import get_router, LLMMessage
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TitleImage:
    """标题图提示词"""
    description: str = ""
    prompt: str = ""
    negative: str = ""


@dataclass
class InsertImage:
    """文内插图提示词"""
    type: str = ""
    description: str = ""
    prompt: str = ""


def _render_system(template: str, style: dict) -> str:
    """将行业风格注入 System Prompt"""
    return (template
            .replace("{{ style }}", style.get("style", ""))
            .replace("{{ palette }}", style.get("palette", ""))
            .replace("{{ lighting }}", style.get("lighting", ""))
            .replace("{{ scene_logic }}", style.get("scene_logic", ""))
            .replace("{{ flowchart_logic }}", style.get("flowchart_logic", "")))


def generate_title_image(title: str, paper: str, question: str, product: str, industry: str) -> TitleImage:
    """生成封面标题图提示词"""
    style = get_style(industry)
    system_prompt = _render_system(TITLE_IMAGE_SYSTEM, style)

    summary = paper[:300].replace("\n", " ").replace("#", "").strip()
    user_prompt = (TITLE_IMAGE_USER
                   .replace("{{ title }}", title)
                   .replace("{{ summary }}", summary)
                   .replace("{{ product }}", product))

    router = get_router()
    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ],
        temperature=0.7, top_p=0.8, max_tokens=600,
    )

    result = TitleImage()
    text = response.content
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("画面") and "：" in line:
            result.description = line.split("：", 1)[1].strip()
        elif line.startswith("Prompt:") or line.startswith("正向"):
            result.prompt = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()
        elif line.startswith("Negative:") or line.startswith("负向"):
            result.negative = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()

    return result


def generate_insert_images(paper: str, title: str, industry: str) -> list[InsertImage]:
    """生成2张文内插图提示词（场景图 + 流程图）"""
    style = get_style(industry)
    system_prompt = _render_system(INSERT_IMAGE_SYSTEM, style)
    user_prompt = (INSERT_IMAGE_USER
                   .replace("{{ title }}", title)
                   .replace("{{ paper }}", paper))

    router = get_router()
    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ],
        temperature=0.7, top_p=0.8, max_tokens=600,
    )

    # 解析 JSON 数组
    json_match = re.search(r'\[[\s\S]*\]', response.content)
    if json_match:
        try:
            items = json.loads(json_match.group(0))
            return [
                InsertImage(
                    type=item.get("type", ""),
                    description=item.get("description", ""),
                    prompt=item.get("prompt", ""),
                )
                for item in items[:2]  # 确保最多2张
            ]
        except json.JSONDecodeError:
            pass

    return []

"""字段匹配与评估器 — 阶段 [2] 核心逻辑"""

import json
import re
from dataclasses import dataclass, field

from knowledge.schema import BizParams
from knowledge.loader import extract_sections_for_prompt, extract_constraint_for_prompt
from prompts.field_match import FIELD_MATCH_SYSTEM, FIELD_MATCH_USER
from llm.router import get_router, LLMMessage
from utils.logger import get_logger
from jinja2 import Template

logger = get_logger(__name__)


@dataclass
class FieldMatchResult:
    """单条种子问题的字段匹配结果"""
    entry_text: str = ""
    dimension: str = ""
    field_refs: list[str] = field(default_factory=list)
    match_degree: str = "一般"       # "强相关" | "一般" | "弱"
    is_sufficient: bool = False      # 基础问答是否充足
    can_expand: bool = False         # 能否拓展为2000字推广文
    reason: str = ""


def _parse_llm_output(text: str) -> dict:
    """解析 LLM JSON 输出（处理可能的 markdown 代码块包裹）"""
    # 尝试提取 JSON
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def match_field(
    entry_text: str,
    dimension: str,
    biz_params: BizParams,
) -> FieldMatchResult:
    """
    对单条种子问题进行字段匹配与资料充足度评估。

    Returns:
        FieldMatchResult — 匹配后的结构化结果
    """
    user_prompt = Template(FIELD_MATCH_USER).render(
        entry_text=entry_text,
        sections=extract_sections_for_prompt(biz_params),
        constraint_fields=extract_constraint_for_prompt(biz_params),
    )

    router = get_router()
    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content=FIELD_MATCH_SYSTEM),
            LLMMessage(role="user", content=user_prompt),
        ],
        temperature=0.7,
        top_p=0.8,
        max_tokens=2048,
    )

    data = _parse_llm_output(response.content)

    # 构建结果
    sufficiency = data.get("dataSufficiency", {})
    return FieldMatchResult(
        entry_text=data.get("entryText", entry_text),
        dimension=dimension,
        field_refs=data.get("fieldRefs", []),
        match_degree=data.get("matchDegree", "一般"),
        is_sufficient=sufficiency.get("isSufficiented", False),
        can_expand=sufficiency.get("referenceStatus", False),
        reason=sufficiency.get("reason", ""),
    )

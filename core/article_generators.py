"""文章生成器 — 阶段 [3][4][5] + 权重路由器"""

import json
import random
import re
from dataclasses import dataclass, field
from typing import Optional

from jinja2 import Template

from knowledge.schema import BizParams
from knowledge.loader import extract_sections_for_prompt, extract_constraint_for_prompt
from prompts.phase_articles import (
    PHASE1_PARSE_SYSTEM,
    PHASE1_ARTICLE_SYSTEM,
    PHASE2_ARTICLE_SYSTEM,
    STABLE_ARTICLE_SYSTEM,
    ARTICLE_USER_TEMPLATE,
    ARTICLE_STAGE_WEIGHTS,
)
from llm.router import get_router, LLMMessage
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Article:
    """一篇文章"""
    title: str
    paper: str          # 正文 (Markdown)
    stage: str          # "phase1" | "phase2" | "stable"
    seed_question: str = ""
    dimension: str = ""


# ── 阶段名称映射 ──
STAGE_SYSTEM_PROMPTS = {
    "phase1": PHASE1_ARTICLE_SYSTEM,
    "phase2": PHASE2_ARTICLE_SYSTEM,
    "stable": STABLE_ARTICLE_SYSTEM,
}

STAGE_LABELS = {
    "phase1": "一阶段养号文(科普避坑)",
    "phase2": "二阶段养号文(深度解析)",
    "stable": "平稳期营销文(SEO知识型)",
}


def _select_stage(weights: Optional[dict] = None) -> str:
    """按权重随机选择一个文章生成阶段"""
    if weights is None:
        weights = ARTICLE_STAGE_WEIGHTS
    stages = list(weights.keys())
    w = [weights[s] for s in stages]
    return random.choices(stages, weights=w, k=1)[0]


def _parse_point_scene(seed_question: str, biz_params: BizParams) -> dict:
    """
    调用 LLM 解析种子问题 → 提取 point(核心痛点) + scene(受众钩子)
    阶段[3]和[4]需要这一步骤，阶段[5]不需要
    """
    router = get_router()
    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content=PHASE1_PARSE_SYSTEM),
            LLMMessage(role="user", content=f"原始提问：{seed_question}"),
        ],
        temperature=0.7,
        top_p=0.8,
        max_tokens=1024,
    )
    # 提取 JSON
    json_match = re.search(r'\{[\s\S]*\}', response.content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return {"point": seed_question, "scene": "通用场景"}


def _render_article_user_prompt(
    seed_question: str,
    point: str,
    scene: str,
    biz_params: BizParams,
    referenced_fields: str = "",
    base_fields: str = "",
    match_context: str = "",
    length_min: int = 800,
    length_max: int = 2000,
    title_length: int = 30,
) -> str:
    """构建文章生成的 User Prompt"""
    return Template(ARTICLE_USER_TEMPLATE).render(
        entry_term=seed_question,
        point=point,
        scene=scene,
        constraint_fields=extract_constraint_for_prompt(biz_params),
        company_name=biz_params.company_name,
        core_product=biz_params.coreProductName,
        length_min=length_min,
        length_max=length_max,
        title_length=title_length,
        referenced_fields=referenced_fields,
        base_fields=base_fields,
        match_context=match_context,
    )


def generate_article(
    seed_question: str,
    dimension: str = "",
    biz_params: Optional[BizParams] = None,
    stage: Optional[str] = None,
    weights: Optional[dict] = None,
    base_fields: str = "",
    referenced_fields: str = "",
    match_context: str = "",
    length_min: int = 800,
    length_max: int = 2000,
    title_length: int = 30,
) -> Article:
    """
    对单条种子问题生成一篇文章。

    Args:
        seed_question: 种子问题文本
        dimension: 内容维度
        biz_params: 知识库参数
        stage: 强制指定阶段（None = 按权重随机）
        weights: 自定义权重

    Returns:
        Article
    """
    if stage is None:
        stage = _select_stage(weights)

    label = STAGE_LABELS.get(stage, stage)
    logger.info("种子问题: %s → 路由到 %s", seed_question[:30], label)

    # 阶段 [3][4] 需要先解析 point + scene，阶段 [5] 直接生成
    if stage in ("phase1", "phase2"):
        ps = _parse_point_scene(seed_question, biz_params)
        point = ps.get("point", seed_question)
        scene = ps.get("scene", "通用场景")
    else:
        point = seed_question
        scene = "通用场景"

    # 构建 prompts
    system_prompt = Template(STAGE_SYSTEM_PROMPTS[stage]).render(
        title_length=title_length,
    )
    user_prompt = _render_article_user_prompt(
        seed_question, point, scene, biz_params,
        referenced_fields=referenced_fields,
        base_fields=base_fields,
        match_context=match_context,
        length_min=length_min, length_max=length_max, title_length=title_length,
    )

    # 调用 LLM（含 1 次 JSON 解析失败重试）
    router = get_router()
    msgs = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_prompt),
    ]

    title, paper = None, None
    for attempt in range(2):
        if attempt == 1:
            msgs.append(LLMMessage(role="user", content="请严格输出 JSON，不要附加任何解释。"))
            logger.warning("首次 JSON 解析失败，重试中...")

        response = router.chat_sync(messages=msgs, temperature=1.0, top_p=0.8, max_tokens=4096)
        match = re.search(r'\{[\s\S]*\}', response.content)
        if match:
            try:
                data = json.loads(match.group(0))
                title, paper = data.get("title"), data.get("paper")
                if title and paper:
                    break
            except json.JSONDecodeError:
                pass

    if title is not None and paper:
        return Article(title=title, paper=paper, stage=stage,
                       seed_question=seed_question, dimension=dimension)

    # Fallback: 两次均失败，返回最后一次原始输出
    return Article(title=seed_question, paper=response.content, stage=stage,
                   seed_question=seed_question, dimension=dimension)

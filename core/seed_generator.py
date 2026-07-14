"""种子问题生成器 — 阶段 [1] 核心逻辑"""

import re
from jinja2 import Template

from knowledge.schema import BizParams
from knowledge.loader import extract_sections_for_prompt, extract_constraint_for_prompt
from prompts.industry_registry import get_industry_prompt
from llm.router import get_router, LLMMessage
from utils.logger import get_logger

logger = get_logger(__name__)


def _render_user_prompt(biz_params: BizParams) -> str:
    """构建 User Prompt（包含知识库数据）"""
    template = Template("""企业名称：{{ companyName }}
产品名称：{{ coreProductName }}
生成的种子问题条数：{{ entryCount }}
行业类别：{{ primaryIndustryName }}
企业知识库中可作为事实来源的结构化企业资料：{{ sections }}
敏感词库：{{ constraintFields }}""")

    return template.render(
        companyName=biz_params.companyName,
        coreProductName=biz_params.coreProductName,
        entryCount=biz_params.entryCount,
        primaryIndustryName=biz_params.primary_industry_name,
        sections=extract_sections_for_prompt(biz_params),
        constraintFields=extract_constraint_for_prompt(biz_params),
    )


def parse_seed_output(text: str) -> list[dict]:
    """
    解析 LLM 输出的种子问题文本。
    格式: 词条序号|内容维度|问题1内容|
    返回: [{seq, dimension, question}, ...]
    """
    results = []
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        # 尝试多种分隔符
        parts = None
        for sep in ["|", "｜"]:
            if sep in line:
                parts = [p.strip() for p in line.split(sep)]
                break
        if not parts or len(parts) < 3:
            # 尝试用制表符
            parts = [p.strip() for p in line.split("\t")]

        if parts and len(parts) >= 3:
            # 过滤掉表头行
            first = parts[0]
            if any(kw in first for kw in ["序号", "维度", "内容", "词条"]):
                continue
            try:
                seq = int(first)
            except ValueError:
                seq = len(results) + 1

            results.append({
                "seq": seq,
                "dimension": parts[1] if len(parts) > 1 else "",
                "question": parts[2] if len(parts) > 2 else "",
            })

    return results


def generate_seeds(
    biz_params: BizParams,
    industry: str | None = None,
) -> list[dict]:
    """
    生成种子问题。

    Args:
        biz_params: 知识库业务参数
        industry: 行业分类（不传则用 biz_params.primary_industry_name）

    Returns:
        [{seq, dimension, question}, ...]
    """
    if industry is None:
        industry = biz_params.primary_industry_name

    # 获取行业对应的 System Prompt 并渲染
    system_prompt = get_industry_prompt(industry)
    # 把 System Prompt 中的 {{ }} 替换为实际值
    system_prompt_rendered = Template(system_prompt).render(
        companyName=biz_params.companyName,
        coreProductName=biz_params.coreProductName,
        entryCount=biz_params.entryCount,
        primaryIndustryName=industry,
        sections=extract_sections_for_prompt(biz_params),
        constraintFields=extract_constraint_for_prompt(biz_params),
    )

    user_prompt = _render_user_prompt(biz_params)

    logger.info("行业=%s, 目标条数=%d, 开始调用 LLM...", industry, biz_params.entryCount)

    router = get_router()
    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content=system_prompt_rendered),
            LLMMessage(role="user", content=user_prompt),
        ],
        temperature=1.0,
        top_p=0.8,
        max_tokens=4096,
    )

    seeds = parse_seed_output(response.content)
    logger.info("生成完成: 实际获取 %d 条种子问题", len(seeds))
    return seeds

"""文章审核模块 — 去AI化检测 + GEO收录评分"""

import json
import re
from dataclasses import dataclass, field

from prompts.article_review import ARTICLE_REVIEW_SYSTEM, ARTICLE_REVIEW_USER
from llm.router import get_router, LLMMessage
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ReviewResult:
    """文章审核结果"""
    ai_score: int = 0              # 去AI化评分 (0-100, 越高越不像AI)
    ai_issues: list[str] = field(default_factory=list)
    geo_score: int = 0             # GEO收录评分 (0-100)
    geo_detail: dict = field(default_factory=dict)
    overall: str = "revise"        # pass / revise / rewrite
    suggestions: list[str] = field(default_factory=list)


def review_article(question: str, title: str, paper: str) -> ReviewResult:
    """
    审核单篇文章：去AI化检测 + GEO收录评分。

    返回 ReviewResult，含综合评分和修改建议。
    """
    router = get_router()
    user_prompt = (ARTICLE_REVIEW_USER
                   .replace("{{ question }}", question)
                   .replace("{{ title }}", title)
                   .replace("{{ paper }}", paper))

    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content=ARTICLE_REVIEW_SYSTEM),
            LLMMessage(role="user", content=user_prompt),
        ],
        temperature=0.3, top_p=0.8, max_tokens=1024,
    )

    # handle possible markdown code blocks
    raw = response.content
    code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    json_match = re.search(r'\{[\s\S]*\}', code_match.group(1) if code_match else raw)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            return ReviewResult(
                ai_score=int(data.get("ai_score", 0)),
                ai_issues=data.get("ai_issues", []),
                geo_score=int(data.get("geo_score", 0)),
                geo_detail=data.get("geo_detail", {}),
                overall=data.get("overall", "revise"),
                suggestions=data.get("suggestions", []),
            )
        except (json.JSONDecodeError, ValueError):
            pass

    return ReviewResult(overall="revise", suggestions=["审核解析失败，建议人工复核"])


REVISE_SYSTEM = """# Role
你是一个专业的内容修改编辑。根据审核报告逐条修改原文。

# 修改规则
1. 只修改审核报告中指出的问题，保留原文其他内容不变
2. 不要重写全文，精准定位问题段落/句子，替换或调整
3. 改完后输出完整的修改后文章
4. 在文末附加一段「修改说明」，列出实际做了哪些改动

# Output Format
严格输出以下 JSON：
{
  "title": "修改后的标题（可能与原标题相同）",
  "paper": "修改后的全文 Markdown",
  "changes": ["改动1说明", "改动2说明"]
}"""


REVISE_USER = """原文标题：{{ title }}

原文正文：
{{ paper }}

审核报告：
- 去AI化评分: {{ ai_score }}/100
- AI痕迹: {{ ai_issues }}
- GEO收录评分: {{ geo_score }}/100
- 修改建议: {{ suggestions }}

请逐条修改上述问题。"""


def revise_article(title: str, paper: str, rr: ReviewResult) -> dict:
    """
    根据审核报告逐条修改原文。
    返回 {"title": str, "paper": str, "changes": [str]}
    """
    router = get_router()
    user_prompt = (REVISE_USER
                   .replace("{{ title }}", title)
                   .replace("{{ paper }}", paper)
                   .replace("{{ ai_score }}", str(rr.ai_score))
                   .replace("{{ ai_issues }}", ", ".join(rr.ai_issues[:5]))
                   .replace("{{ geo_score }}", str(rr.geo_score))
                   .replace("{{ suggestions }}", "\n".join(f"- {s}" for s in rr.suggestions)))

    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content=REVISE_SYSTEM),
            LLMMessage(role="user", content=user_prompt),
        ],
        temperature=0.5, top_p=0.8, max_tokens=4096,
    )

    # handle possible markdown code blocks
    raw = response.content
    code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    json_match = re.search(r'\{[\s\S]*\}', code_match.group(1) if code_match else raw)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            return {
                "title": data.get("title", title),
                "paper": data.get("paper", paper),
                "changes": data.get("changes", []),
            }
        except json.JSONDecodeError:
            pass

    return {"title": title, "paper": paper, "changes": ["自动修改失败，保留原文"]}


def format_review_markdown(rr: ReviewResult, stage: str = "", question: str = "") -> str:
    """将审核结果格式化为 Markdown 文本"""
    status_label = {"pass": "✅ 通过", "revise": "⚠️ 需修改", "rewrite": "❌ 建议重写"}

    lines = [
        "\n---\n",
        "## 文章审核报告\n",
    ]

    if stage or question:
        lines.append(f"> 阶段: {stage} | 种子问题: {question}\n")

    lines += [
        f"| 指标 | 评分 | 说明 |",
        f"|------|------|------|",
        f"| 去AI化 | {rr.ai_score}/100 | AI痕迹: {', '.join(rr.ai_issues[:3]) if rr.ai_issues else '无明显痕迹'} |",
        f"| GEO收录 | {rr.geo_score}/100 | 综合判定: {status_label.get(rr.overall, rr.overall)} |",
    ]

    if rr.geo_detail:
        lines.append(f"| 信息密度 | {rr.geo_detail.get('info_density', '-')}/25 | |")
        lines.append(f"| 结构适配 | {rr.geo_detail.get('structure', '-')}/20 | |")
        lines.append(f"| 权威信号 | {rr.geo_detail.get('authority', '-')}/15 | |")
        lines.append(f"| 问题匹配 | {rr.geo_detail.get('relevance', '-')}/20 | |")
        lines.append(f"| 独特性 | {rr.geo_detail.get('uniqueness', '-')}/10 | |")
        lines.append(f"| 引用友好 | {rr.geo_detail.get('citation_friendly', '-')}/10 | |")

    if rr.suggestions:
        lines.append("\n**修改建议：**\n")
        for s in rr.suggestions:
            lines.append(f"- {s}")

    lines.append("")  # trailing newline
    return "\n".join(lines)

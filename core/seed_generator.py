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


# ── 种子问题校验 ──

# 变相品牌词（暗示特定服务商）
_FORBIDDEN_WORDS = ["你们", "我们", "咱们", "俺们"]

# 常见疑问词尾 —— 去掉后检查剩余主体是否足够长
_QUESTION_TAIL = re.compile(
    r"(行吗|可以吗|能做吗|能买吗|能用吗|能办吗|能接吗|能做不|能接不|"
    r"靠谱吗|有用吗|有效吗|能省吗|值吗|有必要吗|划算吗|"
    r"贵不贵|值不值|好吗|对吗|安全吗|方便吗|合适吗|难不难|"
    r"怎么选|怎么弄|怎么搞|怎么办|怎么处理|怎么收费|怎么收费的|"
    r"多少钱|多少费用|多少预算|什么价|什么价格|啥价|"
    r"咋办|咋选|咋弄|咋收费|有推荐吗|推荐一下|求推荐|"
    r"哪个好|怎么比|哪个划算|哪个便宜|哪个靠谱|"
    r"有坑吗|会踩坑吗|能退吗|能加急吗|有售后吗|"
    r"含不含|包不包|能不能做|做不做得了|接不接|"
    r"能不能只做|能做多少|最少做多少|能做几个)$"
)


def _validate_seed(question: str) -> tuple[bool, str]:
    """
    校验单条种子问题是否合格。
    返回 (is_valid, reason)
    """
    # 1. 禁止变相品牌词
    for word in _FORBIDDEN_WORDS:
        if word in question:
            return False, f"包含变相品牌词: {word}"

    # 2. 最小长度检查（至少 8 字）
    if len(question) < 8:
        return False, f"长度不足({len(question)}字)，缺少业务语境"

    # 3. 主语/对象完整性：去掉疑问词尾后应有实质内容
    body = _QUESTION_TAIL.sub("", question)
    body = re.sub(r"[？?！!。，,、\s]", "", body)
    if len(body) < 4:
        return False, f"缺少业务对象(主体仅{len(body)}字: '{body}')"

    return True, ""


def _fix_seeds(
    failed_seeds: list[dict],
    biz_params,
    industry: str,
    valid_dimensions: list[str],
) -> list[dict]:
    """
    将校验失败的种子发给 LLM 补生成（修复主语/场景完整性）。
    返回修复后的种子列表。
    """
    failed_text = "\n".join(
        f"{s['seq']}. [{s['dimension']}] {s['question']}  —拒绝原因: {s.get('_fail_reason', '')}"
        for s in failed_seeds
    )

    fix_prompt = f"""以下种子问题因缺少主语/业务对象或包含变相品牌词被拒绝，请修复后重新输出。
要求：每条问题必须让陌生人一眼看懂"在问什么产品/什么服务"。禁止使用"你们"/"我们"。

修复要点：
- 补充业务主语（如"小型加工厂"、"企业官网"、"代加工"、"ERP系统"等）
- 把"你们"改成行业通用描述（如"你们最小单多少"→"代加工最小起订量多少"）
- 问题控制在 10-22 字

被拒绝的问题：
{failed_text}

维度池（修复后的问题必须仍归属于这些维度中的某一个）：
{chr(10).join(valid_dimensions)}

请按标准格式输出修复后的 {len(failed_seeds)} 条：
词条序号| 内容维度| 问题内容|"""

    router = get_router()
    response = router.chat_sync(
        messages=[
            LLMMessage(role="system", content="你是一个 AI 搜索意图优化专家。修复种子问题的主语缺失和品牌词问题。只输出修复后的问题，不要解释。"),
            LLMMessage(role="user", content=fix_prompt),
        ],
        temperature=0.7,
        top_p=0.8,
        max_tokens=2048,
    )

    fixed = parse_seed_output(response.content)
    logger.info("修复生成: 返回 %d 条", len(fixed))
    return fixed


def generate_seeds(
    biz_params: BizParams,
    industry: str | None = None,
    max_retries: int = 2,
) -> list[dict]:
    """
    生成种子问题（含后校验 + 失败补生成）。

    Args:
        biz_params: 知识库业务参数
        industry: 行业分类（不传则用 biz_params.primary_industry_name）
        max_retries: 单批失败种子最多重试次数

    Returns:
        [{seq, dimension, question}, ...]
    """
    if industry is None:
        industry = biz_params.primary_industry_name

    # 获取行业对应的 System Prompt 并渲染
    system_prompt = get_industry_prompt(industry)
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

    # ── 后校验 + 补生成 ──
    valid_seeds, failed_seeds = [], []
    for s in seeds:
        ok, reason = _validate_seed(s["question"])
        s["_fail_reason"] = reason
        if ok:
            valid_seeds.append(s)
        else:
            failed_seeds.append(s)

    if failed_seeds:
        logger.warning(
            "校验不通过: %d/%d 条, 失败详情: %s",
            len(failed_seeds), len(seeds),
            [(s["question"][:30], s["_fail_reason"]) for s in failed_seeds],
        )

        # 收集有效维度名作为 fix prompt 的维度池
        all_dims = list(dict.fromkeys(s["dimension"] for s in seeds if s["dimension"]))

        retry = 0
        prev_failed_questions: set[str] = set()
        while failed_seeds and retry < max_retries:
            # 如果本轮失败的问题和上轮完全一样 → LLM 无法修复，提前终止
            current_failed = {s["question"] for s in failed_seeds}
            if current_failed == prev_failed_questions:
                logger.warning("连续两轮修复无变化，终止补生成")
                break
            prev_failed_questions = current_failed

            retry += 1
            logger.info("补生成第 %d/%d 轮, 待修复 %d 条", retry, max_retries, len(failed_seeds))
            fixed = _fix_seeds(failed_seeds, biz_params, industry, all_dims)

            # 再次校验修复结果
            still_failed = []
            for s in fixed:
                ok, reason = _validate_seed(s["question"])
                s["_fail_reason"] = reason
                if ok:
                    valid_seeds.append(s)
                else:
                    still_failed.append(s)

            if still_failed:
                logger.warning("修复后仍有 %d 条不合格", len(still_failed))
            failed_seeds = still_failed

        # 最终仍不合格的保留（宁可有瑕疵也不丢种子），记录日志
        if failed_seeds:
            logger.warning(
                "保留 %d 条未能完全修复的种子: %s",
                len(failed_seeds),
                [(s["question"][:40], s["_fail_reason"]) for s in failed_seeds],
            )
            valid_seeds.extend(failed_seeds)

    # 清理内部字段，重新编号
    result = []
    for i, s in enumerate(valid_seeds, 1):
        s.pop("_fail_reason", None)
        s["seq"] = i
        result.append(s)

    logger.info("校验后输出: %d 条合格种子 (原始 %d 条)", len(result), len(seeds))
    return result

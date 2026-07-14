"""CLI 入口 — GEO 企业推广文生成系统

知识库传入方式（三选一）：
  1. --kb <文件路径>     从 JSON 文件加载
  2. --kb-stdin           从标准输入管道读取  (echo '{...}' | python main.py seed --kb-stdin)
  3. --kb-json '<JSON>'   直接传入 JSON 字符串
"""

import json
import sys
from pathlib import Path
from typing import Optional
import typer

from config.settings import DEFAULT_ENTRY_COUNT, OUTPUT_DIR
from knowledge.loader import load_knowledge_base, create_knowledge_base
from core.seed_generator import generate_seeds
from core.field_matcher import match_field
from core.article_generators import generate_article
from core.pipeline import GEOPipeline
from utils.logger import get_logger
from output.writer import save_seeds, save_match_results, save_articles

logger = get_logger("geo")
app = typer.Typer(help="GEO — 生成式引擎优化企业推广文生成系统")


def _load_kb(
    kb: Optional[Path] = None,
    kb_stdin: bool = False,
    kb_json: Optional[str] = None,
):
    """
    统一的知识库加载入口。三种方式互斥，按优先级：
    kb_json > kb_stdin > kb_file
    """
    if kb_json is not None:
        logger.info("从 JSON 字符串加载知识库")
        return load_knowledge_base(json_str=kb_json)

    if kb_stdin:
        logger.info("从标准输入加载知识库...")
        return load_knowledge_base(stdin=True)

    if kb is not None:
        logger.info("从文件加载知识库: %s", kb)
        return load_knowledge_base(source=kb)

    # 无任何输入
    typer.echo("错误: 必须指定知识库来源:", err=True)
    typer.echo("  --kb <文件路径>     从 JSON 文件加载", err=True)
    typer.echo("  --kb-stdin           从标准输入读取", err=True)
    typer.echo("  --kb-json '<JSON>'   直接传入 JSON 字符串", err=True)
    raise typer.Exit(1)


@app.command(name="seed")
def seed_command(
    kb: Optional[Path] = typer.Option(None, "--kb", help="知识库 JSON 文件路径"),
    kb_stdin: bool = typer.Option(False, "--kb-stdin", help="从标准输入读取知识库"),
    kb_json: Optional[str] = typer.Option(None, "--kb-json", help="直接传入知识库 JSON 字符串"),
    industry: str = typer.Option("企业服务", "--industry", "-i", help="行业分类"),
    count: Optional[int] = typer.Option(None, "--count", "-c", help="种子问题生成条数（默认使用知识库中的 entryCount）"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出目录"),
):
    """[阶段1] 从知识库生成种子问题"""
    knowledge = _load_kb(kb=kb, kb_stdin=kb_stdin, kb_json=kb_json)
    biz = knowledge.biz_params
    # --count 未指定时，使用知识库中的 entryCount
    if count is not None:
        biz.entryCount = count
    actual_count = biz.entryCount

    logger.info("行业: %s, 条数: %d → 调用 LLM...", industry, actual_count)
    seeds = generate_seeds(biz, industry)

    out_dir = _resolve_output_dir(output, knowledge)
    save_seeds(seeds, out_dir)

    typer.echo(f"\n{'='*60}")
    typer.echo(f"已生成 {len(seeds)} 条种子问题 → {out_dir}")
    typer.echo(f"{'='*60}")
    for s in seeds[:8]:
        typer.echo(f"  {s['seq']:2d}. [{s['dimension']}] {s['question']}")
    if len(seeds) > 8:
        typer.echo(f"  ... 还有 {len(seeds) - 8} 条")


@app.command(name="match")
def match_command(
    kb: Optional[Path] = typer.Option(None, "--kb", help="知识库 JSON 文件路径"),
    kb_stdin: bool = typer.Option(False, "--kb-stdin", help="从标准输入读取知识库"),
    kb_json: Optional[str] = typer.Option(None, "--kb-json", help="直接传入知识库 JSON 字符串"),
    seeds_json: Path = typer.Option(..., "--seeds", help="种子问题 JSON 文件路径"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出目录"),
):
    """[阶段2] 对已有种子问题进行字段匹配与评估"""
    knowledge = _load_kb(kb=kb, kb_stdin=kb_stdin, kb_json=kb_json)

    with open(seeds_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    seeds = data.get("seeds", data) if isinstance(data, dict) else data

    results = []
    for seed in seeds:
        result = match_field(
            entry_text=seed.get("question", ""),
            dimension=seed.get("dimension", ""),
            biz_params=knowledge.biz_params,
        )
        results.append(result)
        typer.echo(f"  [{result.match_degree}] {seed['question'][:40]}")

    out_dir = _resolve_output_dir(output, knowledge)
    save_match_results(results, out_dir)

    sufficient = sum(1 for r in results if r.is_sufficient)
    typer.echo(f"\n匹配完成: {sufficient}/{len(results)} 条资料充足 → {out_dir}")


@app.command(name="write")
def write_command(
    kb: Optional[Path] = typer.Option(None, "--kb", help="知识库 JSON 文件路径"),
    kb_stdin: bool = typer.Option(False, "--kb-stdin", help="从标准输入读取知识库"),
    kb_json: Optional[str] = typer.Option(None, "--kb-json", help="直接传入知识库 JSON 字符串"),
    seeds_json: Path = typer.Option(..., "--seeds", help="种子问题 JSON 文件路径"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出目录"),
    w1: int = typer.Option(40, "--w1", help="一阶段权重"),
    w2: int = typer.Option(35, "--w2", help="二阶段权重"),
    w3: int = typer.Option(25, "--w3", help="平稳期权重"),
):
    """[阶段3/4/5] 按权重路由生成推广文章"""
    knowledge = _load_kb(kb=kb, kb_stdin=kb_stdin, kb_json=kb_json)

    with open(seeds_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    seeds = data.get("seeds", data) if isinstance(data, dict) else data

    weights = {"phase1": w1, "phase2": w2, "stable": w3}

    articles = []
    for i, seed in enumerate(seeds):
        typer.echo(f"  [{i+1}/{len(seeds)}] {seed['question'][:40]}")
        article = generate_article(
            seed_question=seed.get("question", ""),
            dimension=seed.get("dimension", ""),
            biz_params=knowledge.biz_params,
            weights=weights,
        )
        articles.append(article)
        typer.echo(f"    → {article.stage}: {article.title[:50]}")

    out_dir = _resolve_output_dir(output, knowledge)
    saved = save_articles(articles, out_dir)

    total = sum(len(files) for files in saved.values())
    typer.echo(f"\n文章生成完成: {total} 篇 → {out_dir}")
    for stage, files in saved.items():
        typer.echo(f"  {stage}: {len(files)} 篇")


@app.command(name="run")
def run_command(
    kb: Optional[Path] = typer.Option(None, "--kb", help="知识库 JSON 文件路径"),
    kb_stdin: bool = typer.Option(False, "--kb-stdin", help="从标准输入读取知识库"),
    kb_json: Optional[str] = typer.Option(None, "--kb-json", help="直接传入知识库 JSON 字符串"),
    industry: str = typer.Option("企业服务", "--industry", "-i", help="行业分类（仅步骤1使用）"),
    count: Optional[int] = typer.Option(None, "--count", "-c", help="种子问题生成条数（默认使用知识库中的 entryCount）"),
    w1: int = typer.Option(40, "--w1", help="一阶段权重"),
    w2: int = typer.Option(35, "--w2", help="二阶段权重"),
    w3: int = typer.Option(25, "--w3", help="平稳期权重"),
    enable_image: bool = typer.Option(False, "--image", help="生成配图提示词"),
    skip_precheck: bool = typer.Option(False, "--skip-precheck", help="跳过知识库预检"),
    interactive: bool = typer.Option(False, "--interactive", "-I", help="每个步骤完成后询问是否继续"),
    resume: bool = typer.Option(False, "--resume", help="从上次中断点恢复执行"),
    dry_run: bool = typer.Option(False, "--dry-run", help="预演模式：仅展示执行计划，不调用 LLM"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出目录"),
):
    """根据知识库中的 entryText 自动路由：
    - 有 entryText → 跳过步骤1，直接字段匹配+生文
    - 无 entryText → 仅执行步骤1（种子问题生成），输出后停止
    """
    knowledge = _load_kb(kb=kb, kb_stdin=kb_stdin, kb_json=kb_json)
    biz = knowledge.biz_params

    if biz.has_entry_text:
        # 模式 A: 传入了种子问题 → 步骤2+3
        typer.echo(f"路由: entryText 已存在 → 跳过步骤1，执行 字段匹配 → 文章生成")
        typer.echo(f"种子问题: {biz.entryText}")
        actual_count = 1
        pipeline_stages = ["match", "articles"]
        seed_text = biz.entryText
    else:
        # 模式 B: 纯知识库 → 仅步骤1
        typer.echo(f"路由: 无 entryText → 仅执行步骤1（种子问题生成）")
        actual_count = count if count is not None else biz.entryCount
        pipeline_stages = ["seed"]
        seed_text = None

    pipeline = GEOPipeline(
        knowledge_base=knowledge,
        industry=industry,
        entry_count=actual_count,
        stages=pipeline_stages,
        weights={"phase1": w1, "phase2": w2, "stable": w3},
        enable_image=enable_image,
        interactive=interactive,
        seed_text=seed_text,
        skip_precheck=skip_precheck,
        resume=resume,
    )

    if dry_run:
        _print_dry_run(knowledge, industry, actual_count, pipeline_stages,
                       enable_image, {"phase1": w1, "phase2": w2, "stable": w3})
        return

    report = pipeline.run()

    typer.echo(f"\n{'='*60}")
    typer.echo(f"GEO 全流程完成!")
    typer.echo(f"  企业: {report.company_name}")
    typer.echo(f"  种子问题: {report.total_seeds} 条")
    typer.echo(f"  匹配: {report.matched_count} 条 (充足: {report.sufficient_count})")
    typer.echo(f"  文章: {sum(report.articles.values())} 篇 {report.articles}")
    typer.echo(f"  输出: {pipeline.out_dir}")


def _print_dry_run(kb, industry, count, stages, enable_image, weights):
    """预演模式：展示执行计划和预估 token 消耗"""
    biz = kb.biz_params
    has_seed = "seed" in stages
    has_match = "match" in stages
    has_articles = "articles" in stages

    sections_count = sum(len(s.fields) for s in biz.sections)
    # 粗略估算
    seed_tokens = 8000 if has_seed else 0  # system prompt + user prompt
    match_tokens = 4200 * (1 if has_match else 0)  # per match call
    article_tokens = 8000 if has_articles else 0  # system + user + output
    image_tokens = 1500 if enable_image else 0  # 2 image prompts
    total_estimate = seed_tokens + match_tokens + article_tokens + image_tokens

    typer.echo(f"\n{'='*60}")
    typer.echo(f"  GEO 执行计划 (dry-run)")
    typer.echo(f"{'='*60}")
    typer.echo(f"  企业: {biz.company_name}")
    typer.echo(f"  产品: {biz.coreProductName}")
    typer.echo(f"  行业: {industry}")
    typer.echo(f"  知识库: {len(biz.sections)} sections, {sections_count} fields")
    typer.echo(f"")
    typer.echo(f"  执行步骤:")
    if has_seed:
        typer.echo(f"    1. 种子问题生成     → 生成 {count} 条, 预估 ~{seed_tokens} tokens")
    if has_match:
        typer.echo(f"    {2 if has_seed else 1}. 字段匹配与评估   → 1 条种子匹配, 预估 ~{match_tokens} tokens")
    if has_articles:
        n = 3 if has_seed else (2 if has_match else 1)
        typer.echo(f"    {n}. 文章生成          → {weights}, 预估 ~{article_tokens} tokens")
    if enable_image:
        n = 4 if has_seed else (3 if has_match else 2)
        typer.echo(f"    {n}. 配图提示词        → 标题图+2插图, 预估 ~{image_tokens} tokens")
    typer.echo(f"")
    typer.echo(f"  预估总 tokens: ~{total_estimate}")
    typer.echo(f"{'='*60}")


def _resolve_output_dir(output: Optional[Path], kb) -> Path:
    if output:
        path = Path(output)
    else:
        company_name = kb.biz_params.company_name or "unknown"
        safe_name = company_name.replace("（", "").replace("）", "").replace(" ", "_")
        path = OUTPUT_DIR / safe_name
    path.mkdir(parents=True, exist_ok=True)
    return path


if __name__ == "__main__":
    app()

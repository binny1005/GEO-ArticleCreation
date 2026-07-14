"""输出文件写入器"""

import json
from pathlib import Path
from dataclasses import dataclass, field

from core.field_matcher import FieldMatchResult
from core.article_generators import Article
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OutputReport:
    """生成报告"""
    company_name: str = ""
    industry: str = ""
    total_seeds: int = 0
    matched_count: int = 0
    sufficient_count: int = 0
    articles: dict[str, int] = field(default_factory=dict)


def save_seeds(seeds: list[dict], out_dir: Path) -> tuple[Path, Path]:
    """保存种子问题（含维度分组统计）"""
    seeds_txt = out_dir / "seeds.txt"
    seeds_json = out_dir / "seeds.json"

    with open(seeds_txt, "w", encoding="utf-8") as f:
        for s in seeds:
            f.write(f"{s['seq']}|{s['dimension']}|{s['question']}|\n")

    groups: dict[str, list[dict]] = {}
    for s in seeds:
        dim = s.get("dimension", "其他")
        groups.setdefault(dim, []).append(s)

    summary = {
        "total": len(seeds),
        "dimensions": {
            dim: {
                "count": len(items),
                "seeds": [{"seq": s["seq"], "question": s["question"]} for s in items],
            }
            for dim, items in groups.items()
        },
        "seeds": seeds,
    }

    with open(seeds_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("种子问题: %s (%d 条, %d 个维度)", seeds_txt, len(seeds), len(groups))
    return seeds_txt, seeds_json


def save_match_results(results: list[FieldMatchResult], out_dir: Path) -> Path:
    """保存字段匹配结果"""
    path = out_dir / "match_results.json"
    data = [
        {
            "entry_text": r.entry_text,
            "dimension": r.dimension,
            "field_refs": r.field_refs,
            "match_degree": r.match_degree,
            "is_sufficient": r.is_sufficient,
            "can_expand": r.can_expand,
            "reason": r.reason,
        }
        for r in results
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("匹配结果: %s (%d 条)", path, len(results))
    return path


def save_articles(articles: list[Article], out_dir: Path) -> dict[str, list[Path]]:
    """保存文章，按阶段分组"""
    articles_dir = out_dir / "articles"
    articles_dir.mkdir(exist_ok=True)

    saved = {"phase1": [], "phase2": [], "stable": []}
    stage_dir_names = {"phase1": "phase1_养号", "phase2": "phase2_养号", "stable": "stable_平稳"}

    for i, article in enumerate(articles):
        stage_dir = articles_dir / stage_dir_names.get(article.stage, article.stage)
        stage_dir.mkdir(exist_ok=True)

        safe_title = article.title[:20].replace("/", "_").replace("\\", "_").strip()
        filename = f"{i+1:03d}_{safe_title or 'untitled'}.md"
        filepath = stage_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {article.title}\n\n")
            f.write(article.paper)

        saved[article.stage].append(filepath)

    for stage, files in saved.items():
        if files:
            logger.info("%s: %d 篇", stage, len(files))

    return saved


def save_report(report: OutputReport, out_dir: Path) -> Path:
    """保存生成报告"""
    path = out_dir / "report.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.__dict__, f, ensure_ascii=False, indent=2)
    logger.info("报告: %s", path)
    return path

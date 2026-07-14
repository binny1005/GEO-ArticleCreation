"""GEO 主流程编排器 — 串联全部 5 个阶段"""

import random
import time
from pathlib import Path
from typing import Optional

from config.settings import (
    DEFAULT_ENTRY_COUNT,
    DEFAULT_ARTICLE_MIN_LENGTH,
    DEFAULT_ARTICLE_MAX_LENGTH,
    DEFAULT_TITLE_LENGTH,
    OUTPUT_DIR,
)
import json

from knowledge.schema import KnowledgeBase
from knowledge.loader import (
    extract_sections_for_prompt,
    extract_base_fields,
    resolve_referenced_fields,
)
from core.seed_generator import generate_seeds
from core.field_matcher import match_field
from core.article_generators import generate_article
from core.image_gen import (
    generate_title_image, generate_insert_images,
    TitleImage, InsertImage,
)
from prompts.image_styles import get_style
from llm.router import get_router, LLMMessage
from prompts.kb_analysis import (
    KB_PRECHECK_SYSTEM, KB_PRECHECK_USER,
    REJECTION_ANALYSIS_SYSTEM, REJECTION_ANALYSIS_USER,
)
from prompts.industry_registry import get_industry_prompt
from output.writer import (
    save_seeds, save_match_results, save_articles, save_report,
    OutputReport,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def _extract_dimension_names(industry_prompt: str) -> list[str]:
    """从行业 Prompt 中提取维度名称列表"""
    import re
    dims = []
    patterns = [
        r'维度\s*\d+\s*[：:]\s*([^\n]+)',
    ]
    for line in industry_prompt.split('\n'):
        line = line.strip()
        for pat in patterns:
            m = re.search(pat, line)
            if m:
                name = m.group(1).strip()
                if name and len(name) < 20 and name not in dims:
                    dims.append(name)
    return dims[:8]


class GEOPipeline:
    """GEO 全流程编排器"""

    def __init__(
        self,
        knowledge_base: KnowledgeBase = None,
        industry: str = "企业服务",
        entry_count: int = DEFAULT_ENTRY_COUNT,
        stages: list[str] | None = None,
        weights: dict | None = None,
        enable_image: bool = False,
        interactive: bool = False,
        seed_text: str = None,
        skip_precheck: bool = False,
        resume: bool = False,
        length_min: int = DEFAULT_ARTICLE_MIN_LENGTH,
        length_max: int = DEFAULT_ARTICLE_MAX_LENGTH,
        title_length: int = DEFAULT_TITLE_LENGTH,
    ):
        self.industry = industry
        self.entry_count = entry_count
        self.stages = stages or ["seed", "match", "articles"]
        self.weights = weights
        self.enable_image = enable_image
        self.interactive = interactive
        self.seed_text = seed_text
        self.skip_precheck = skip_precheck
        self.resume = resume
        self._completed_steps: list[str] = []
        # 知识库由外部传入，参数优先使用 KB 中的值
        self.kb: KnowledgeBase = knowledge_base
        self.biz_params = self.kb.biz_params
        self.biz_params.entryCount = entry_count

        # 字数/标题参数：优先 KB 传入值，否则用默认
        self.length_min = self.biz_params.lengthmin or length_min
        self.length_max = self.biz_params.lengthmax or length_max
        self.title_length = self.biz_params.titlelength or title_length

        # 输出目录
        company_name = self.biz_params.company_name or "unknown"
        self.safe_name = company_name.replace("（", "").replace("）", "").replace(" ", "_")
        self.out_dir = OUTPUT_DIR / self.safe_name

        # 结果容器
        self.seeds: list[dict] = []
        self.match_results: list = []
        self.rejected_trials: list[dict] = []  # 步骤2被拒绝的种子问题及原因
        self.articles: list = []
        self.title_images: list[TitleImage] = []
        self.insert_images: list[list[InsertImage]] = []

    def _ask(self, prompt: str) -> bool:
        """交互式询问用户是否继续"""
        print(f"\n{prompt}")
        answer = input("  [Y] 继续  [N] 结束流程  > ").strip().lower()
        return answer in ("", "y", "yes")

    def _print_divider(self, title: str = ""):
        print(f"\n{'='*60}")
        if title:
            print(f"  {title}")
            print(f"{'='*60}")

    def _print_seeds(self):
        """打印种子问题摘要"""
        for s in self.seeds:
            print(f"  {s['seq']:2d}. [{s['dimension']}] {s['question']}")

    def _print_match_summary(self):
        """打印字段匹配摘要"""
        sufficient = sum(1 for r in self.match_results if r.is_sufficient)
        print(f"  匹配结果: {sufficient}/{len(self.match_results)} 条资料充足")
        print()
        for r in self.match_results:
            icon = "[充足]" if r.is_sufficient else "[不足]"
            print(f"  {icon} [{r.match_degree}] {r.entry_text[:50]}")
            if r.field_refs:
                print(f"         匹配字段: {', '.join(r.field_refs[:5])}")

    def _print_article(self, article):
        """打印单篇文章预览"""
        print(f"  [{article.stage}] {article.title}")
        body_preview = article.paper[:200].replace("\n", " ").replace("#", "").strip()
        print(f"         正文预览: {body_preview}...")

    def _precheck_kb(self) -> dict | None:
        """
        #5 知识库预检 — 扫描信息密度，薄弱则返回结果并终止。
        返回 None 表示通过；返回 dict 表示被拒，含薄弱维度信息。
        """
        router = get_router()
        sections_text = extract_sections_for_prompt(self.biz_params)

        # 从行业 Prompt 中提取维度名称
        industry_prompt = get_industry_prompt(self.industry)
        dim_names = _extract_dimension_names(industry_prompt)
        dim_list = "\n".join(f"{i+1}. **{d}**" for i, d in enumerate(dim_names))
        dim_json = ",\n".join(f'    "{d}": "充足 / 薄弱 / 缺失"' for d in dim_names)

        system_prompt = KB_PRECHECK_SYSTEM.replace("{{ dimensions }}", dim_list).replace("{{ dim_json }}", dim_json)

        response = router.chat_sync(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=KB_PRECHECK_USER.replace(
                    "{{ company_name }}", self.biz_params.company_name
                ).replace(
                    "{{ core_product }}", self.biz_params.coreProductName
                ).replace(
                    "{{ sections_text }}", sections_text
                )),
            ],
            temperature=0.3,
            top_p=0.8,
            max_tokens=1024,
        )

        # 解析 JSON
        import re as _re
        match = _re.search(r'\{[\s\S]*\}', response.content)
        if not match:
            return None
        try:
            result = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        # 保存预检结果
        precheck_file = self.out_dir / "kb_precheck.json"
        with open(precheck_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        overall = result.get("overall_density", "中")
        weak = result.get("weak_dimensions", [])

        self._print_divider("知识库预检")
        print(f"  信息密度: {overall}")
        print(f"  薄弱维度: {', '.join(weak) if weak else '无'}")
        print(f"  预检报告: {precheck_file}")

        if overall == "低" or len(weak) >= 3:
            print(f"\n  ⚠ 知识库信息密度不足，终止流程")
            print(f"  建议补全以下维度后再运行: {', '.join(weak) if weak else '各维度'}")
            return result

        return None  # 通过

    def _analyze_rejections(self):
        """#3 被拒模式分析 — 分析 rejected_trials，输出知识库补全建议"""
        if not self.rejected_trials:
            return

        router = get_router()

        # 构建拒绝记录文本
        records = []
        for i, rt in enumerate(self.rejected_trials):
            records.append(
                f"[{i+1}] 种子: {rt['question']}\n"
                f"    维度: {rt['dimension']}\n"
                f"    匹配度: {rt['match_degree']}\n"
                f"    拒绝原因: {rt['reason'][:200]}\n"
            )
        rejection_text = "\n".join(records)

        response = router.chat_sync(
            messages=[
                LLMMessage(role="system", content=REJECTION_ANALYSIS_SYSTEM),
                LLMMessage(role="user", content=REJECTION_ANALYSIS_USER.replace(
                    "{{ rejection_records }}", rejection_text
                )),
            ],
            temperature=0.5,
            top_p=0.8,
            max_tokens=1024,
        )

        # 解析 JSON
        import re as _re
        match = _re.search(r'\{[\s\S]*\}', response.content)
        data = {}
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # 合并 LLM 分析的补全建议
        gaps = {
            "rejected_count": len(self.rejected_trials),
            "rejected_details": self.rejected_trials,
            "llm_analysis": data,
        }
        gaps_file = self.out_dir / "knowledge_gaps.json"
        with open(gaps_file, "w", encoding="utf-8") as f:
            json.dump(gaps, f, ensure_ascii=False, indent=2)

        self._print_divider("知识库补全建议")
        summary = data.get("rejection_summary", "")
        if summary:
            print(f"  被拒分析: {summary}")
        dims = data.get("dimension_analysis", {})
        if dims:
            print(f"  问题维度:")
            for dim, info in dims.items():
                print(f"    [{dim}] 被拒{info.get('reject_count', '?')}次: {info.get('root_cause', '')[:80]}")
        missing = data.get("missing_fields", [])
        if missing:
            print(f"  建议补全字段: {', '.join(missing[:6])}")
        print(f"  详情: {gaps_file}")

    def _state_path(self) -> Path:
        return self.out_dir / "pipeline_state.json"

    def _save_state(self, step_name: str):
        self._completed_steps.append(step_name)
        state = {
            "company_name": self.biz_params.company_name,
            "industry": self.industry,
            "completed_steps": self._completed_steps,
            "seeds_count": len(self.seeds),
            "match_count": len(self.match_results),
            "articles_count": len(self.articles),
        }
        with open(self._state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _load_state(self) -> dict | None:
        path = self._state_path()
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _is_step_done(self, step_name: str) -> bool:
        return step_name in self._completed_steps

    def run(self) -> OutputReport:
        """执行流程（支持交互模式）"""
        start_time = time.time()
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # ── 断点恢复 ──
        if self.resume:
            saved = self._load_state()
            if saved:
                self._completed_steps = saved.get("completed_steps", [])
                print(f"  断点恢复: 已完成 {self._completed_steps}")

        stage_list = [s.strip() for s in self.stages] if isinstance(self.stages, str) else self.stages
        has_seed_step = "seed" in stage_list
        total_steps = len(stage_list) + (1 if self.enable_image else 0)
        current_step = 1

        # ── #5 知识库预检（步骤1之前）──
        if (has_seed_step and self.seed_text is None and not self.skip_precheck
                and not self._is_step_done("precheck")):
            precheck_result = self._precheck_kb()
            if precheck_result is not None:
                return self._finish(start_time)
            self._save_state("precheck")

        # ── [1] 种子问题生成（仅当未传入 seed_text 时执行）──
        if has_seed_step and self.seed_text is None and not self._is_step_done("seed"):
            self._print_divider(f"[{current_step}/{total_steps}] 种子问题生成")
            print(f"  行业: {self.industry}")
            print(f"  企业: {self.biz_params.company_name}")
            print(f"  产品: {self.biz_params.coreProductName}")
            print(f"  目标: {self.entry_count} 条")
            print(f"  正在调用 LLM...")

            self.seeds = generate_seeds(self.biz_params, self.industry)
            seeds_file, seeds_json = save_seeds(self.seeds, self.out_dir)

            print(f"\n  >> 生成完成: {len(self.seeds)} 条种子问题 <<")
            print(f"  >> 输出文件: {seeds_file}")
            print(f"  >> 结构化数据: {seeds_json}")
            self._print_seeds()
            self._save_state("seed")

            current_step += 1
            if self.interactive:
                if not self._ask("是否继续下一步 [随机选取1条 → 字段匹配]？"):
                    return self._finish(start_time)

        # 如果传入了 seed_text，跳过步骤1，直接使用
        if self.seed_text is not None:
            self.seeds = [{"seq": 1, "dimension": "外部输入", "question": self.seed_text}]
            print(f"  >> 跳过步骤1（使用外部传入的种子问题） <<")
            print(f"  种子问题: {self.seed_text}")

        # ── [2] 字段匹配与评估（随机选取，确保强相关+充足）──
        if "match" in stage_list and self.seeds and not self._is_step_done("match"):
            self._print_divider(f"[{current_step}/{total_steps}] 字段匹配与评估")

            # 可用种子池（排除已试过但不合格的）
            available_pool = list(self.seeds)
            tried_count = 0
            max_retries = min(len(self.seeds), 5)  # 最多重试 5 次
            result = None
            picked = None

            while available_pool and tried_count < max_retries:
                picked = random.choice(available_pool)
                print(f"  种子池: {len(available_pool)} 条 → 随机选取: [{picked['dimension']}] {picked['question']}")
                print(f"  正在匹配...")

                result = match_field(
                    entry_text=picked.get("question", ""),
                    dimension=picked.get("dimension", ""),
                    biz_params=self.biz_params,
                )

                is_quality = (result.match_degree == "强相关" and result.is_sufficient)
                icon = "[通过]" if is_quality else "[重试]"
                print(f"  {icon} [{result.match_degree}] 充足={result.is_sufficient}")

                if is_quality:
                    break

                # 不合格：记录原因，移出池子
                self.rejected_trials.append({
                    "question": picked.get("question", ""),
                    "dimension": picked.get("dimension", ""),
                    "match_degree": result.match_degree,
                    "is_sufficient": result.is_sufficient,
                    "can_expand": result.can_expand,
                    "reason": result.reason,
                })
                available_pool.remove(picked)
                tried_count += 1
                if available_pool:
                    print(f"    拒绝原因: [{result.match_degree}] is_sufficient={result.is_sufficient}")
                    print(f"    重新选取... (已尝试 {tried_count}/{max_retries})")

            # 最终结果：无合格种子则终止流程
            if result is None:
                print("\n  >> 错误: 种子池全部耗尽，无可用种子")
                return self._finish(start_time)

            # 如果最终选中的种子不合格（重试耗尽），不进入步骤3
            is_quality = (result.match_degree == "强相关" and result.is_sufficient)
            if not is_quality:
                # 保存被拒记录 + 输出拒因
                rejected_file = self.out_dir / "rejected_trials.json"
                with open(rejected_file, "w", encoding="utf-8") as f:
                    json.dump(self.rejected_trials, f, ensure_ascii=False, indent=2)
                print(f"\n  >> 被拒绝的种子问题: {len(self.rejected_trials)} 条 → {rejected_file}")
                for rt in self.rejected_trials:
                    print(f"     [{rt['match_degree']}] {rt['question'][:50]}")
                print(f"\n  ⚠ 所有尝试的种子问题均未达到「强相关+充足」标准")
                print(f"  流程终止于步骤2，不生成文章。请补充知识库后重试。")
                return self._finish(start_time)

            # 通过质量检查：保存被拒记录（如有）
            if self.rejected_trials:
                rejected_file = self.out_dir / "rejected_trials.json"
                with open(rejected_file, "w", encoding="utf-8") as f:
                    json.dump(self.rejected_trials, f, ensure_ascii=False, indent=2)
                print(f"\n  >> 被拒绝的种子问题: {len(self.rejected_trials)} 条 → {rejected_file}")
                for rt in self.rejected_trials:
                    print(f"     [{rt['match_degree']}] {rt['question'][:50]}")

            self.match_results.append(result)
            save_match_results(self.match_results, self.out_dir)

            if result.field_refs:
                print(f"  匹配字段: {', '.join(result.field_refs[:5])}")
            if result.reason:
                print(f"  评估理由: {result.reason[:120]}")
            self._save_state("match")

            current_step += 1
            if self.interactive:
                if not self._ask("是否继续下一步 [文章生成]？"):
                    return self._finish(start_time)

        # ── [3][4][5] 文章生成 (权重路由，单条) ──
        if "articles" in stage_list and self.match_results and not self._is_step_done("articles"):
            self._print_divider(f"[{current_step}/{total_steps}] 文章生成 (权重路由)")

            mr = self.match_results[0]
            seed_question = mr.entry_text
            seed_dimension = mr.dimension

            print(f"  种子: {seed_question[:50]}")
            print(f"  匹配度: {mr.match_degree} | 充足: {mr.is_sufficient}")
            print(f"  字数: {self.length_min}-{self.length_max} | 标题≤{self.title_length}字")
            print(f"  权重: phase1={self.weights.get('phase1',40)}%  "
                  f"phase2={self.weights.get('phase2',35)}%  "
                  f"stable={self.weights.get('stable',25)}%")

            # 步骤3 字段精简：baseFields + referencedFields + 匹配上下文
            base_fields = extract_base_fields(self.biz_params)
            ref_fields = resolve_referenced_fields(self.biz_params, mr.field_refs)
            match_context = f"匹配度: {mr.match_degree}\n匹配字段: {', '.join(mr.field_refs)}\n评估: {mr.reason[:200]}"
            print(f"  baseFields: 企业基础信息")
            print(f"  referencedFields: {len(mr.field_refs)} 个字段")
            print(f"  matchContext: {mr.match_degree}")

            article = generate_article(
                seed_question=seed_question,
                dimension=seed_dimension,
                biz_params=self.biz_params,
                base_fields=base_fields,
                referenced_fields=ref_fields,
                match_context=match_context,
                weights=self.weights,
                length_min=self.length_min,
                length_max=self.length_max,
                title_length=self.title_length,
            )
            self.articles.append(article)
            self._print_article(article)
            save_articles(self.articles, self.out_dir)
            self._save_state("articles")

            current_step += 1

        # ── [4] 配图提示词 (行业风格驱动，--image 启用) ──
        if self.enable_image and self.articles and not self._is_step_done("images"):
            self._print_divider(f"[{current_step}/{total_steps}] 配图提示词")

            style = get_style(self.industry)
            print(f"  行业风格: {style.get('style', '')}")
            img_dir = self.out_dir / "image_prompts"
            img_dir.mkdir(exist_ok=True)

            for i, article in enumerate(self.articles):
                print(f"\n  [{i+1}/{len(self.articles)}] {article.title[:40]}")

                # 标题图
                title_img = generate_title_image(
                    title=article.title, paper=article.paper,
                    question=article.seed_question,
                    product=self.biz_params.coreProductName,
                    industry=self.industry,
                )
                self.title_images.append(title_img)

                # 插图（场景图 + 流程图）
                inserts = generate_insert_images(
                    paper=article.paper, title=article.title,
                    industry=self.industry,
                )
                self.insert_images.append(inserts)

                # 保存到独立文件
                filepath = img_dir / f"{i+1:03d}_prompts.txt"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"标题图\n")
                    f.write(f"  画面: {title_img.description}\n")
                    f.write(f"  Prompt: {title_img.prompt}\n")
                    f.write(f"  Negative: {title_img.negative}\n")
                    for j, ins in enumerate(inserts):
                        f.write(f"\n插图{j+1} [{ins.type}]\n")
                        f.write(f"  画面: {ins.description}\n")
                        f.write(f"  Prompt: {ins.prompt}\n")

                print(f"    标题图: {title_img.description[:50]}")
                for ins in inserts:
                    print(f"    [{ins.type}] {ins.description[:50]}")
                print(f"    → {filepath}")
            self._save_state("images")

            current_step += 1

        return self._finish(start_time)

    def _finish(self, start_time: float) -> OutputReport:
        """生成报告并返回"""
        # ── #3 被拒模式分析 ──
        if self.rejected_trials:
            self._analyze_rejections()

        elapsed = time.time() - start_time
        article_counts = {}
        for a in self.articles:
            article_counts[a.stage] = article_counts.get(a.stage, 0) + 1

        report = OutputReport(
            company_name=self.biz_params.company_name,
            industry=self.industry,
            total_seeds=len(self.seeds),
            matched_count=len(self.match_results),
            sufficient_count=sum(1 for mr in self.match_results if mr.is_sufficient),
            articles=article_counts,
        )
        save_report(report, self.out_dir)

        self._print_divider("流程汇总")
        print(f"  企业: {self.biz_params.company_name}")
        print(f"  行业: {self.industry}")
        print(f"  耗时: {elapsed:.1f} 秒")
        print(f"  步骤1 种子问题: {len(self.seeds)} 条")
        if self.rejected_trials:
            print(f"  步骤2 被拒绝: {len(self.rejected_trials)} 条 → rejected_trials.json")
        print(f"  步骤2 通过: {len(self.match_results)} 条 (充足: {sum(1 for r in self.match_results if r.is_sufficient)})")
        print(f"  步骤3 文章: {len(self.articles)} 篇 {article_counts}")
        print(f"  输出目录: {self.out_dir}")

        return report

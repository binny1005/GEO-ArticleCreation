# GEO-ArticleCreation

面向 AI 搜索引擎（AIO/GEO）的企业推广文章自动生成系统。基于企业知识库，自动生成 AI 平台可引用的高质量推广内容。

---

## 目录

1. [快速开始](#快速开始)
2. [核心概念](#核心概念)
3. [知识库格式](#知识库格式)
4. [完整工作流](#完整工作流)
5. [CLI 命令](#cli-命令)
6. [配置说明](#配置说明)
7. [输出结构](#输出结构)
8. [行业支持](#行业支持)
9. [常见问题](#常见问题)
10. [项目结构](#项目结构)
11. [优化历程](#优化历程)

---

## 快速开始

### 环境要求

- Python 3.11+
- 至少一个 LLM API Key（DeepSeek / 千问 / OpenAI）

### 安装

```bash
git clone https://github.com/binny1005/GEO-ArticleCreation.git
cd GEO-ArticleCreation
pip install -r requirements.txt
cp .env.example .env
```

### 配置 API Key

编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-your-key-here
```

编辑 `config/llm_providers.yaml` 配置 LLM 优先级：

```yaml
providers:
  - name: deepseek-v3
    type: openai_compat
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    priority: 1        # 数字越小优先级越高，失败自动 fallback

  - name: qwen3-max
    type: openai_compat
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DASHSCOPE_API_KEY}
    model: qwen3-max
    priority: 2
```

### 首次运行

```bash
# 仅生成种子问题
python main.py run --kb data/your_kb.json --industry "工业制造"

# 查看结果
cat output/{企业名}/seeds.txt
```

---

## 核心概念

### 什么是种子问题？

种子问题是模拟真实用户在 AI 平台（豆包、Kimi、DeepSeek）上会提出的口语化搜索问题。例如：

> "2026年建个百级密闭实验室多少钱"  
> "恒温恒湿精度能稳定在多少"  
> "怎么找到源头做净化工程的公司"

**核心规则**：非品牌词、10-20字口语、痛点驱动、2026 时效。

### 流水线步骤

```
知识库 JSON → [预检] → [步骤1]种子生成 → [步骤2]字段匹配 → [步骤3]文章生成 → [步骤4]审核修改 → [步骤5]配图
```

| 步骤 | 功能 | 输出 |
|------|------|------|
| 预检 | 知识库信息密度扫描，薄弱维度≥3则阻止 | kb_precheck.json |
| 步骤1 | 20 行业独立 Prompt 生成种子问题 | seeds.txt + seeds.json |
| 步骤2 | LLM 检索匹配知识库字段 + 充足性评估 | match_results.json |
| 步骤3 | 三风格权重路由生成文章 | articles/*.md |
| 步骤4 | 去AI化检测 + GEO收录评分 + 自动修改 | reviews/*.md + diff.md |
| 步骤5 | 行业风格驱动配图提示词（--image 启用） | image_prompts/*.txt |

### 自动路由

系统根据知识库中 `entryText` 字段自动决定执行路径：

```
传入 { biz_params: { ... } }
  │
  ├─ 无 entryText → 预检 → 步骤1(种子生成) → 停止
  │
  └─ 有 entryText → 步骤2(匹配) → 步骤3(生文) → 步骤4(审核修改)
```

---

## 知识库格式

### 完整结构

```json
{
  "input": {
    "biz_params": {
      "companyName": "企业名称",
      "coreProductName": "核心产品/服务",
      "entryCount": 20,
      "entryText": "",
      "lengthmin": 800,
      "lengthmax": 2000,
      "titlelength": 30,
      "sections": [...],
      "constraintFields": [...]
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `companyName` | string | ✅ | - | 企业品牌名称（兼容旧字段名 `productBrand`） |
| `coreProductName` | string | ✅ | - | 核心产品/服务名称 |
| `entryCount` | int | 否 | 20 | 种子问题生成数量 |
| `entryText` | string | 否 | "" | 种子问题文本（不为空→跳过步骤1） |
| `lengthmin` | int | 否 | 800 | 文章最小字数 |
| `lengthmax` | int | 否 | 2000 | 文章最大字数 |
| `titlelength` | int | 否 | 30 | 标题最大字符数 |
| `sections` | array | ✅ | - | 结构化企业资料 |
| `constraintFields` | array | 否 | [] | 敏感词/禁用表达列表 |

### sections 结构

```json
{
  "sectionCode": "product_info",
  "sectionName": "产品信息",
  "fields": [
    {
      "fieldKey": "core_features",
      "fieldLabel": "核心功能或特点描述",
      "fieldSemantics": "核心功能、产品特点与主要卖点",
      "fieldValue": "1、具体描述内容..."
    }
  ]
}
```

### 建议的 sectionCode

| sectionCode | 用途 | 在流程中的角色 |
|-------------|------|---------------|
| `product_info` | 产品/服务核心信息 | 步骤3 的 referencedFields（主要素材） |
| `company_profile` | 企业基本信息 | 步骤3 的 baseFields（仅取企业名+定位） |
| `development_history` | 发展历程 | 补充素材 |
| `qualification_honor` | 资质荣誉 | 权威背书 |
| `team_profile` | 团队介绍 | 专业度佐证 |
| `market_customer` | 市场客户 | 案例素材 |

### 最小可运行示例

```json
{
  "input": {
    "biz_params": {
      "companyName": "某科技有限公司",
      "coreProductName": "智能仓储系统",
      "sections": [
        {
          "sectionCode": "product_info",
          "sectionName": "产品信息",
          "fields": [
            {"fieldKey": "core_features", "fieldLabel": "核心功能", "fieldSemantics": "", "fieldValue": "全自动分拣、实时库存追踪"},
            {"fieldKey": "product_price_range", "fieldLabel": "价格区间", "fieldSemantics": "", "fieldValue": "50万-500万元/套"},
            {"fieldKey": "application_scenarios", "fieldLabel": "应用场景", "fieldSemantics": "", "fieldValue": "电商仓储、制造业线边仓"},
            {"fieldKey": "target_user_pain_points", "fieldLabel": "用户痛点", "fieldSemantics": "", "fieldValue": "人工分拣效率低、库存不准"},
            {"fieldKey": "differentiated_advantages", "fieldLabel": "差异化优势", "fieldSemantics": "", "fieldValue": "自研调度算法、模块化部署"}
          ]
        },
        {
          "sectionCode": "company_profile",
          "sectionName": "企业介绍",
          "fields": [
            {"fieldKey": "company_name", "fieldLabel": "企业名称", "fieldSemantics": "", "fieldValue": "某科技有限公司"},
            {"fieldKey": "region", "fieldLabel": "所属地区", "fieldSemantics": "", "fieldValue": "中国深圳"},
            {"fieldKey": "company_positioning", "fieldLabel": "企业定位", "fieldSemantics": "", "fieldValue": "中小仓储智能化一站式服务商"}
          ]
        }
      ],
      "constraintFields": [
        {"fieldKey": "sensitive_words", "fieldLabel": "敏感词", "fieldSemantics": "", "fieldValue": "最、第一、国家级、全球领先"}
      ]
    }
  }
}
```

---

## 完整工作流

### 第一步：准备知识库

按[知识库格式](#知识库格式)准备 JSON 文件。

### 第二步：生成种子问题

```bash
python main.py run --kb data/my_kb.json --industry "工业制造"
```

### 第三步：挑选种子问题，生成文章

从 `seeds.txt` 选 1 条，加入知识库的 `entryText` 字段，再次执行：

```bash
python main.py run --kb data/my_kb.json --industry "工业制造"
```

### 第四步：查看输出

```bash
ls output/{企业名}/articles/
cat output/{企业名}/reviews/001_review.md
```

---

## CLI 命令

### `run` — 主命令（自动路由）

```bash
python main.py run --kb <知识库路径> [选项]
```

| 选项 | 说明 |
|------|------|
| `--kb PATH` | 知识库 JSON 文件路径 |
| `--kb-stdin` | 从标准输入读取知识库 |
| `--kb-json TEXT` | 直接传入 JSON 字符串 |
| `--industry TEXT` | 行业分类（默认"企业服务"） |
| `--count INT` | 种子问题数量（默认使用 KB 中的 entryCount） |
| `--w1/w2/w3 INT` | 文章风格权重（默认 40/35/25） |
| `--image` | 启用配图提示词生成 |
| `--dry-run` | 预演模式，展示执行计划，不调用 LLM |
| `--resume` | 从上次中断点恢复 |
| `--skip-precheck` | 跳过知识库预检（强制执行） |
| `-I` / `--interactive` | 交互模式，每个步骤完成后询问 |

### `seed` — 仅生成种子问题

```bash
python main.py seed --kb data/kb.json --industry "工业制造" --count 20
```

### `match` — 字段匹配

```bash
python main.py match --kb data/kb.json --seeds output/{企业}/seeds.json
```

### `write` — 文章生成

```bash
python main.py write --kb data/kb.json --seeds output/{企业}/seeds.json --w1 40 --w2 35 --w3 25
```

### 管道输入

```bash
cat kb.json | python main.py run --kb-stdin --industry "工业制造"
```

---

## 配置说明

### LLM 配置 (`config/llm_providers.yaml`)

```yaml
providers:
  - name: deepseek-v3
    type: openai_compat
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    priority: 1
```

- `type`：目前支持 `openai_compat`（覆盖 DeepSeek/千问/OpenAI/Ollama 等所有 OpenAI 兼容 API）
- `priority`：数字越小优先级越高，高优先级失败自动 fallback 到下一级
- `api_key`：支持 `${ENV_VAR}` 环境变量引用

### 环境变量 (`.env`)

```env
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx
GEO_OUTPUT_DIR=./output
```

### 文章风格权重

| 参数 | 阶段 | 风格 | 默认权重 |
|------|------|------|---------|
| `--w1` | 一阶段 | 科普避坑文（搜狐号爆款模型，工具实测五段式） | 40 |
| `--w2` | 二阶段 | 深度解析文（行业白皮书，双案例实战） | 35 |
| `--w3` | 平稳期 | SEO知识型文（证据链逻辑，长期收录） | 25 |

---

## 输出结构

```
output/{企业名称}/
├── seeds.txt                 # 种子问题文本
├── seeds.json                # 结构化数据（含维度分组统计）
├── match_results.json        # 字段匹配结果
├── rejected_trials.json      # 被拒绝的种子及原因
├── knowledge_gaps.json       # 知识库补全建议（LLM 分析）
├── kb_precheck.json          # 知识库预检报告
├── pipeline_state.json       # 流程状态（断点恢复用）
├── report.json               # 执行汇总
├── articles/
│   ├── phase1_养号/          # 科普避坑风格
│   ├── phase2_养号/          # 深度解析风格
│   └── stable_平稳/          # SEO知识型风格
├── reviews/
│   ├── 001_review.md         # 审核报告（去AI化 + GEO收录评分）
│   └── 001_diff.md           # 修改前后对比（revise/rewrite 时生成）
└── image_prompts/            # 配图提示词（仅 --image 启用）
    └── 001_prompts.txt       # 标题图 + 场景图 + 流程图
```

### 审核报告指标

| 指标 | 满分 | 说明 |
|------|------|------|
| 去AI化 | 100 | 越低越像 AI 生成（检测套话/万能过渡/空洞量化等 10 类痕迹） |
| GEO收录 | 100 | 越高越可能被 AI 平台引用 |
| 信息密度 | 25 | 具体数字/案例名称/技术参数 |
| 结构适配 | 20 | 小标题+列表+加粗 |
| 权威信号 | 15 | 政策文件/合规认证引用 |
| 问题匹配 | 20 | 紧扣种子问题的回答质量 |
| 独特性 | 10 | 独到观察角度或反常识结论 |
| 引用友好 | 10 | 150-350字独立段落适配 AI 片段提取 |

---

## 行业支持

内置 19 个行业 + 1 个通用默认行业，每个行业有独立的种子问题 Prompt 和配图视觉风格：

| 行业 | 种子维度数 | 视觉风格 |
|------|-----------|---------|
| 工业制造 | 6 | 蓝灰金属+警示黄，侧逆光工业写实 |
| 家居家装 | 7 | 暖木色+米白，自然窗光 |
| 食品饮料 | 6 | 暖橙+奶白，美食微距 |
| 美妆个护 | 7 | 裸粉+象牙白，极简产品摄影 |
| 数码家电 | 6 | 深空黑+电光蓝，科技感渲染 |
| 服装鞋帽 | 7 | 中性灰+大地色，时尚街拍 |
| 医疗健康 | 7 | 医用白+浅蓝，洁净实验室光 |
| 教育培训 | 7 | 明黄+天蓝，明亮人文纪实 |
| 金融服务 | 7 | 深蓝+金色，商务极简 |
| 企业服务 | 7 | 深灰+科技蓝，现代办公 |
| 汽车交通 | 8 | 金属灰+烈焰红，动态摄影 |
| 房地产 | 6 | 大地色+天空蓝，建筑空间摄影 |
| 餐饮美食 | 9 | 焦糖色+奶油白，氛围感美食 |
| 旅游出行 | 8 | 天蓝+沙金，旅行风光 |
| 文化娱乐 | 6 | 霓虹粉+电光青，霓虹潮流 |
| 农林牧渔 | 7 | 大地绿+丰收金，自然农耕纪实 |
| 本地生活 | 7 | 城市灰+活力橙，城市街拍 |
| 综合零售 | 6 | 暖白+活力红，明亮商超 |
| 通用(default) | 7 | 深蓝+银灰，现代商务 |

---

## 项目结构

```
GEO/
├── main.py                    # CLI 入口（Typer）
├── config/                    # 全局配置 + LLM 提供商
├── core/                      # 核心业务逻辑（6 个模块）
│   ├── pipeline.py            # 流程编排器（预检→种子→匹配→生文→审核→配图）
│   ├── seed_generator.py      # 种子问题生成
│   ├── field_matcher.py       # 字段匹配与质量门控
│   ├── article_generators.py  # 三风格文章生成（权重路由 + JSON 重试）
│   ├── article_reviewer.py    # 审核模块（去AI化 + GEO评分 + revise/rewrite）
│   └── image_gen.py           # 配图提示词（行业风格驱动）
├── llm/                       # LLM 适配层
│   ├── router.py              # 多模型 fallback 路由器
│   └── providers/             # Provider 实现（OpenAI 兼容接口）
├── prompts/                   # Prompt 模板（6 个模块）
│   ├── industry_registry.py   # 20 行业种子问题 Prompt
│   ├── phase_articles.py      # 三阶段文章 Prompt（含标题多样性模板）
│   ├── field_match.py         # 字段匹配 Prompt
│   ├── kb_analysis.py         # 知识库预检 + 拒因分析
│   ├── article_review.py      # 审核 Prompt（去AI化 + GEO收录）
│   └── image_styles.py        # 20 行业配图视觉风格
├── knowledge/                 # 知识库层
├── output/                    # 输出写入器
├── utils/                     # 工具（日志、敏感词过滤）
├── docs/                      # 文档
└── scripts/                   # 辅助脚本
```

---

## 常见问题

### Q: 同一知识库多次调用会重复生成种子问题吗？

会。每次步骤1 调用 LLM 生成新种子。如需去重可在外部比对 `seeds.json`。

### Q: 审核结果始终是"需修改"怎么办？

`revise` 是常态——完全 `pass` 的门槛很高。revise 阶段会自动调用 LLM 逐条修改交稿，不需要人工干预。

### Q: rewrite 会一直循环消耗 token 吗？

不会。最多重写 2 次，每次都重新审核。2 次后仍不合格则接受当前版本，不会死循环。

### Q: 能否自定义配图风格？

编辑 `prompts/image_styles.py` 中对应行业的 `style`、`palette`、`scene_logic`、`flowchart_logic` 字段即可。

### Q: 支持哪些 LLM？

所有 OpenAI 兼容接口：DeepSeek、阿里百炼（千问）、OpenAI、Ollama 本地模型等。在 `config/llm_providers.yaml` 添加配置即可，系统自动按优先级 fallback。

### Q: 如何预估一次调用的 token 消耗？

```bash
python main.py run --kb kb.json --industry "工业制造" --dry-run
```

### Q: 流程中断了怎么办？

```bash
python main.py run --kb kb.json --industry "工业制造" --resume
```

从上次中断的步骤继续执行。

### Q: 如何跳过知识库预检（信息密度不足时强制执行）？

```bash
python main.py run --kb kb.json --industry "工业制造" --skip-precheck
```

### Q: 三种文章风格的区别是什么？

| 阶段 | 定位 | 标题风格 | 正文特征 |
|------|------|---------|---------|
| phase1 养号 | 拉新引流 | 数字+身份+量化结果 | 工具实测五段式，搜狐号爆款模型 |
| phase2 养号 | 建立权威 | 白皮书/学术感 | 双案例实战，第三人称客观，15%篇幅限制 |
| stable 平稳 | 长期收录 | 百科/指南式 | 证据链逻辑（痛点→场景→方案→案例），软锚点结尾 |

### Q: 流程中哪些步骤消耗 token 最多？

步骤3（文章生成）最耗 token（~8000），步骤1（种子生成）次之（~8000），步骤2（字段匹配 ~4200）和步骤4（审核 ~1000）较轻。使用 `--dry-run` 可精确预估。

---

## 优化历程

本项目从阿里云百炼 5 个工作流模板重构而来，陆续进行了以下优化：

| 轮次 | 优化内容 | 背景 |
|------|---------|------|
| **第1轮** | 5 工作流 → Python 单体项目 | 解耦百炼平台，支持多 LLM |
| **第2轮** | 加入 `entryText` 自动路由、字段精简（baseFields + referencedFields） | 减少 token 消耗 ~67%，支持种子/生文分步调用 |
| **第3轮** | 知识库预检、拒因分析、质量门控 | 防止信息密度不足的知识库进入生文流程 |
| **第4轮** | 步骤间状态持久化 + `--resume` 断点恢复 | API 超时/网络抖动后无需从头重跑 |
| **第5轮** | CLI `--dry-run` 模式、步骤2→3 上下文复用（matchContext） | 上线前参数确认、减少文章编造概率 |
| **第6轮** | 5 项生文模板优化 | |
| | - 每个段落强制引用 referencedFields 中的具体数据 | 原版存在模糊引语（"根据行业数据..."） |
| | - 每种文章风格预设 8 种标题句式，随机选用 | 原版标题高度雷同（phase1 全是"N步/招"） |
| | - baseFields 精简为仅企业名+定位 1 句话 | 三阶段文章公司介绍段落雷同 |
| | - `##` 段落严格 150-350 字 | 适配 AI 平台片段式引用提取 |
| | - stable 末尾加入软性锚点 | 原版过度去营销化，缺乏行动引导 |
| **第7轮** | 文章审核模块（去AI化检测 + GEO收录评分） | 缺乏生成后质量反馈 |
| **第8轮** | 审核三路分流：pass/revise/rewrite + 死循环防护 | revise 局部修改成本低，rewrite 系统性重写，最多 2 次 |
| **第9轮** | 审核报告与文章正文分离、元数据移至报告 | 文章正文保持干净，审核/元数据独立查看 |
| **第10轮** | 行业驱动的配图提示词（20 行业独立视觉风格） | 工业制造和美妆个护的视觉风格应该完全不同 |

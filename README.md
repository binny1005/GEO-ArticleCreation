# GEO-ArticleCreation

面向 AI 搜索引擎（AIO/GEO）的企业推广文章自动生成系统。基于企业知识库，自动生成 AI 平台可引用的高质量推广内容。

---

## 核心流程

```
企业知识库 JSON
  ├─ 无 entryText → 步骤1: LLM 生成种子问题（模拟真实用户搜索提问）
  │                  → 输出 seeds.json（含维度分组统计）
  │
  └─ 有 entryText → 步骤2: 字段匹配与评估（知识库是否足够支撑文章）
                    → 步骤3: 权重路由生成文章（3 种风格随机分配）
                    → 步骤4: 行业风格配图提示词（标题图 + 2 张插图）
```

### 三步工作流

| 步骤 | 功能 | 输出 |
|------|------|------|
| 步骤1 | 种子问题生成 | `seeds.txt` + `seeds.json`（20 条口语化搜索问题，按维度分组） |
| 步骤2 | 字段匹配与评估 | `match_results.json`（匹配度 + 充足性判定） |
| 步骤3 | 文章生成 | `articles/*.md`（科普/深度/SEO 三风格权重路由） |
| 步骤4 | 配图提示词 | `image_prompts/*.txt`（封面 + 场景图 + 流程图） |

---

## 快速开始

### 安装

```bash
git clone https://github.com/binny1005/GEO-ArticleCreation.git
cd GEO-ArticleCreation
pip install -r requirements.txt
cp .env.example .env  # 编辑填入 API Key
```

### 配置 LLM

编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-your-key-here
```

编辑 `config/llm_providers.yaml` 配置更多 LLM 及优先级：

```yaml
providers:
  - name: deepseek-v3
    type: openai_compat
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    priority: 1          # 数字越小优先级越高，失败自动 fallback
```

支持的 LLM 类型：所有 OpenAI 兼容接口（DeepSeek / 千问 / OpenAI / 等）。

### 使用

**模式 A：生成种子问题**

```bash
python main.py run --kb data/your_kb.json --industry "工业制造"
# → 输出 20 条种子问题（数量由 KB 中 entryCount 决定）
# → 保存到 output/{company_name}/seeds.json
```

**模式 B：生成文章**

在知识库 JSON 中加入 `entryText` 字段（从步骤 A 的结果中挑选 1 条种子问题），再次执行：

```bash
python main.py run --kb data/your_kb.json --industry "工业制造"
# → 自动检测 entryText → 跳过步骤1 → 执行字段匹配 + 文章生成
```

**模式 C：生成配图提示词**

```bash
python main.py run --kb data/your_kb.json --industry "工业制造" --image
# → 额外输出标题图 + 场景图 + 流程图提示词
```

**其他模式：**

```bash
python main.py run --kb data/your_kb.json --industry "工业制造" --dry-run  # 预演计划
python main.py run --kb data/your_kb.json --industry "工业制造" --resume   # 断点恢复
python main.py run --kb data/your_kb.json --industry "工业制造" -I          # 交互模式
```

### 通过管道传入知识库

```bash
cat your_kb.json | python main.py run --kb-stdin --industry "工业制造"
```

---

## 知识库格式

详见 [docs/KB_FORMAT.md](docs/KB_FORMAT.md)

### 最小结构

```json
{
  "input": {
    "biz_params": {
      "companyName": "广州英派尔建设工程有限公司",
      "coreProductName": "实验室洁净",
      "entryCount": 20,
      "lengthmin": 800,
      "lengthmax": 2000,
      "titlelength": 30,
      "entryText": "",
      "sections": [
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
      ],
      "constraintFields": [
        {
          "fieldKey": "sensitive_words",
          "fieldLabel": "敏感词过滤",
          "fieldSemantics": "敏感词、禁用表达",
          "fieldValue": "最、第一、国家级、全球领先"
        }
      ]
    }
  }
}
```

### 关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `companyName` | string | 企业品牌名称 |
| `coreProductName` | string | 核心产品/服务 |
| `entryCount` | int | 种子问题数量（默认 20） |
| `entryText` | string | 种子问题文本（不为空时跳过步骤1） |
| `lengthmin` | int | 文章最小字数（默认 800） |
| `lengthmax` | int | 文章最大字数（默认 2000） |
| `titlelength` | int | 标题最大字符数（默认 30） |
| `sections` | array | 结构化企业资料 |
| `constraintFields` | array | 敏感词列表 |

### 支持的行业

19 个行业 + default，覆盖主流 B2B/B2C 场景：工业制造、家居家装、食品饮料、美妆个护、数码家电、服装鞋帽、医疗健康、教育培训、金融服务、企业服务、汽车交通、房地产、餐饮美食、旅游出行、文化娱乐、农林牧渔、本地生活、综合零售。

每个行业有独立的种子问题 Prompt 和配图视觉风格。

---

## 输出结构

```
output/{company_name}/
├── seeds.txt                 # 种子问题文本
├── seeds.json                # 种子问题（含维度分组统计）
├── match_results.json        # 字段匹配结果
├── rejected_trials.json      # 被拒绝的种子（含拒绝原因）
├── knowledge_gaps.json       # 知识库补全建议
├── kb_precheck.json          # 知识库预检报告
├── pipeline_state.json       # 流程状态（支持断点恢复）
├── report.json               # 汇总报告
├── articles/
│   ├── phase1_养号/          # 科普避坑风格
│   ├── phase2_养号/          # 深度解析风格
│   └── stable_平稳/          # SEO知识型风格
└── image_prompts/
    └── 001_prompts.txt       # 标题图 + 文内插图提示词
```

---

## 项目结构

```
GEO/
├── main.py                    # CLI 入口
├── config/                    # 全局配置 + LLM 提供商
├── core/                      # 核心逻辑
│   ├── pipeline.py            # 流程编排器
│   ├── seed_generator.py      # 种子问题生成
│   ├── field_matcher.py       # 字段匹配与评估
│   ├── article_generators.py  # 文章生成（3 风格）
│   └── image_gen.py           # 配图提示词生成
├── llm/                       # LLM 适配层
│   ├── router.py              # 多模型 fallback 路由器
│   └── providers/             # LLM 提供商实现
├── prompts/                   # Prompt 模板
│   ├── industry_registry.py   # 20 行业种子问题 Prompt
│   ├── phase_articles.py      # 三阶段文章 Prompt
│   ├── field_match.py         # 字段匹配 Prompt
│   ├── kb_analysis.py         # 知识库预检 + 拒因分析
│   └── image_styles.py        # 20 行业配图风格
├── knowledge/                 # 知识库加载与校验
├── output/                    # 输出写入器
├── utils/                     # 工具（日志、敏感词过滤）
├── docs/                      # 文档
└── scripts/                   # 辅助脚本
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| LLM 调用 | OpenAI SDK（兼容 DeepSeek/千问/OpenAI 等） |
| 配置 | YAML + python-dotenv |
| CLI | Typer |
| Prompt 模板 | Jinja2 |
| 数据模型 | Pydantic v2 |

# GEO-ArticleCreation 使用手册

面向 AI 搜索引擎（AIO/GEO）的企业推广文章自动生成系统。

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
    priority: 1    # 数字越小优先级越高，失败自动 fallback
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

### 三步工作流

```
知识库 JSON → [步骤1]种子问题生成 → [步骤2]字段匹配 → [步骤3]文章生成 → [步骤4]审核修改
```

| 步骤 | 功能 | 触发条件 | 输出 |
|------|------|---------|------|
| 预检 | 知识库信息密度扫描 | 自动 | 薄弱维度报告 |
| 步骤1 | 生成种子问题 | 无 entryText | seeds.txt + seeds.json |
| 步骤2 | 字段匹配与质量门控 | 有 entryText | match_results.json |
| 步骤3 | 三风格文章生成 | 有 entryText | articles/*.md |
| 步骤4 | 去AI化检测 + 收录评分 + 修改 | 有文章 | reviews/*.md |

### 自动路由

系统根据知识库中是否存在 `entryText` 自动决定执行路径：

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
| `companyName` | string | ✅ | - | 企业品牌名称 |
| `coreProductName` | string | ✅ | - | 核心产品/服务名称 |
| `entryCount` | int | 否 | 20 | 种子问题生成数量 |
| `entryText` | string | 否 | "" | 种子问题文本（不为空时跳过步骤1） |
| `lengthmin` | int | 否 | 800 | 文章最小字数 |
| `lengthmax` | int | 否 | 2000 | 文章最大字数 |
| `titlelength` | int | 否 | 30 | 标题最大字符数 |
| `sections` | array | ✅ | - | 结构化企业资料 |
| `constraintFields` | array | 否 | [] | 敏感词/禁用表达 |

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
      "fieldValue": "1、洁净度管控能力强..."
    }
  ]
}
```

### 建议的 sectionCode

| sectionCode | 用途 | 用于 |
|-------------|------|------|
| `product_info` | 产品/服务核心信息 | referencedFields（步骤3素材） |
| `company_profile` | 企业基本信息 | baseFields（步骤3企业背景） |
| `development_history` | 发展历程 | 补充素材 |
| `qualification_honor` | 资质荣誉 | 权威背书 |
| `team_profile` | 团队介绍 | 专业度佐证 |
| `market_customer` | 市场客户 | 案例素材 |

### 最小示例

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

按照[知识库格式](#知识库格式)准备 JSON 文件，保存为 `data/my_kb.json`。

### 第二步：生成种子问题

```bash
python main.py run --kb data/my_kb.json --industry "工业制造"
```

输出 20 条（或 `entryCount` 指定数量）种子问题到 `output/{企业名}/seeds.txt` 和 `seeds.json`。

### 第三步：挑选种子问题，生成文章

从 `seeds.txt` 中挑选 1 条种子问题，加入知识库 JSON 的 `entryText` 字段：

```json
"entryText": "2026年建个百级密闭实验室多少钱"
```

再次执行：

```bash
python main.py run --kb data/my_kb.json --industry "工业制造"
```

系统自动检测 `entryText` → 跳过步骤1 → 执行字段匹配 → 文章生成 → 审核修改。

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
| `--dry-run` | 预演模式，不调用 LLM |
| `--resume` | 从上次中断点恢复 |
| `--skip-precheck` | 跳过知识库预检 |
| `-I` / `--interactive` | 交互模式，每步确认 |

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

  - name: qwen3-max
    type: openai_compat
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DASHSCOPE_API_KEY}
    model: qwen3-max
    priority: 2
```

- `type`：目前支持 `openai_compat`（覆盖所有 OpenAI 兼容 API）
- `priority`：数字越小优先级越高，高优先级失败自动降级
- `api_key`：支持 `${ENV_VAR}` 环境变量引用

### 环境变量 (`.env`)

```env
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx
GEO_OUTPUT_DIR=./output
```

### 文章风格权重

```bash
python main.py run --kb kb.json --industry "工业制造" --w1 40 --w2 35 --w3 25
```

| 参数 | 阶段 | 风格 |
|------|------|------|
| `--w1` | 一阶段 | 科普避坑文（搜狐号爆款模型） |
| `--w2` | 二阶段 | 深度解析文（行业白皮书风格） |
| `--w3` | 平稳期 | SEO知识型文（长期收录型） |

---

## 输出结构

```
output/{企业名称}/
├── seeds.txt                 # 种子问题文本
├── seeds.json                # 结构化数据（含维度分组统计）
├── match_results.json        # 字段匹配结果
├── rejected_trials.json      # 被拒绝的种子及原因
├── knowledge_gaps.json       # 知识库补全建议
├── kb_precheck.json          # 知识库预检报告
├── pipeline_state.json       # 流程状态（断点恢复用）
├── report.json               # 执行汇总报告
├── articles/
│   ├── phase1_养号/          # 科普避坑风格文章
│   ├── phase2_养号/          # 深度解析风格文章
│   └── stable_平稳/          # SEO知识型风格文章
├── reviews/
│   ├── 001_review.md         # 审核报告（去AI化 + GEO评分）
│   └── 001_diff.md           # 修改前后对比（仅revise/rewrite时）
└── image_prompts/            # 配图提示词（仅 --image 启用）
    └── 001_prompts.txt       # 标题图 + 2张插图提示词
```

### 审核报告字段

| 指标 | 满分 | 说明 |
|------|------|------|
| 去AI化 | 100 | 越高越不像 AI 生成 |
| GEO收录 | 100 | 越高越可能被 AI 平台引用 |
| 信息密度 | 25 | 具体数字/案例数量 |
| 结构适配 | 20 | 小标题/列表/加粗 |
| 权威信号 | 15 | 政策文件/合规认证 |
| 问题匹配 | 20 | 紧扣种子问题 |
| 独特性 | 10 | 独到角度 |
| 引用友好 | 10 | 段落长度适配 AI 片段提取 |

---

## 行业支持

内置 19 个行业 + 1 个默认通用行业，每个行业有独立的种子问题 Prompt 和配图视觉风格：

| 行业 | 种子维度 | 视觉风格 |
|------|---------|---------|
| 工业制造 | 询价/工艺/起订/交期/质量/甄别 | 蓝灰金属+警示黄 |
| 家居家装 | 效果/痛点/选材/预算/空间/避雷/智能 | 暖木色+米白 |
| 食品饮料 | 口味/健康/性价比/场景/送礼/储存 | 暖橙+奶白 |
| 美妆个护 | 突发/肤质/成分/预算/搭配/年龄/渠道 | 裸粉+象牙白 |
| 数码家电 | 预算/概念/参数/售后/人群/空间 | 深空黑+电光蓝 |
| 服装鞋帽 | 尺码/材质/穿搭/性价比/舒适/健康/洗护 | 中性灰+大地色 |
| 医疗健康 | 分诊/方案/费用/机构/用药/慢病/医美 | 医用白+浅蓝 |
| 教育培训 | 成绩/升学/兴趣/考证/机构/费用/效果 | 明黄+天蓝 |
| 金融服务 | 价格/选型/实施/售后/合规/效率/适配 | 深蓝+金色 |
| 企业服务 | 价格/选型/实施/售后/合规/效率/适配 | 深灰+科技蓝 |
| 汽车交通 | 预算/车型/油耗/新能源/智驾/保值/贷款 | 金属灰+烈焰红 |
| 房地产 | 时机/资金/地段/交付/户型/二手房 | 大地色+天空蓝 |
| 餐饮美食 | 位置/场景/口味/需求/口碑/性价比/纠结/外卖/正宗 | 焦糖色+奶油白 |
| 旅游出行 | 目的地/行程/交通/住宿/门票/预算/特殊/天气 | 天蓝+沙金 |
| 文化娱乐 | 价格/选店/预约/人群/新手/内容 | 霓虹粉+电光青 |
| 农林牧渔 | 品种/病虫害/肥料/农机/销售/技术/政策 | 大地绿+丰收金 |
| 本地生活 | 价格/质量/地理/预约/口碑/团购/售后 | 城市灰+活力橙 |
| 综合零售 | 挑选/省钱/售后/平台/配送/质量 | 暖白+活力红 |
| default | 通用维度 | 深蓝+银灰 |

---

## 常见问题

### Q: 同一知识库多次调用会重复生成种子问题吗？

会。每次步骤1 调用 LLM 生成新种子。如果需要去重，可以在外部比对 `seeds.json`。

### Q: 审核结果始终是"需修改"怎么办？

`revise` 是常态——完全通过 `pass` 的审核门槛很高（去AI化 ≥ 80 且 GEO收录 ≥ 90）。revise 阶段会自动修改交稿。

### Q: rewrite 会一直循环吗？

不会。最多重写 2 次，每次都重新审核。2 次后仍不合格则接受当前版本。

### Q: 能否自定义配图风格？

当前配图风格由行业预设。可通过编辑 `prompts/image_styles.py` 覆盖具体行业的风格参数。

### Q: 支持哪些 LLM？

所有 OpenAI 兼容接口的 LLM：DeepSeek、阿里百炼（千问）、OpenAI、Ollama 本地模型等。在 `config/llm_providers.yaml` 中添加配置即可。

### Q: 如何预估一次调用的 token 消耗？

```bash
python main.py run --kb kb.json --industry "工业制造" --dry-run
```

### Q: 流程中断了怎么办？

重新运行加 `--resume`：

```bash
python main.py run --kb kb.json --industry "工业制造" --resume
```

系统从上次中断的步骤继续执行。

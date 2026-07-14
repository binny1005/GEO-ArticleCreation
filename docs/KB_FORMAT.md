# GEO 知识库传入格式规范

## 顶层结构

```json
{
  "input": {
    "prompt": "请基于提供的结构化企业资料和生成约束，生成适合用于企业GEO内容布局的可追溯的词条结果。",
    "biz_params": {
      // 核心参数，见下方说明
    }
  }
}
```

---

## biz_params 字段说明

### 必填字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `companyName` | string | 企业品牌名称 | `"广州英派尔建设工程有限公司"` |
| `coreProductName` | string | 核心产品/服务名称 | `"实验室洁净"` |
| `sections` | array | 结构化企业资料，至少包含 `product_info` 和 `company_profile` | 见下方 |
| `constraintFields` | array | 敏感词/禁用表达列表 | 见下方 |

### 可选字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `entryCount` | int | `20` | 种子问题生成条数 |
| `entryText` | string | `""` | **种子问题文本**。存在时跳过步骤1（种子生成），直接进入步骤2（字段匹配→生文）。不存在时仅执行步骤1 |

---

## sections 结构

每个 section 包含：

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

### 建议的 sectionCode 列表

| sectionCode | sectionName | 用途 |
|-------------|-------------|------|
| `product_info` | 产品信息 | 核心产品描述、功能、价格、优势、应用场景 |
| `company_profile` | 企业介绍 | 企业基础信息（名称、区域、定位、使命愿景） |
| `development_history` | 发展历程 | 创立时间、背景、里程碑 |
| `qualification_honor` | 资质荣誉 | 行业资质、认证、荣誉 |
| `team_profile` | 团队介绍 | 团队规模、构成、核心成员背景 |
| `market_customer` | 市场客户 | 行业方案、客户案例、合作伙伴 |

> `company_profile` 中的字段将作为步骤3生文的 `baseFields`。

---

## constraintFields 结构

```json
{
  "fieldKey": "sensitive_words",
  "fieldLabel": "敏感词过滤",
  "fieldSemantics": "敏感词、禁用表达与审核限制",
  "fieldValue": "一、通用绝对化极限词\n1. \"最\" 系列：最、最佳、最好、最大、最高..."
}
```

---

## entryText 路由规则

```
传入 entryText 不为空？
  ├─ 是 → 步骤2(字段匹配) → 步骤3(文章生成)
  └─ 否 → 步骤1(种子问题生成) → 输出 → 停止
```

**完整工作流**：
```
第1次调用: 传入无 entryText 的知识库 → 获得 20 条种子问题 → 人工挑选 1 条
第2次调用: 传入同一知识库 + entryText(选中的种子问题) → 获得 1 篇推广文
```

---

## 最小示例

```json
{
  "input": {
    "biz_params": {
      "companyName": "某科技有限公司",
      "coreProductName": "智能仓储系统",
      "entryCount": 20,
      "sections": [
        {
          "sectionCode": "product_info",
          "sectionName": "产品信息",
          "fields": [
            {
              "fieldKey": "core_features",
              "fieldLabel": "核心功能",
              "fieldSemantics": "核心功能与卖点",
              "fieldValue": "全自动分拣、实时库存追踪、AGV调度"
            },
            {
              "fieldKey": "product_price_range",
              "fieldLabel": "价格区间",
              "fieldSemantics": "价格范围",
              "fieldValue": "50万-500万元/套"
            },
            {
              "fieldKey": "application_scenarios",
              "fieldLabel": "应用场景",
              "fieldSemantics": "典型应用场景",
              "fieldValue": "电商仓储、制造业线边仓、冷链物流"
            },
            {
              "fieldKey": "target_user_pain_points",
              "fieldLabel": "目标用户痛点",
              "fieldSemantics": "核心用户痛点",
              "fieldValue": "人工分拣效率低、库存不准、旺季用工难"
            },
            {
              "fieldKey": "differentiated_advantages",
              "fieldLabel": "差异化优势",
              "fieldSemantics": "差异化优势",
              "fieldValue": "自研调度算法、7x24运维、模块化部署"
            }
          ]
        },
        {
          "sectionCode": "company_profile",
          "sectionName": "企业介绍",
          "fields": [
            {
              "fieldKey": "company_name",
              "fieldLabel": "企业名称",
              "fieldSemantics": "企业名称",
              "fieldValue": "某科技有限公司"
            },
            {
              "fieldKey": "region",
              "fieldLabel": "所属地区",
              "fieldSemantics": "服务区域",
              "fieldValue": "中国深圳"
            },
            {
              "fieldKey": "company_positioning",
              "fieldLabel": "企业定位",
              "fieldSemantics": "企业定位",
              "fieldValue": "中小仓储智能化一站式服务商"
            }
          ]
        }
      ],
      "constraintFields": [
        {
          "fieldKey": "sensitive_words",
          "fieldLabel": "敏感词过滤",
          "fieldSemantics": "敏感词",
          "fieldValue": "最、第一、国家级、全球领先、唯一"
        }
      ]
    }
  }
}
```

---

## 注意事项

1. **fieldValue 中的 HTML 标签**：`<br>` 标签会被保留并传给 LLM，用于结构化展示
2. **信息密度**：预检模块会扫描 sections 评估各维度信息密度，薄弱维度 ≥ 3 时终止流程
3. **字符编码**：所有 JSON 文件使用 UTF-8 编码
4. **字段语义**：`fieldSemantics` 帮助 LLM 理解字段含义，即使 `fieldValue` 为空也不会影响匹配

"""知识库 JSON 加载器 — 支持文件路径、JSON 字符串、stdin 三种输入方式"""

import json
import sys
from pathlib import Path
from typing import Union

from .schema import KnowledgeBase, BizParams


def load_knowledge_base(source: Union[str, Path] = None, *, json_str: str = None, stdin: bool = False) -> KnowledgeBase:
    """
    加载知识库，支持三种方式（按优先级）：
    1. json_str: 直接传入 JSON 字符串
    2. stdin: True 时从标准输入读取
    3. source: 文件路径（Path 对象或字符串）
    """
    data = None

    # 方式 1: 直接传 JSON 字符串
    if json_str is not None:
        data = json.loads(json_str)

    # 方式 2: 从标准输入读取
    elif stdin:
        raw = sys.stdin.read().strip()
        if not raw:
            raise ValueError("stdin 无数据，请通过管道传入知识库 JSON")
        data = json.loads(raw)

    # 方式 3: 从文件读取
    elif source is not None:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"知识库文件不存在: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

    else:
        raise ValueError("必须提供 source、json_str 或 stdin=True 中的一种")

    return KnowledgeBase(**data)


def create_knowledge_base(biz_params_data: dict) -> KnowledgeBase:
    """从 biz_params 字典直接创建 KnowledgeBase（适配直接传参的情况）"""
    return KnowledgeBase(input={"biz_params": biz_params_data})


def extract_sections_for_prompt(biz_params: BizParams) -> str:
    """将 sections 转为 LLM prompt 可用的文本格式"""
    lines = []
    for section in biz_params.sections:
        lines.append(f"\n## {section.sectionName} ({section.sectionCode})")
        for field in section.fields:
            value = field.fieldValue or "(空)"
            # 截断过长字段值
            if len(value) > 500:
                value = value[:500] + "..."
            lines.append(f"  [{field.fieldKey}] {field.fieldLabel}: {value}")
    return "\n".join(lines)


def extract_constraint_for_prompt(biz_params: BizParams) -> str:
    """提取敏感词列表供 prompt 使用"""
    words = []
    for cf in biz_params.constraintFields:
        if cf.fieldValue:
            words.append(cf.fieldValue)
    return "\n".join(words)


# ── 步骤3字段精简 ──

BASE_FIELD_SECTIONS = ["company_profile"]  # 企业基础信息所属的 sectionCode


def extract_base_fields(biz_params: BizParams) -> str:
    """
    提取企业基础信息字段（company_profile section），
    作为步骤3生文的 baseFields 传入。
    """
    lines = []
    for section in biz_params.sections:
        if section.sectionCode in BASE_FIELD_SECTIONS:
            for field in section.fields:
                value = field.fieldValue or "(空)"
                if len(value) > 300:
                    value = value[:300] + "..."
                lines.append(f"[{field.fieldKey}] {field.fieldLabel}: {value}")
    return "\n".join(lines)


def resolve_referenced_fields(biz_params: BizParams, field_refs: list[str]) -> str:
    """
    根据步骤2返回的 fieldRefs（fieldKey 列表），从知识库中查找对应字段内容，
    作为步骤3生文的 referencedFields 传入。
    """
    lines = []
    for ref in field_refs:
        for section in biz_params.sections:
            for field in section.fields:
                if field.fieldKey == ref and field.fieldValue:
                    value = field.fieldValue
                    if len(value) > 500:
                        value = value[:500] + "..."
                    lines.append(f"[{field.fieldKey}] {field.fieldLabel}: {value}")
                    break
    return "\n".join(lines)

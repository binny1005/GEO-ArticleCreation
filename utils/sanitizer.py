"""敏感词过滤工具 — 检查生成内容是否包含 constraintFields 中的禁用词"""

import re
from knowledge.schema import BizParams


def extract_sensitive_patterns(biz_params: BizParams) -> list[str]:
    """从 constraintFields 中提取需要过滤的禁用词列表"""
    patterns = []
    for cf in biz_params.constraintFields:
        if not cf.fieldValue:
            continue
        # fieldValue 是换行分隔的文本，按行拆分提取关键词
        for line in cf.fieldValue.split("\n"):
            line = line.strip()
            # 跳过分类标题行（如 "1. \"最\" 系列（高频违规）"）
            if not line or line.startswith("#") or len(line) < 2:
                continue
            # 提取中文词汇
            words = re.findall(r'[一-鿿　-〿＀-￯]{2,}', line)
            patterns.extend(words)
    # 去重，按长度降序（先匹配长词，避免短词误匹配）
    return sorted(set(patterns), key=len, reverse=True)


def check_sensitive(text: str, biz_params: BizParams) -> list[str]:
    """检查文本是否包含敏感词，返回匹配到的禁用词列表"""
    patterns = extract_sensitive_patterns(biz_params)
    found = []
    for word in patterns:
        if word in text:
            found.append(word)
    return found


def is_clean(text: str, biz_params: BizParams) -> bool:
    """Check if text is free of sensitive words"""
    return len(check_sensitive(text, biz_params)) == 0

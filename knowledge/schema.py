"""知识库数据模型 — 对齐百炼 Start 节点输入结构"""

from typing import Optional
from pydantic import BaseModel, Field


class FieldItem(BaseModel):
    """知识库中的单个字段"""
    fieldKey: str = ""
    fieldLabel: str = ""
    fieldSemantics: str = ""
    fieldValue: str = ""


class Section(BaseModel):
    """知识库中的一个 section（如 product_info, company_profile）"""
    sectionCode: str = ""
    sectionName: str = ""
    fields: list[FieldItem] = []

    def get_field(self, key: str) -> Optional[FieldItem]:
        """按 fieldKey 查找字段"""
        for f in self.fields:
            if f.fieldKey == key:
                return f
        return None

    def get_value(self, key: str, default: str = "") -> str:
        """按 fieldKey 取值"""
        field = self.get_field(key)
        return field.fieldValue if field else default

    def to_dict(self) -> dict[str, str]:
        """转为 {fieldKey: fieldValue} 映射"""
        return {f.fieldKey: f.fieldValue for f in self.fields}


class ConstraintField(BaseModel):
    """敏感词约束"""
    fieldKey: str = ""
    fieldLabel: str = ""
    fieldSemantics: str = ""
    fieldValue: str = ""


class BizParams(BaseModel):
    """百炼工作流的 biz_params 输入层"""
    model_config = {"populate_by_name": True}

    companyName: str = Field(default="", alias="productBrand")
    coreProductName: str = ""
    entryCount: int = 20
    entryText: str = ""          # 种子问题文本（存在时跳过步骤1，直接进入步骤2）
    lengthmin: int = 800          # 文章最小字数
    lengthmax: int = 2000         # 文章最大字数
    titlelength: int = 30         # 标题最大字符数
    sections: list[Section] = []
    constraintFields: list[ConstraintField] = []

    @property
    def company_name(self) -> str:
        return self.companyName

    @property
    def has_entry_text(self) -> bool:
        """是否传入了种子问题（决定是否跳过步骤1）"""
        return bool(self.entryText and self.entryText.strip())

    @property
    def primary_industry_name(self) -> str:
        """从 sections 中推断行业类型（可被外部覆盖）"""
        return "企业服务"

    def get_section(self, code: str) -> Optional[Section]:
        for s in self.sections:
            if s.sectionCode == code:
                return s
        return None

    def get_all_field_keys(self) -> set[str]:
        """获取所有 section 中的 fieldKey 集合"""
        keys = set()
        for s in self.sections:
            for f in s.fields:
                keys.add(f.fieldKey)
        return keys


class KnowledgeBaseInput(BaseModel):
    """TestInput 的顶层包装"""
    biz_params: BizParams = Field(default_factory=BizParams)


class KnowledgeBase(BaseModel):
    """完整知识库（对齐 TestInput 结构）"""
    input: KnowledgeBaseInput = Field(default_factory=KnowledgeBaseInput)

    @property
    def biz_params(self) -> BizParams:
        return self.input.biz_params

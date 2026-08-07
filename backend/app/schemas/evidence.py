"""证据引用契约（EvidenceRef）
所有 Agent 输出必须绑定 EvidenceRef，确保每条结论可追溯。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    """单一证据引用"""

    url: str = Field(..., description="信息来源链接")
    title: str = Field(..., description="信息标题")
    snippet: str = Field(..., max_length=200, description="关键摘要")


class EvidenceMixin(BaseModel):
    """混入类：包含 evidence_refs 的结构化产物基类"""

    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list,
        description="支撑本次分析结论的证据引用列表",
    )
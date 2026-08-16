"""商品级竞品数据统一契约 — 飞书 base_competitors 的归一化视图

CompetitorRecord 是竞品分析消费的商品级数据形状。
与 base_records（BaseRecord）严格区分：竞品表是商品级，明细表是采集记录级。

字段规则（provider 解析时执行，非法记录跳过并记录 caveat，不静默吞掉）：
- product_name / category / snapshot_id 必须有合法值，否则跳过并记录 caveat。
- source_url 缺失不伪造（None），前端显示「来源缺失」；非法值（非 http(s)）→ None。
- price / price_min / price_max 必须是非负数字，非法 → 跳过记录并记 caveat。
- design_score 缺失保持 None（不得补 0）；超出 0-10 时置为 None 并记 caveat。
- selling_points JSON 损坏时返回空列表并记 caveat。
- verification_status 只接受 unverified / reviewed / rejected；非法 → 默认 unverified 并记 caveat。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class VerificationStatus(str, Enum):
    """竞品核验状态 — 只接受这三种；不要把未核验显示成已核验"""

    UNVERIFIED = "unverified"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class CompetitorRecord(BaseModel):
    """商品级竞品记录（来自飞书 base_competitors）"""

    competitor_id: str = Field(..., description="竞品记录唯一标识")
    product_name: str = Field(..., min_length=1, description="商品名称")
    brand: str | None = Field(default=None, description="品牌；缺失不伪造")
    category: str = Field(..., min_length=1, description="品类")
    price: float | None = Field(default=None, ge=0, description="价格（元）")
    price_min: float | None = Field(default=None, ge=0, description="价格下限")
    price_max: float | None = Field(default=None, ge=0, description="价格上限")
    price_band: str | None = Field(default=None, description="价格带标签")
    image_url: str | None = Field(default=None, description="商品图；缺失不伪造")
    selling_points: list[str] = Field(default_factory=list, description="结构化卖点关键词")
    design_score: float | None = Field(default=None, ge=0, le=10, description="设计感评分 0-10；缺失保持 None")
    source_url: str | None = Field(default=None, description="来源链接；缺失不伪造")
    source_platform: str | None = Field(default=None, description="来源平台")
    evidence_quote: str | None = Field(default=None, description="证据原文引用")
    record_date: str | None = Field(default=None, description="业务日期（YYYY-MM-DD）")
    snapshot_id: str = Field(..., min_length=1, description="快照标识")
    ingested_at: str | None = Field(default=None, description="入库时间（ISO8601）")
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.UNVERIFIED, description="核验状态"
    )

    @field_validator("source_url")
    @classmethod
    def _valid_source_url(cls, v: str | None) -> str | None:
        """缺失/空 → None（不伪造）；非 http(s) → None（无效链接不可点击）"""
        if v is None or v.strip() == "":
            return None
        if not v.startswith(("http://", "https://")):
            return None
        return v

    @field_validator("image_url")
    @classmethod
    def _valid_image_url(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        if not v.startswith(("http://", "https://")):
            return None
        return v

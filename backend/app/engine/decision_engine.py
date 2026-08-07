"""Decision Engine — 综合决策引擎

汇聚商业官和全球化官的输出，生成结构化的《商品立项建议书》。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DecisionResult(BaseModel):
    """立项决策结果"""

    product_name: str = Field(..., description="商品名称")
    opportunity_score: float = Field(..., ge=0, le=100, description="机会值评分")
    recommendation: str = Field(
        ..., description="决策建议：approve/hold/reject"
    )
    risk_warnings: list[str] = Field(default_factory=list, description="风险提示")
    reasoning: str = Field(..., description="决策推理过程")
    launch_plan: str | None = Field(default=None, description="上市建议")


class DecisionEngine:
    """综合决策引擎"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def evaluate(
        self,
        business_output: dict,
        global_output: dict,
        ideation_output: dict | None = None,
    ) -> DecisionResult:
        """综合评估商品方案

        Args:
            business_output: 商业官输出
            global_output: 全球化官输出
            ideation_output: 创意官输出（可选）

        Returns:
            DecisionResult: 决策结果
        """
        # 综合评分逻辑
        score = self._calculate_score(business_output, global_output)
        recommendation = self._decide(score)
        risk_warnings = self._extract_risks(business_output, global_output)

        return DecisionResult(
            product_name=business_output.get("product_name", "未知"),
            opportunity_score=score,
            recommendation=recommendation,
            risk_warnings=risk_warnings,
            reasoning=self._generate_reasoning(
                business_output, global_output, score
            ),
            launch_plan=global_output.get("launch_strategy"),
        )

    def _calculate_score(self, business: dict, global_: dict) -> float:
        """计算综合机会值"""
        biz_score = business.get("opportunity_score", 0)
        return min(biz_score, 100.0)

    def _decide(self, score: float) -> str:
        if score >= 80:
            return "approve"
        elif score >= 60:
            return "hold"
        return "reject"

    def _extract_risks(
        self, business: dict, global_: dict
    ) -> list[str]:
        risks = []
        raw_risks = business.get("risk_warnings", [])
        if isinstance(raw_risks, list):
            risks.extend(raw_risks)
        return risks

    def _generate_reasoning(
        self, business: dict, global_: dict, score: float
    ) -> str:
        return f"综合机会值评分 {score:.1f} 分，" \
               f"基于商业评估和全球化策略分析。"
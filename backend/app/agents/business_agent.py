"""BusinessEvaluationAgent — 真实商业官

基于三官 Artifact（feature_matrix / user_sentiment / ip_assessment）与
BusinessSummaryView（Scoped View）的聚合结果，确定性生成五维 OpportunityScore。

评分纪律（不调用 LLM、不编造分数）：
- 五维分数均来自上游真实数据或 View 聚合结果，每个维度 0~100，统一 clamp；
- 缺少数据时保守为 0，并写入对应维度的 risk_warning；
- total_score 由 Weights 加权算术生成，由 OpportunityScore validator 强制校验；
- evidence_refs 只聚合自三官 Artifact 的真实证据引用，不伪造 URL；
- 数据源不可用（BaseUnavailable / BaseProviderError / View 缺失）不得回退 Mock，
  也不得把「数据不可用」变成高分。

纯函数（score_*）只做确定性数学，输入输出均为纯数据，可独立单元测试。
"""

from __future__ import annotations

import os
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.mock_agents import MockBusinessAgent
from app.data.base_adapter import BaseProviderError, BaseUnavailable
from app.engine.decision_engine import min_confidence
from app.schemas import (
    Confidence,
    DimensionScore,
    EvidenceRef,
    OpportunityScore,
    RiskWarning,
    Weights,
)

# ── 纯函数：确定性评分公式 ──────────────────────────

def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """统一 clamp：所有维度分数限制在 [lo, hi]，默认 0~100"""
    return max(lo, min(hi, value))

def score_trend_heat(trends: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """trend_heat = 趋势峰值热度（FeatureMatrix.trends 的 heat_index 最大值）。

    无趋势信号 → 0 + warning，不把缺数据当成趋势热度。
    """
    if not trends:
        return 0.0, ["无趋势信号，trend_heat 保守为 0"]
    heat = max((t.get("heat_index") or 0.0) for t in trends)
    return clamp(float(heat)), []

def score_user_demand(
    pain_points: list[dict[str, Any]],
    motivation_tags: list[str],
    sentiment: dict[str, Any],
) -> tuple[float, list[str]]:
    """user_demand = 痛点平均频率 × 70 + 动机标签数（≤3）× 10。

    不根据文字主观臆造比例；sentiment 为 neutral 占位（无情感测量）时保守计分并加 warning。
    """
    warnings: list[str] = []
    if pain_points:
        avg_freq = sum((p.get("frequency") or 0.0) for p in pain_points) / len(pain_points)
    else:
        avg_freq = 0.0
        warnings.append("无痛点数据，user_demand 保守计分")
    tag_bonus = min(len(motivation_tags), 3) * 10
    if (sentiment.get("neutral") or 0.0) >= 0.999:
        warnings.append("情感为中性占位（无情感测量），user_demand 保守计分")
    score = clamp(avg_freq * 70 + tag_bonus)
    return score, warnings

def score_ip_fit(proposal: dict[str, Any], ip_assessment: dict[str, Any]) -> tuple[float, list[str]]:
    """ip_fit = 提案（名称/概念/IP 引用）与 ip_ranking 的确定性匹配热度。

    rejected=True 的 IP 不得产生正向适配分；未引用已评估 IP → 0 + warning。
    """
    ranking = ip_assessment.get("ip_ranking") or []
    text = f"{proposal.get('name', '')} {proposal.get('concept', '')}"
    for ref in proposal.get("source_map") or []:
        if ref.get("artifact") == "IPAssessment":
            text += f" {ref.get('claim', '')}"

    for cand in ranking:
        ip_name = cand.get("ip_name", "")
        if ip_name and ip_name in text:
            if cand.get("rejected", False):
                return 0.0, [f"IP「{ip_name}」被标记 rejected，ip_fit 为 0"]
            heat = cand.get("heat_score") or 0.0
            return clamp(float(heat)), []
    return 0.0, ["提案未引用任何已评估 IP，ip_fit 保守为 0"]

def score_competition(brand_concentration: dict[str, int]) -> tuple[float, list[str]]:
    """competition = 100 - 品牌数 × 10（品牌越多竞争越激烈，差异化空间越小）。

    可解释的确定性归一化：每个品牌贡献 10 分竞争压力，封顶 10 个品牌。
    """
    if not brand_concentration:
        return 0.0, ["无品牌集中度数据，competition 保守为 0"]
    return clamp(100.0 - len(brand_concentration) * 10.0), []

def score_history_analog(hit_products: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """history_analog = 爆款热度均值（BusinessSummaryView.get_hit_products）。

    无历史爆款参照 → 0 + warning；不把当前趋势热度冒充历史表现。
    """
    if not hit_products:
        return 0.0, ["无历史爆款参照数据，history_analog 保守为 0"]
    avg = sum((p.get("heat_index") or 0.0) for p in hit_products) / len(hit_products)
    return clamp(float(avg)), []

# ── Agent ──────────────────────────

class BusinessEvaluationAgent(BaseAgent):
    """真实商业官：确定性五维评分，不调用 LLM，不编造分数"""

    name = "business_evaluation_agent"
    description = "商业评估：基于三官 Artifact 与商业摘要的五维机会值评分"

    def __init__(self, config: dict | None = None, views: dict[str, Any] | None = None):
        super().__init__(config)
        self.views = views or {}

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        brief = context.get("brief", {})
        weights = Weights.model_validate(context.get("weights", {}))
        proposal_set = context.get("proposal_set", {})
        feature_matrix = context.get("feature_matrix", {})
        user_sentiment = context.get("user_sentiment", {})
        ip_assessment = context.get("ip_assessment", {})
        upstream = context.get("upstream_confidences", [])
        category = brief.get("category", "")
        weight_map = weights.model_dump()

        view = self.views.get("BusinessSummaryView")
        view_failed = False
        if view is None:
            view_failed = True
            brand_conc, comp_view_warnings = {}, ["BusinessSummaryView 不可用"]
            hit_products, hist_view_warnings = [], ["BusinessSummaryView 不可用"]
        else:
            try:
                brand_conc = view.get_brand_concentration(category)
                hit_products = view.get_hit_products(category)
                comp_view_warnings, hist_view_warnings = [], []
            except (BaseUnavailable, BaseProviderError):
                view_failed = True
                brand_conc, comp_view_warnings = {}, ["商业摘要数据源不可用"]
                hit_products, hist_view_warnings = [], ["商业摘要数据源不可用"]

        # 与 proposal 无关的固定维度
        trend_score, trend_warnings = score_trend_heat(feature_matrix.get("trends") or [])
        demand_score, demand_warnings = score_user_demand(
            user_sentiment.get("pain_points") or [],
            user_sentiment.get("motivation_tags") or [],
            user_sentiment.get("sentiment") or {},
        )
        comp_score, comp_warnings = score_competition(brand_conc)
        hist_score, hist_warnings = score_history_analog(hit_products)

        evidence_refs = self._collect_evidence(feature_matrix, user_sentiment, ip_assessment)
        base_conf = min_confidence(upstream)
        conf, caveats = self._resolve_confidence(base_conf, view_failed, brand_conc, hit_products)

        scores = []
        for proposal in proposal_set.get("proposals", []):
            ip_score, ip_warnings = score_ip_fit(proposal, ip_assessment)
            dims = [
                DimensionScore(
                    dimension="trend_heat", score=trend_score,
                    source_agent="trend_agent", basis=f"趋势峰值热度 {trend_score:.1f}",
                ),
                DimensionScore(
                    dimension="user_demand", score=demand_score,
                    source_agent="consumer_insight_agent", basis=f"痛点频率+动机标签 {demand_score:.1f}",
                ),
                DimensionScore(
                    dimension="ip_fit", score=ip_score,
                    source_agent="ip_strategy_agent", basis=f"IP 匹配热度 {ip_score:.1f}",
                ),
                DimensionScore(
                    dimension="competition", score=comp_score,
                    source_agent="business_evaluation_agent",
                    basis=f"品牌集中度 {len(brand_conc)} 个品牌归一化 {comp_score:.1f}",
                ),
                DimensionScore(
                    dimension="history_analog", score=hist_score,
                    source_agent="business_evaluation_agent", basis=f"爆款热度均值 {hist_score:.1f}",
                ),
            ]

            warnings = self._merge_warnings(
                trend_warnings, demand_warnings, ip_warnings,
                comp_warnings + comp_view_warnings, hist_warnings + hist_view_warnings,
            )
            total = round(sum(d.score * weight_map[d.dimension] for d in dims), 2)

            scores.append(
                OpportunityScore(
                    proposal_name=proposal["name"],
                    dimension_scores=dims,
                    weights_used=weights,
                    total_score=total,
                    star_rating=max(1, min(5, round(total / 20))),
                    risk_warnings=warnings,
                    upstream_confidence=base_conf,
                    evidence_refs=[EvidenceRef(**e) for e in evidence_refs],
                    caveats=caveats,
                    confidence=conf,
                ).model_dump(mode="json")
            )
        return {"opportunity_scores": scores}

    # ── View 读取（异常 → 空 + warning，不伪造） ──────────────────────────

    def _resolve_confidence(
        self,
        base: Confidence,
        view_failed: bool,
        brand_conc: dict[str, int],
        hit_products: list[dict[str, Any]],
    ) -> tuple[Confidence, list[str]]:
        """置信度收口：上游置信度为基础，商业维度证据链不完整时降级。

        - 数据源故障 → caveat + 降级；
        - 品牌集中度缺失 → caveat + 降级；
        - 历史爆款缺失 → caveat + 降级；
        - 仅有聚合数据（缺逐条来源）→ caveat + 降级。
        避免「数据不完整但置信度偏高」。
        """
        conf = base
        caveats: list[str] = []
        if view_failed:
            caveats.append("商业摘要数据源不可用，competition/history_analog 无依据")
        else:
            if not brand_conc:
                caveats.append("品牌集中度数据缺失，competition 无依据")
            if not hit_products:
                caveats.append("历史爆款数据缺失，history_analog 无依据")
            if brand_conc and hit_products:
                caveats.append("competition/history_analog 仅有聚合数据，缺少逐条来源链接")
        if base in (Confidence.HIGH, Confidence.MEDIUM):
            conf = Confidence.LOW
        return conf, caveats

    # ── 证据 / 风险汇总 ──────────────────────────

    def _collect_evidence(
        self,
        feature_matrix: dict[str, Any],
        user_sentiment: dict[str, Any],
        ip_assessment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """只聚合三官 Artifact 的真实证据引用，去重，不伪造 URL"""
        refs: list[dict[str, Any]] = []
        for artifact in (feature_matrix, user_sentiment, ip_assessment):
            for ref in artifact.get("evidence_refs") or []:
                if ref and ref not in refs:
                    refs.append(ref)
        return refs[:5]

    def _merge_warnings(self, *groups: list[str]) -> list[RiskWarning]:
        """把各维度的 warning 字符串映射为带 source_dimension 的 RiskWarning"""
        dims = ["trend_heat", "user_demand", "ip_fit", "competition", "history_analog"]
        warnings: list[RiskWarning] = []
        for dim, group in zip(dims, groups):
            for w in group:
                warnings.append(RiskWarning(risk=w, source_dimension=dim, severity="medium"))
        return warnings

def get_business_agent_class() -> type[BaseAgent]:
    """注册表切换：默认 MockBusinessAgent；设 BUSINESS_AGENT_PROVIDER=real 时返回真实实现"""
    provider = os.getenv("BUSINESS_AGENT_PROVIDER", "mock").strip().lower()
    if provider == "real":
        return BusinessEvaluationAgent
    return MockBusinessAgent

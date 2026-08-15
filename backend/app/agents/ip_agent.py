"""IPStrategyAgent — 真实 IP 官

基于 IPDataView（Scoped View）的 IP 聚合信号，确定性生成 IPAssessment。
只读 IP 类型数据（category="IP"）的聚合结果与证据引用；不读 BaseDataAdapter、
不读原始评论全文、不访问其他 Agent 的 View、不调用白名单外的数据源。

确定性规则（不编造 IP / 热度 / 授权风险 / 窗口期）：
- ip_ranking 仅来自真实 IP 信号（brand + heat_index 聚合）；
- heat_score 仅来自 heat_index（取该 IP 峰值热度）；
- lifecycle_stage / window_estimate / regional_fit / licensing_risk 缺数据时一律
  写 unknown / 待核验语义，绝不臆造；
- regional_fit 为必填 float 无法表达 unknown，采用确定性中性值 0.0 并配合
  rejected=True + reject_reason="区域适配数据缺失，待核验"（方案 C）。

数据不足 / 数据源故障时返回 confidence="unknown" 的合法产物，不回退 Mock。
"""

from __future__ import annotations

import os
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.mock_agents import MockIPAgent
from app.data.base_adapter import BaseProviderError, BaseUnavailable
from app.schemas import Confidence, EvidenceRef, IPAssessment, IPCandidate


class IPStrategyAgent(BaseAgent):
    """真实 IP 官：从 IPDataView 聚合 IP 信号生成 IPAssessment"""

    name = "ip_strategy_agent"
    description = "IP 策略：基于 IP 热度信号生成 IP 候选排序与授权风险声明"

    def __init__(self, config: dict | None = None, views: dict[str, Any] | None = None):
        super().__init__(config)
        self.views = views or {}

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        brief = context.get("brief", {})
        category = brief.get("category", "")
        market = brief.get("market", "")
        view = self.views.get("IPDataView")
        if view is None:
            return self._unknown(category, market, "无 IPDataView 权限")

        candidate_pool = brief.get("candidate_pool", []) or []
        try:
            result = view.get_ip_signals(candidates=candidate_pool)
        except BaseUnavailable:
            return self._unknown(category, market, "IP 数据源不可用（配置缺失或未接入）")
        except BaseProviderError:
            return self._unknown(category, market, "IP 数据源请求失败（网络/服务错误）")

        signals = result.get("signals", []) or []
        evidence = result.get("evidence", []) or []
        candidates = self._build_candidates(signals)
        evidence_refs = [EvidenceRef(**e) for e in evidence[:5]]

        if not candidates:
            return self._unknown(category, market, "无 IP 信号（无品牌或热度数据）")
        if not evidence_refs:
            # 有 IP 提及信号但无可引用链接 → 诚实降为 unknown，不产出 ip_ranking
            return self._unknown(category, market, "检测到 IP 提及信号，但缺少可引用的来源链接")

        return self._build(category, market, candidates, evidence_refs)

    # ── 数据不足 ──────────────────────────

    def _unknown(self, category: str, market: str, caveat: str) -> dict[str, Any]:
        """数据不足 → 合法 IPAssessment，confidence=unknown，ip_ranking 为空，不编造"""
        return IPAssessment(
            category=category,
            market=market,
            ip_ranking=[],
            licensing_risk="待核验",
            strategy_note="",
            evidence_refs=[],
            confidence=Confidence.UNKNOWN,
            caveats=[caveat],
        ).model_dump(mode="json")

    # ── 有数据 ──────────────────────────

    def _build(
        self,
        category: str,
        market: str,
        candidates: list[IPCandidate],
        evidence_refs: list[EvidenceRef],
    ) -> dict[str, Any]:
        return IPAssessment(
            category=category,
            market=market,
            ip_ranking=candidates,
            licensing_risk="待核验",
            strategy_note=(
                "IP 热度信号已识别，生命周期/区域适配/授权信息待核验，"
                "暂无法给出联名策略研判"
            ),
            evidence_refs=evidence_refs,
            confidence=Confidence.LOW,
            caveats=[
                "生命周期阶段无数据源，标注 unknown",
                "窗口期无历史同构曲线依据，标注待核验",
                "区域适配数据缺失，regional_fit 无依据，保守标记待核验",
                "授权信息缺失，licensing_risk 待核验",
            ],
        ).model_dump(mode="json")

    def _build_candidates(self, signals: list[dict[str, Any]]) -> list[IPCandidate]:
        """按 brand 聚合 IP 热度，生成候选（缺区域数据 → 确定性中性值 + rejected）"""
        brand_heat: dict[str, float] = {}
        for s in signals:
            brand = s.get("brand")
            heat = s.get("heat_index")
            if not brand or heat is None:
                continue
            brand_heat[brand] = max(brand_heat.get(brand, 0.0), float(heat))

        ranked = sorted(brand_heat.items(), key=lambda x: x[1], reverse=True)
        return [
            IPCandidate(
                ip_name=brand,
                heat_score=round(heat, 2),
                lifecycle_stage="unknown",
                window_estimate="待核验",
                regional_fit=0.0,
                rejected=True,
                reject_reason="区域适配数据缺失，待核验",
            )
            for brand, heat in ranked
        ]

def get_ip_agent_class() -> type[BaseAgent]:
    """注册表切换：默认 MockIPAgent（离线/确定/快）；
    设 IP_AGENT_PROVIDER=real 时返回真实 IPStrategyAgent。
    """
    provider = os.getenv("IP_AGENT_PROVIDER", "mock").strip().lower()
    if provider == "real":
        return IPStrategyAgent
    return MockIPAgent

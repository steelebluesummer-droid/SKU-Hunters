"""GoToMarketAgent — 真实 GTM（全球化）Agent

基于 brief 目标市场 + 上游商业/创意/IP 结果 + GTMMarketView 聚合信号，
确定性生成保守、可解释、证据约束的 GTMPlan。

纪律（不调用 LLM、不编造）：
- country 原样使用 brief.market，不扩展、不翻译、不推断；
- price_band 原样来自 proposal，不换算汇率、不改数字；
- 无真实排期数据时 batch=1 仅表「候选首批」，timing 固定「待核验」；
- 缺市场/节日/法规/渠道数据时不生成虚假上市计划，转 deferred + caveat；
- 不把品类热度解释成销量/接受度/节日机会/法规通过/渠道成功率；
- 不把 opportunity_score 高分直接等价为「应立即上市」。

数据权限：只读 self.views["GTMMarketView"]，不访问 BaseDataAdapter、其他 View、
未实现的 market_db/holiday_calendar connector。
"""

from __future__ import annotations

import os
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.mock_agents import MockGTMAgent
from app.data.base_adapter import BaseProviderError, BaseUnavailable
from app.engine.decision_engine import min_confidence
from app.schemas import Confidence, CountryPlan, EvidenceRef, GTMPlan


class GoToMarketAgent(BaseAgent):
    """真实 GTM：保守、确定性、证据约束的上市计划"""

    name = "go_to_market_agent"
    description = "GTM 全球化：基于 brief 市场与上游结果的保守上市计划"

    def __init__(self, config: dict | None = None, views: dict[str, Any] | None = None):
        super().__init__(config)
        self.views = views or {}

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        brief = context.get("brief", {})
        proposal_set = context.get("proposal_set", {})
        opportunity_scores = context.get("opportunity_scores") or []
        ip_assessment = context.get("ip_assessment", {})
        category = brief.get("category", "")
        market = brief.get("market", "") or ""

        view = self.views.get("GTMMarketView")
        signals, market_evidence, market_failed = self._get_market(view, category)

        score_map = {s.get("proposal_name"): s for s in opportunity_scores}

        plans = []
        for proposal in proposal_set.get("proposals", []):
            score = score_map.get(proposal.get("name"))
            plans.append(
                self._build_plan(
                    proposal, score, ip_assessment,
                    market, signals, market_evidence, market_failed,
                )
            )
        return {"gtm_plans": plans}

    # ── 市场信号读取（异常 → 空 + failed，不伪造） ──────────────────────────

    def _get_market(self, view: Any, category: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        if view is None:
            return [], [], True
        try:
            result = view.get_market_signals(category)
        except (BaseUnavailable, BaseProviderError):
            return [], [], True
        return (
            result.get("signals") or [],
            result.get("evidence") or [],
            False,
        )

    # ── 单方案 GTMPlan 构造 ──────────────────────────

    def _build_plan(
        self,
        proposal: dict[str, Any],
        score: dict[str, Any] | None,
        ip_assessment: dict[str, Any],
        market: str,
        signals: list[dict[str, Any]],
        market_evidence: list[dict[str, Any]],
        market_failed: bool,
    ) -> dict[str, Any]:
        name = proposal.get("name", "")
        licensing_risk = ip_assessment.get("licensing_risk", "")

        # 证据引用：只来自上游 Artifact / opportunity_score / GTMMarketView 真实引用
        evidence_refs = self._collect_evidence(score, ip_assessment, market_evidence)

        # caveats（覆盖数据缺口）
        caveats: list[str] = []
        if not market:
            caveats.append("缺少目标市场（brief.market 为空）")
        if market_failed:
            caveats.append("市场数据源不可用，无法形成市场依据")
        elif not signals:
            caveats.append("目标品类无市场参照数据")
        caveats.append("渠道/供应链数据未接入")
        if not market_evidence:
            caveats.append("仅有品类聚合数据，缺少逐条来源")
        else:
            caveats.append("缺少区域/节日/法规数据")
        caveats.append("目标市场由 brief 指定，尚未完成区域适配验证")
        if licensing_risk == "待核验":
            caveats.append("IP 授权状态待核验")

        # dependencies
        dependencies = "需核验：目标市场节日/法规/渠道/供应链信息"
        if licensing_risk == "待核验":
            dependencies += "；IP 授权状态"
        if score is None:
            dependencies += "；该方案缺少 opportunity_score"

        # 上游最低置信度（不放大）
        upstream_confs = [ip_assessment.get("confidence", "unknown")]
        if score is not None:
            upstream_confs.append(score.get("confidence", "unknown"))
        upstream_conf = min_confidence(upstream_confs)

        # 是否具备生成上市计划的条件
        can_plan = (
            bool(market)
            and not market_failed
            and bool(signals)
            and score is not None
        )

        # 置信度
        if not can_plan:
            conf = Confidence.UNKNOWN
        else:
            # 仅有品类聚合数据、无逐条来源 → 最多 low；上游 unknown 不升高
            conf = min_confidence([upstream_conf, Confidence.LOW])

        if can_plan:
            country_plans = [
                CountryPlan(
                    country=market,               # 原样 brief.market
                    batch=1,                      # 候选首批，非确认
                    price_band=proposal.get("price_band", ""),  # 原样 proposal
                    timing="待核验",              # 无真实排期数据
                    rationale="品类存在市场参照（聚合信号），区域适配待核验",
                )
            ]
            deferred_markets: list[str] = []
        else:
            country_plans = []
            deferred_markets = [market] if market else []

        localization_notes = ["本地化内容待核验（缺少区域语言/文化/法规数据）"]

        return GTMPlan(
            proposal_name=name,
            country_plans=country_plans,
            localization_notes=localization_notes,
            deferred_markets=deferred_markets,
            dependencies=dependencies,
            evidence_refs=[EvidenceRef(**e) for e in evidence_refs],
            confidence=conf,
            caveats=caveats,
        ).model_dump(mode="json")

    def _collect_evidence(
        self,
        score: dict[str, Any] | None,
        ip_assessment: dict[str, Any],
        market_evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """只聚合真实 EvidenceRef，去重，不伪造 URL"""
        refs: list[dict[str, Any]] = []
        sources: list[list[dict[str, Any]]] = [
            (score or {}).get("evidence_refs") or [],
            ip_assessment.get("evidence_refs") or [],
            market_evidence or [],
        ]
        for group in sources:
            for ref in group:
                if ref and ref not in refs:
                    refs.append(ref)
        return refs[:5]

def get_gtm_agent_class() -> type[BaseAgent]:
    """注册表切换：默认 MockGTMAgent；设 GTM_AGENT_PROVIDER=real 时返回真实实现"""
    provider = os.getenv("GTM_AGENT_PROVIDER", "mock").strip().lower()
    if provider == "real":
        return GoToMarketAgent
    return MockGTMAgent

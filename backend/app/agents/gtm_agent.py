"""GTMAgent — 真全球化官：市场声量接地 + LLM 上市策略

对应剧本 3.2：上市国家排序、分批计划、定价、本地化要点（112 国口径）。

接地数据源（按目标市场切换）：
  - 海外市场 → TikTok Creative Center 话题榜（get_trending_hashtags，
    112 国市场口径；国内网络受限属预期故障）
  - 国内市场（CN）→ 微博/百度热搜按品类词过滤

分工铁律：
  - LLM 出策略：国家排序/批次/时点/本地化要点/暂缓市场
  - 价格带以提案 price_band 为锚（代码传入，LLM 做当地货币表达）
  - EvidenceRef 只由代码从连接器返回构建

降级纪律（与其他真 Agent 有一个刻意差异）：
  - 数据源故障 **不回退 Mock**——LLM 仍可基于提案与 Brief 出策略，
    标 confidence=low + caveats 声明（GTM 节点不走证据铁律，合法输出；
    这样 Phase 2 占位官在真模式下始终有真产出）
  - 仅 LLM 未配置/输出不合 schema 才回退 MockGTMAgent
  - 注册表切换：默认 Mock，设 GTM_AGENT_PROVIDER=real（或总开关
    AGENT_PROVIDER=real）启用
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.mock_agents import MockGTMAgent
from app.agents.real_common import fuzzy_get, parse_llm_json, provider_enabled
from app.data.baidu_hot import BaiduHotConnector
from app.data.errors import ConnectorFetchError
from app.data.tiktok_trends import TiktokTrendsConnector
from app.data.weibo_hot import WeiboHotConnector
from app.schemas import Confidence, EvidenceRef, GTMPlan

_OUTPUT_CONTRACT = """
以上为角色与职责说明。本次请以「严格 JSON」输出（不要输出任何解释文字）：

{
  "plans": [
    {
      "proposal_name": "照抄「」内的方案名（不含其他任何文字）",
      "country_plans": [
        {
          "country": "国家/地区码，如 TH/JP/US",
          "batch": 1,
          "price_band": "当地货币价格带（以所给提案价格带为锚换算）",
          "timing": "上市时点，如 首批2周内",
          "rationale": "依据的区域适配证据（引用所给市场材料，或说明为经验判断）"
        }
      ],
      "localization_notes": ["本地化要点，如 日本需礼盒装"],
      "deferred_markets": ["建议暂缓的市场及原因"],
      "dependencies": "批次间依赖说明"
    }
  ]
}

要求：
1. 每个输入方案恰好一条，proposal_name 只照抄「」内的方案名
2. country_plans 1-3 个国家，按批次排序，batch 从 1 开始
3. rationale 优先引用所给市场材料；材料缺失时写清"经验判断"而不是编数据
"""


class GTMAgent(BaseAgent):
    """真全球化官：LLM 出上市策略，代码管证据与置信度，LLM 失败回退 Mock"""

    name = "go_to_market_agent"

    def __init__(
        self,
        tiktok: TiktokTrendsConnector | None = None,
        weibo: WeiboHotConnector | None = None,
        baidu: BaiduHotConnector | None = None,
    ):
        self.tiktok = tiktok or TiktokTrendsConnector(timeout=8)
        self.weibo = weibo or WeiboHotConnector(timeout=6)
        self.baidu = baidu or BaiduHotConnector(timeout=6)

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(self._generate, context)
            if result is not None:
                return result
        except Exception:  # noqa: BLE001,S110 — 降级纪律：LLM 故障回退 Mock
            pass
        return await MockGTMAgent().run(context)

    # ── 市场声量采集（故障返回 failed 标记，不抛）─────────────

    def _collect(self, market: str, filter_words: list[str]) -> dict[str, Any]:
        hits: list[dict[str, Any]] = []
        if market == "CN":
            for name, connector in (("weibo", self.weibo), ("baidu", self.baidu)):
                try:
                    hits += [
                        {"source": name, **item}
                        for item in connector.get_hot_search()
                        if any(w and w in item["word"] for w in filter_words)
                    ]
                except ConnectorFetchError:
                    pass  # 单源故障：继续用另一源
            source_label = "微博/百度热搜"
        else:
            try:
                hits = [
                    {"source": "tiktok", **item}
                    for item in self.tiktok.get_trending_hashtags(country_code=market)
                    if any(w and w.lower() in item["word"].lower() for w in filter_words)
                ]
            except ConnectorFetchError:
                pass  # 国内访问 TikTok 受限属预期故障
            source_label = f"TikTok 话题榜（{market}）"
        return {"hits": hits, "source_label": source_label}

    # ── 主流程 ─────────────────────────────────────────────

    def _generate(self, context: dict[str, Any]) -> dict[str, Any] | None:
        from app.engine.llm import complete, load_prompt

        brief = context.get("brief", {})
        category = brief.get("category", "潮玩")
        market = brief.get("market", "CN")
        proposals = context.get("proposal_set", {}).get("proposals", [])
        if not proposals:
            return None

        filter_words = [category]
        collected = self._collect(market, filter_words)
        hits, source_label = collected["hits"], collected["source_label"]
        data_available = bool(hits)

        # 材料：brief + 提案 + 市场声量
        material = [
            (f"【Brief】品类：{category}　目标市场：{market}　"
             f"预算带：{brief.get('budget_range', 'mid')}"),
            "",
            "【待规划方案】",
        ]
        for p in proposals:
            material.append(
                f"  · 方案「{p.get('name', '')}」：{p.get('concept', '')}"
                f"（形态 {p.get('product_form', '')}，"
                f"目标人群 {p.get('target_segment', '')}，"
                f"价格带锚点 {p.get('price_band', '')}）"
            )
        material.append(f"\n【市场声量材料】来源：{source_label}")
        if hits:
            for h in hits[:8]:
                material.append(f"  · {h['word']}（热度 {h['heat']}）")
        else:
            material.append("  （品类词未命中或数据源不可用——按经验判断出策略，"
                            "并在 rationale 中注明）")
        challenges = context.get("challenges", [])
        if challenges:
            material.append("\n【质询记录】")
            for c in challenges[:4]:
                material.append(f"  · {c.get('proposal_name', '')}："
                                f"{c.get('content', '')[:60]}")

        persona_prompt = load_prompt(self.name)
        system = (persona_prompt + "\n" + _OUTPUT_CONTRACT) if persona_prompt else _OUTPUT_CONTRACT
        raw = complete(system, "\n".join(material), temperature=0.3, max_tokens=100_000)
        if not raw:
            return None
        data = parse_llm_json(raw)
        if data is None:
            return None

        # 组装 + schema 强校验；证据代码构建
        evidence = [
            EvidenceRef(
                url=h.get("url") or "https://s.weibo.com/top/summary",
                title=f"{h['source']}：{h['word'][:30]}",
                snippet=f"目标市场声量命中，热度 {h['heat']}"[:200],
            )
            for h in hits[:3]
        ]
        confidence = Confidence.MEDIUM if data_available else Confidence.LOW
        caveats = [] if data_available else [
            f"{source_label} 品类词未命中或不可用，策略为经验判断（confidence=low）"
        ]

        llm_by_name = {str(p.get("proposal_name", "")): p for p in data.get("plans", [])}
        plans = []
        for p in proposals:
            name = p.get("name", "")
            plan = fuzzy_get(llm_by_name, name)
            if plan is None:
                return None  # 缺方案 → 整体回退
            country_plans = []
            for cp in plan.get("country_plans", [])[:3]:
                try:
                    batch = int(cp.get("batch", 1))
                except (TypeError, ValueError):
                    batch = 1
                country_plans.append({
                    "country": str(cp.get("country", market)),
                    "batch": max(1, batch),
                    "price_band": str(cp.get("price_band", "")).strip()
                    or str(p.get("price_band", "")),
                    "timing": str(cp.get("timing", "首批2周内")),
                    "rationale": str(cp.get("rationale", "")).strip() or "经验判断",
                })
            if not country_plans:
                return None
            plans.append(GTMPlan(
                proposal_name=name,
                country_plans=country_plans,
                localization_notes=[str(x) for x in plan.get("localization_notes", [])][:5],
                deferred_markets=[str(x) for x in plan.get("deferred_markets", [])][:5],
                dependencies=str(plan.get("dependencies", "")),
                evidence_refs=evidence,
                confidence=confidence,
                caveats=caveats,
            ).model_dump(mode="json"))

        return {"gtm_plans": plans}


def get_gtm_agent_class() -> type[BaseAgent]:
    """注册表切换：默认 MockGTMAgent（离线/确定/快）；
    GTM_AGENT_PROVIDER=real（或总开关 AGENT_PROVIDER=real）启用真 GTMAgent，
    LLM 故障时内部回退 Mock（数据源故障不回退，降置信度继续出策略）。
    """
    if provider_enabled("GTM_AGENT_PROVIDER"):
        return GTMAgent
    return MockGTMAgent

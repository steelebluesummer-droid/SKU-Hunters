"""趋势官 Agent — 基于真实 Google Trends 数据的趋势分析

最小可行闭环：真实数据进 → FeatureMatrix（带 EvidenceRef）出。
LLM 增强分析为可选层：无 API Key 时自动降级为规则引擎输出，
保证 Demo 任何环境下可运行。
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from ..data.google_trends import GoogleTrendsConnector
from ..schemas.evidence import EvidenceRef
from ..schemas.feature import FeatureMatrix, TrendItem
from .base_agent import BaseAgent


class TrendAgent(BaseAgent):
    """趋势官 — Trend Intelligence Agent"""

    name = "trend"
    description = "市场研究总监，负责全球消费趋势感知与预判"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.connector = GoogleTrendsConnector()
        self.llm_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行趋势分析

        context 输入:
            keywords: 候选关键词列表，如 ['Labubu', 'Chiikawa']
            category: 品类，如 '潮玩'
            geo: 目标市场地区代码，如 'TH'，空为全球

        输出: FeatureMatrix（含 evidence_refs）
        """
        keywords = context.get("keywords", [])
        category = context.get("category", "general")
        geo = context.get("geo", "")
        region_label = geo or "global"

        trend_items: list[TrendItem] = []
        evidence: list[EvidenceRef] = []

        for kw in keywords[:5]:  # Google Trends 单次最多5个关键词
            try:
                result = self.connector.compute_heat_index(kw, geo=geo)
            except Exception as e:
                # 单个关键词失败不阻塞整体，记录后继续
                evidence.append(EvidenceRef(
                    url=f"https://trends.google.com/trends/explore?q={kw}",
                    title=f"{kw} - 数据获取失败",
                    snippet=f"错误: {str(e)[:100]}",
                ))
                continue

            trend_items.append(TrendItem(
                keyword=kw,
                heat_index=result["heat_index"],
                platform="Google Trends",
                region=region_label,
                lifecycle=result["lifecycle"],
            ))

            evidence.append(EvidenceRef(
                url=f"https://trends.google.com/trends/explore?q={kw}&geo={geo}",
                title=f"Google Trends: {kw}",
                snippet=(
                    f"近7天热度均值 {result['level']}，"
                    f"环比增长 {result['growth']}%，"
                    f"关联上升查询 {result['breadth']} 个，"
                    f"生命周期: {result['lifecycle']}"
                ),
            ))

        trend_items.sort(key=lambda t: t.heat_index, reverse=True)
        summary = self._generate_summary(trend_items, category, region_label)

        matrix = FeatureMatrix(
            category=category,
            region=region_label,
            trends=trend_items,
            summary=summary,
            analysis_date=date.today().isoformat(),
            evidence_refs=evidence,
        )
        return matrix.model_dump()

    def _generate_summary(
        self, items: list[TrendItem], category: str, region: str
    ) -> str:
        """生成趋势摘要。有 LLM Key 时走模型，否则规则引擎兜底。"""
        if not items:
            return f"{category} 品类在 {region} 市场暂无有效趋势数据。"

        top = items[0]
        rising = [t for t in items if t.lifecycle == "rising"]

        rule_based = (
            f"{category} 品类趋势扫描（{region}）："
            f"当前最热关键词「{top.keyword}」（热度指数 {top.heat_index}，"
            f"{top.lifecycle} 阶段）。"
        )
        if rising:
            names = "、".join(t.keyword for t in rising)
            rule_based += f"处于上升期的关键词：{names}，建议优先关注。"
        else:
            rule_based += "暂无明确上升趋势信号，建议持续监控。"

        if self.llm_api_key:
            return self._llm_enhanced_summary(items, category, region, rule_based)
        return rule_based

    def _llm_enhanced_summary(
        self,
        items: list[TrendItem],
        category: str,
        region: str,
        fallback: str,
    ) -> str:
        """LLM 增强摘要，失败时降级为规则输出"""
        try:
            import openai

            client = openai.OpenAI()
            data_lines = "\n".join(
                f"- {t.keyword}: 热度{t.heat_index}, 生命周期{t.lifecycle}"
                for t in items
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是名创优品的市场研究总监。基于真实 Google Trends 数据，"
                            "用 100 字以内输出趋势研判，指出最值得关注的 1-2 个方向和理由。"
                            "禁止编造数据中不存在的数字。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"品类: {category}\n市场: {region}\n数据:\n{data_lines}",
                    },
                ],
                temperature=0.3,
            )
            return resp.choices[0].message.content or fallback
        except Exception:
            return fallback

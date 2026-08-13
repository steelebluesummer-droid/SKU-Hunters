"""五看洞察解析器（insight resolver）：按品类解析真实社媒证据，回退冻结 fixtures

职责边界：只负责「洞察数据从哪来」（真实证据 vs 冻结 fixture 的选择与组装），
不负责机会生成、企划卡等下游业务。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.planning import fixtures


def _resolve_insight_bundle(category: str) -> dict[str, Any]:
    """按品类取社媒真实证据；无对应数据回退冻结 fixtures（process_log 兼容）"""
    try:
        from app.insights.loaders.social_evidence import SocialEvidenceLoader
        bundle = SocialEvidenceLoader().get_insight_bundle(category)
        # heatCurve 无快照时回退 fixtures，保证契约完整（前端 ECharts 不因 None 崩溃）
        bundle["trendRadar"]["heatCurve"] = _load_heat_curve() or fixtures.TREND_RADAR.get("heatCurve")
        return bundle
    except FileNotFoundError:
        return {
            "trendRadar": fixtures.TREND_RADAR,
            "consumerVoice": fixtures.CONSUMER_VOICE,
            "competitiveMap": fixtures.COMPETITIVE_MAP,
            "insightBase": fixtures.INSIGHT_BASE,
            "trendGallery": fixtures.TREND_GALLERY,
        }


def _load_heat_curve() -> dict[str, Any] | None:
    """从 Google Trends 冻结快照注入热度曲线（存在才注入，否则前端留空）"""
    try:
        # 快照分目录：优先 data/snapshot/，旧路径向后兼容
        base = Path(__file__).resolve().parents[2] / "data"
        path = base / "snapshot" / "google_trends_snapshot.json"
        if not path.is_file():
            path = base / "google_trends_snapshot.json"
        if not path.is_file():
            return None
        snap = json.loads(path.read_text(encoding="utf-8"))
        return {"weeks": snap["weeks"], "series": snap["series"]}
    except (OSError, ValueError, KeyError):
        return None

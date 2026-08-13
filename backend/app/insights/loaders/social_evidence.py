"""
社媒证据注入器 — 把 OpenClaw 采集的 JSON 转成管线「五看洞察」的 camelCase 结构

采集 JSON 键名是 snake（见 docs/guides/openclaw-社媒采集prompt包.md），
管线洞察结构是 camelCase（见 fixtures.py 的 TREND_RADAR/CONSUMER_VOICE/...）。
本 loader 负责映射，产出可被 get_insights 直接消费的 dict。

用法：
    from app.insights.loaders.social_evidence import SocialEvidenceLoader
    loader = SocialEvidenceLoader()
    bundle = loader.get_insight_bundle("保温杯")   # 五看全量
    voice  = loader.to_consumer_voice("保温杯")    # 单模块
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EVIDENCE_ROOT = Path(__file__).resolve().parents[1] / "evidence_sources" / "social"


def _first_number(s: Any, default: float = 0.0) -> float:
    """从 '约80-120元'、'高频, 217条' 等字符串里提取首个数字"""
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return float(m.group()) if m else default


def _weight_value(w: Any) -> int:
    """场景权重 → 数值（高80/中50/低20），无则给0"""
    return {"高": 80, "中": 50, "低": 20, "high": 80, "mid": 50, "low": 20}.get(str(w), 0)


class SocialEvidenceLoader:
    """读取 social/ 目录下的采集 JSON，映射为管线五看结构（camelCase）"""

    def __init__(self, root: Path = EVIDENCE_ROOT):
        self.root = root
        self._cache: dict[str, dict[str, Any]] = {}

    def list_topics(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))

    def load(self, topic: str) -> dict[str, Any]:
        if topic in self._cache:
            return self._cache[topic]
        # 文件名形如「{品类}_{日期}.json」，按品类前缀匹配，避免写死日期
        path = self.root / f"{topic}.json"
        if not path.is_file():
            cands = sorted(self.root.glob(f"{topic}_*.json"))
            path = cands[0] if cands else path
        if not path.is_file():
            raise FileNotFoundError(f"未找到社媒证据：{topic}（目录 {self.root}）")
        with open(path, encoding="utf-8") as f:
            self._cache[topic] = json.load(f)
        return self._cache[topic]

    # ── ① 趋势信号 ────────────────────────────────────────
    def to_trend_radar(self, topic: str) -> dict[str, Any]:
        d = self.load(topic)
        signals = [
            {
                "name": s["name"],
                "metric": s["metric"],
                "period": s["period"],
                "domains": s.get("domains", []),
                "opportunity": s.get("opportunity", ""),
            }
            for s in d.get("trend_signals", [])
        ]
        return {
            "processLog": [f"加载 {topic} 社媒证据，识别趋势信号 {len(signals)} 条"],
            "signals": signals,
            "hotWords": d.get("hot_words", []),
            "heatCurve": None,  # 热度曲线来自 Google Trends 线，另行注入
        }

    # ── ② 消费者之声 ──────────────────────────────────────
    def to_consumer_voice(self, topic: str) -> dict[str, Any]:
        raw = self.load(topic)
        d = raw.get("consumer_voice")
        # 兼容「voice 全量原声」格式（键为 voice_of_user，见小风扇voice 文件）
        if d is None and raw.get("voice_of_user"):
            d = self._voice_of_user_to_consumer(raw)
        d = d or {}
        return {
            "processLog": [f"加载 {topic} 社媒评论样本，情感与痛点聚类"],
            "painPoints": [
                {"text": p["text"], "count": int(_first_number(p.get("count", 0), 0))}
                for p in d.get("pain_points", [])
            ],
            "scenes": [
                {"name": s["scene"], "value": _weight_value(s.get("weight", 0))}
                for s in d.get("scenes", [])
            ],
            "quotes": [
                {"text": q["text"], "source": q.get("source", "")}
                for q in d.get("quotes", [])
            ],
            "summary": d.get("summary", ""),
        }

    @staticmethod
    def _voice_of_user_to_consumer(raw: dict[str, Any]) -> dict[str, Any]:
        """把 voice_of_user（speaker/raw_quote/scenario/sentiment）转成 ConsumerVoice 结构"""
        items = raw.get("voice_of_user", [])
        quotes = [
            {
                "text": q["raw_quote"],
                "source": f"{q.get('speaker', '')} · {q.get('source_note', '')}",
            }
            for q in items
        ]
        # 痛点：负面情绪的原声，按类别合并
        pain_map: dict[str, int] = {}
        for q in items:
            if q.get("sentiment") == "negative":
                cat = str(q.get("category", "用户痛点"))
                pain_map[cat] = pain_map.get(cat, 0) + 1
        pain_points = [{"text": c, "count": n} for c, n in pain_map.items()]
        # 场景：从 scenario 聚合
        scene_count: dict[str, int] = {}
        for q in items:
            sc = str(q.get("scenario", "其他"))
            scene_count[sc] = scene_count.get(sc, 0) + 1
        # 场景：从 scenario 聚合；出现次数≥2 记为高，否则为中（供外层映射算 value）
        scenes = [
            {"scene": s, "weight": "高" if c >= 2 else "中"}
            for s, c in scene_count.items()
        ]
        return {
            "pain_points": pain_points,
            "scenes": scenes,
            "quotes": quotes,
            "summary": raw.get("note", ""),
        }

    # ── ③ 竞争地图 ────────────────────────────────────────
    def to_competitive_map(self, topic: str) -> dict[str, Any]:
        d = self.load(topic).get("competitive_map", {})
        products = [
            {
                "name": p["name"],
                "price": _first_number(p.get("price", 0)),
                "design": _first_number(p.get("design", 5)),
                "image_url": p.get("image_url", ""),
                "selling_point": p.get("selling_point", ""),
            }
            for p in d.get("products", [])
        ]
        gap = d.get("gap_zone", "")
        return {
            "processLog": [f"加载 {topic} 竞品样本，构建价格×设计感矩阵"],
            "products": products,
            # 采集侧未给坐标，x/y 置空；前端展示 label，坐标为 0 不影响文字
            "gapZone": {"x": [], "y": [], "label": gap} if gap else None,
            "priceBands": [
                {"band": b.get("band", ""), "pct": int(_first_number(b.get("pct", 0), 0))}
                for b in d.get("price_bands", [])
            ],
            "sellingPoints": [
                {"word": s, "count": 0} for s in d.get("selling_points", [])
            ],
        }

    # ── ④ 爆款 & 名创资产 ─────────────────────────────────
    def to_insight_base(self, topic: str) -> dict[str, Any]:
        d = self.load(topic).get("insight_base", {})
        return {
            "processLog": [f"加载 {topic} 爆款案例与可联名 IP 池"],
            "hitProducts": [
                {
                    "name": p.get("title", ""),
                    # HitProduct.index 上限 100，metric 里的销量/点赞数字需钳制
                    "index": min(int(_first_number(p.get("metric", 0), 0)), 100),
                    "factors": [],
                    "note": p.get("metric", ""),
                }
                for p in d.get("hit_products", [])
            ],
            "ipPool": [
                {"name": i.get("ip", ""), "status": "待评估",
                 "heat": "—", "fit": [i.get("why", "")]}
                for i in d.get("ip_pool", [])
            ],
            "designLanguage": d.get("design_language", []),
        }

    # ── ⑤ 流行元素板 ──────────────────────────────────────
    def to_trend_gallery(self, topic: str) -> dict[str, Any]:
        d = self.load(topic).get("trend_gallery", {})
        return {
            "processLog": [f"加载 {topic} 当季流行设计元素"],
            "colors": [{"name": c, "hex": "", "source": ""} for c in d.get("colors", [])],
            "patterns": [{"name": p, "source": "", "note": ""} for p in d.get("patterns", [])],
            "shapes": [{"name": s, "source": "", "note": ""} for s in d.get("shapes", [])],
            "expressions": [{"name": e, "emoji": "", "note": ""} for e in d.get("expressions", [])],
        }

    # ── 五看全量 ───────────────────────────────────────────
    def get_insight_bundle(self, topic: str) -> dict[str, Any]:
        """返回与 pipeline get_insights 同构的五看洞察 dict（camelCase）"""
        return {
            "trendRadar": self.to_trend_radar(topic),
            "consumerVoice": self.to_consumer_voice(topic),
            "competitiveMap": self.to_competitive_map(topic),
            "insightBase": self.to_insight_base(topic),
            "trendGallery": self.to_trend_gallery(topic),
        }

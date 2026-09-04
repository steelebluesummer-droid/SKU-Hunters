"""Scoped Views — Agent 数据权限视图（只读）+ 独立写入端口

每个 View 持有受限查询端口（RestrictedQueryPort / BaseQueryPort），不持有完整
BaseDataAdapter；View 只暴露权限范围内的方法，且聚合方法一律翻页取全量（避免只统计
默认 page_size=20 的第一页）。
- 创意官（product_ideation）不注入任何数据视图，只接收三官 Artifact。
- LearningLedgerReadView 只读，写入走独立 RetroLedgerWriter（内存测试实现）。
- 权限范围（谁能看什么）见各 View docstring，并写入测试。

隔离边界说明：这是「应用层能力隔离」——View 依赖受限查询端口协议，公共接口不含
adapter 管理方法；但 Python 反射可绕过，非进程级安全边界。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data.base_adapter import BaseProviderError, BaseQueryPort, BaseUnavailable

# ── 竞品图片本地化：外链图床（淘宝/京东 CDN）有防盗链，前端 <img> 加载不可靠 ──
# data/evidence/images/competitors_url_map.json 维护「外链 URL → 本地文件名」映射；
# 命中映射则改写为 /evidence/competitors/<file>（由后端静态目录服务）；未命中保留原链。
_URL_MAP_PATH = Path(__file__).resolve().parents[2] / "data" / "evidence" / "images" / "competitors_url_map.json"


def _localize_image_url(url: str | None) -> str | None:
    """外链竞品图 → 本地路径；未命中映射返回原值（不伪造、不丢数据）"""
    if not url:
        return url
    try:
        with open(_URL_MAP_PATH, encoding="utf-8") as _f:
            mapping = json.load(_f)
        fname = mapping.get(url)
        return f"/evidence/competitors/{fname}" if fname else url
    except (OSError, ValueError):
        return url


class _ReadView:
    """只读 View 基类：持有受限查询端口（BaseQueryPort），不持有完整 adapter"""

    def __init__(self, port: BaseQueryPort):
        self._port = port

class TrendDataView(_ReadView):
    """趋势数据视图 — 权限：趋势信号 / 日期分布 / 热度 / 证据引用"""

    def search_trend_signals(self, keyword: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all(keyword, as_of=as_of, snapshot_id=snapshot_id)
        return [
            {"keyword": r.keyword, "platform": r.platform,
             "heat_index": r.heat_index, "record_date": r.record_date}
            for r in records
        ]

    def get_date_distribution(self, keyword: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        return self._port.get_date_distribution(keyword, as_of, snapshot_id)

    def compute_heat_index(self, keyword: str, as_of: str | None = None, snapshot_id: str | None = None) -> float | None:
        return self._port.compute_heat_index(keyword, as_of, snapshot_id)

    def build_evidence_refs(self, records: list[Any]) -> list[dict[str, str]]:
        return self._port.build_evidence_refs(records)

class ConsumerDataView(_ReadView):
    """消费者数据视图 — 权限：分类评论 / 搜索意图 / 证据引用"""

    def get_reviews_by_category(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        return [
            {"summary": r.summary, "platform": r.platform, "record_date": r.record_date}
            for r in records
        ]

    def get_search_intent(self, keyword: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all(keyword, platform="taobao", as_of=as_of, snapshot_id=snapshot_id)
        return [{"keyword": r.keyword, "summary": r.summary} for r in records]

    def get_category_signals(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, Any]:
        """按品类返回聚合信号 + 证据引用（不返回原始评论全文；source_url 缺失不伪造）"""
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        signals = [
            {"keyword": r.keyword, "summary": r.summary, "platform": r.platform,
             "heat_index": r.heat_index, "interaction": r.interaction}
            for r in records
        ]
        evidence = self._port.build_evidence_refs(records)
        return {"signals": signals, "evidence": evidence}

    def build_evidence_refs(self, records: list[Any]) -> list[dict[str, str]]:
        return self._port.build_evidence_refs(records)

class IPDataView(_ReadView):
    """IP 数据视图 — 权限：IP 提及 / 品牌 top20 / 联名案例 / 证据引用（无用户评论原文）"""

    def search_ip_mentions(self, keyword: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all(keyword, category="IP", as_of=as_of, snapshot_id=snapshot_id)
        return [
            {"keyword": r.keyword, "brand": r.brand, "heat_index": r.heat_index}
            for r in records
        ]

    def get_brand_top20(self, as_of: str | None = None, snapshot_id: str | None = None) -> list[tuple[str, float]]:
        records = self._port.search_all("", as_of=as_of, snapshot_id=snapshot_id)
        brand_heat: dict[str, float] = {}
        for r in records:
            if r.brand:
                brand_heat[r.brand] = brand_heat.get(r.brand, 0.0) + (r.heat_index or 0.0)
        return sorted(brand_heat.items(), key=lambda x: x[1], reverse=True)[:20]

    def get_hit_cases(self, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all("", category="IP", as_of=as_of, snapshot_id=snapshot_id)
        return [{"brand": r.brand, "summary": r.summary} for r in records if r.brand]

    def get_ip_signals(self, candidates: list[str] | None = None, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, Any]:
        """返回 IP 聚合信号 + 证据引用。

        只读取 IP 类型数据（category="IP"），不把普通品类热度伪装成 IP 授权结论；
        不返回原始评论全文；source_url 缺失不伪造。

        candidates 非空：只返回候选池中的 IP（按 brand 匹配）；
        candidates 为空/None：显式返回全库 Top IP（非隐含“空 keyword 不过滤”行为）。
        """
        records = self._port.search_all("", category="IP", as_of=as_of, snapshot_id=snapshot_id)
        if candidates:
            candidate_set = set(candidates)
            records = [r for r in records if r.brand in candidate_set]
        signals = [
            {"keyword": r.keyword, "brand": r.brand, "heat_index": r.heat_index,
             "summary": r.summary, "platform": r.platform, "record_date": r.record_date}
            for r in records
        ]
        evidence = self._port.build_evidence_refs(records)
        return {"signals": signals, "evidence": evidence}

    def build_evidence_refs(self, records: list[Any]) -> list[dict[str, str]]:
        return self._port.build_evidence_refs(records)

class BusinessSummaryView(_ReadView):
    """商业摘要视图 — 权限：品牌集中度 / 价格带分布 / 爆款（聚合结果，无原始评论）"""

    def get_brand_concentration(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, int]:
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        brand_count: dict[str, int] = {}
        for r in records:
            if r.brand:
                brand_count[r.brand] = brand_count.get(r.brand, 0) + 1
        return brand_count

    def get_price_band_distribution(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, int]:
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        bands: dict[str, int] = {}
        for r in records:
            if r.price_range:
                bands[r.price_range] = bands.get(r.price_range, 0) + 1
        return bands

    def get_hit_products(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        return [
            {"keyword": r.keyword, "brand": r.brand, "heat_index": r.heat_index}
            for r in records if r.heat_index is not None
        ]

class GTMMarketView(_ReadView):
    """GTM 市场视图 — 权限：品类分布 / 市场参照"""

    def get_category_distribution(self, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, int]:
        records = self._port.search_all("", as_of=as_of, snapshot_id=snapshot_id)
        cat_count: dict[str, int] = {}
        for r in records:
            cat_count[r.category] = cat_count.get(r.category, 0) + 1
        return cat_count

    def get_market_reference(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        return [
            {"keyword": r.keyword, "platform": r.platform, "heat_index": r.heat_index}
            for r in records
        ]

    def get_market_signals(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, Any]:
        """返回品类市场聚合信号 + 证据引用（不返回原始评论全文；source_url 缺失不伪造）"""
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        signals = [
            {"keyword": r.keyword, "platform": r.platform, "heat_index": r.heat_index,
             "record_date": r.record_date, "brand": r.brand}
            for r in records
        ]
        evidence = self._port.build_evidence_refs(records)
        return {"signals": signals, "evidence": evidence}

class LearningLedgerReadView(_ReadView):
    """学习台账只读视图 — 权限：决策记录 / 历史评分 / 结果信号（只读，不含写入方法）"""

    def get_decision_record(self, snapshot_id: str) -> dict[str, Any]:
        return self._port.get_summary(snapshot_id=snapshot_id)

    def get_historical_scores(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, Any]:
        summary = self._port.get_summary(category=category, as_of=as_of, snapshot_id=snapshot_id)
        return {"category": category, "avg_heat_index": summary.get("avg_heat_index", 0.0)}

    def get_outcome_signals(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        records = self._port.search_all("", category=category, as_of=as_of, snapshot_id=snapshot_id)
        return [
            {"keyword": r.keyword, "heat_index": r.heat_index, "record_date": r.record_date}
            for r in records if r.heat_index is not None
        ]

class RetroLedgerWriter:
    """复盘台账写入端口（独立，只追加复盘记录，不读取、不覆盖）

    注意：当前为内存测试实现（list），未接入任何持久化存储。仅用于验证「写入端口」
    与只读 View 的权限分离；生产环境需替换为真实持久化后端（如飞书 Base / SQLite）。
    """

    def __init__(self, ledger: list[dict[str, Any]] | None = None):
        self._ledger = ledger if ledger is not None else []

    def append_retro_entry(self, session_id: str, question: str, answer: str, timestamp: str | None = None) -> dict[str, Any]:
        entry = {
            "session_id": session_id,
            "question": question,
            "answer": answer,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        }
        self._ledger.append(entry)
        return entry


class CompetitorDataView(_ReadView):
    """竞品数据视图 — 只读商品级竞品表（base_competitors）

    权限：只暴露竞品表查询与确定性聚合；不暴露 BaseDataAdapter / Feishu provider、
    不访问其他 View、不调用 LLM、不生成缺失数据。

    get_competitor_map 返回：
    - products: 商品级真实记录（product_name/brand/price/selling_points/source_url/verification_status/designScore…）
    - price_bands: 真实 price_band 或由合法 price 分桶
    - selling_points: 真实结构化卖点 word 频次
    - brands: 真实 brand 频次
    - evidence_refs: 真实 source_url 证据引用
    - gap_zone: 仅当有合法 design_score + price + 足够样本 + 明确规则时计算；否则 None + caveat
    - caveats: 计算层面的说明（如样本不足、竞品表不可用）
    """

    _MIN_GAP_SAMPLES = 5  # 设计评分+价格有效样本下限，不足不计算竞品空白区

    def get_competitor_map(self, category: str, as_of: str | None = None, snapshot_id: str | None = None) -> dict[str, Any]:
        caveats: list[dict[str, Any]] = []
        try:
            records = self._port.get_competitor_records(category=category, snapshot_id=snapshot_id, as_of=as_of)
        except (BaseUnavailable, BaseProviderError) as e:
            # 竞品表不可用（未配置/网络/HTTP/权限）→ fail-closed，不返回 500、不伪造、不调用 LLM
            return {
                "products": [], "record_count": 0, "product_count": 0, "skipped_count": 0,
                "price_bands": [], "selling_points": [], "brands": [], "evidence_refs": [],
                "gap_zone": None, "snapshot_id": None,
                "caveats": [{"source": "competitors", "reason": f"竞品表不可用：{e!s}"}],
            }
        products, skipped_count = self._build_products(records)
        if skipped_count:
            caveats.append({"source": "competitors", "reason": f"{skipped_count} 条商品缺少价格，未进入商品卡"})
        gap_zone, gap_caveat = self._build_gap_zone(records)
        if gap_caveat:
            caveats.append(gap_caveat)
        return {
            "products": products,
            "record_count": len(records),
            "product_count": len(products),
            "skipped_count": skipped_count,
            "snapshot_id": (records[0].snapshot_id if records else None),
            "price_bands": self._build_price_bands(records),
            "selling_points": self._build_selling_points(records),
            "brands": self._build_brands(records),
            "evidence_refs": self._build_evidence_refs(records),
            "gap_zone": gap_zone,
            "caveats": caveats,
        }

    # ── 确定性计算（不伪造、不估算、不调 LLM）────────────────

    def _build_products(self, records: list[Any]) -> tuple[list[dict[str, Any]], int]:
        """商品卡构建：只保留 price 或 price_min 合法非负数字的商品；缺价格跳过（不补 0、不编造）。

        返回 (products, skipped_count)。返回的商品卡 price 必为合法数字。
        """
        products = []
        skipped = 0
        for r in records:
            price = r.price
            if price is None and r.price_min is not None:
                price = r.price_min
            if price is None or price < 0:
                skipped += 1
                continue
            products.append({
                "name": r.product_name,
                "brand": r.brand,
                "price": price,
                "priceMin": r.price_min,
                "priceMax": r.price_max,
                "priceBand": r.price_band,
                "imageUrl": _localize_image_url(r.image_url),
                "sellingPoints": list(r.selling_points or []),
                "designScore": r.design_score,
                "sourceUrl": r.source_url,
                "sourcePlatform": r.source_platform,
                "verificationStatus": r.verification_status.value,
                "evidenceQuote": r.evidence_quote,
            })
        products.sort(key=lambda p: (p["price"] is None, p["price"] or 0))
        return products, skipped

    def _build_price_bands(self, records: list[Any]) -> list[dict[str, Any]]:
        """优先真实 price_band；缺失时由合法 price 分桶；无合法价格跳过"""
        bands: Counter[str] = Counter()
        for r in records:
            if r.price_band:
                bands[r.price_band] += 1
            elif r.price is not None:
                bands[self._price_to_band(r.price)] += 1
        total = sum(bands.values())
        if not total:
            return []
        return [{"band": b, "count": c, "pct": round(c / total * 100, 1)} for b, c in bands.most_common()]

    @staticmethod
    def _price_to_band(price: float) -> str:
        """确定性价格分桶（元）"""
        if price < 30:
            return "0-30"
        if price < 60:
            return "30-60"
        if price < 100:
            return "60-100"
        return "100+"

    def _build_selling_points(self, records: list[Any]) -> list[dict[str, Any]]:
        """只统计 selling_points JSON 中真实存在的 word；无结构化卖点返回空"""
        counter: Counter[str] = Counter()
        for r in records:
            for word in (r.selling_points or []):
                counter[word] += 1
        return [{"word": w, "count": c} for w, c in counter.most_common()]

    def _build_brands(self, records: list[Any]) -> list[dict[str, Any]]:
        """统计真实 brand；空品牌跳过（不把 keyword 当 brand）"""
        counter: Counter[str] = Counter()
        for r in records:
            if r.brand:
                counter[r.brand] += 1
        return [{"brand": b, "count": c} for b, c in counter.most_common()]

    def _build_evidence_refs(self, records: list[Any]) -> list[dict[str, str]]:
        refs = []
        for r in records:
            if r.source_url:
                refs.append({"url": r.source_url, "title": r.product_name,
                             "snippet": (r.evidence_quote or "")[:200]})
        return refs

    def _build_gap_zone(self, records: list[Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """竞品空白区：仅当有合法 design_score + price + 足够样本 + 明确规则时计算。

        规则（确定性）：以价格中位数 P50、设计评分中位数 D50 划分四象限，
        样本最稀少的象限作为机会区；样本不足 _MIN_GAP_SAMPLES → None + caveat。
        """
        valid = [(r.price, r.design_score) for r in records
                 if r.price is not None and r.design_score is not None]
        if len(valid) < self._MIN_GAP_SAMPLES:
            return None, {"source": "competitors", "reason": "设计评分或价格样本不足，暂不计算竞品空白区"}
        prices = sorted(v[0] for v in valid)
        designs = sorted(v[1] for v in valid)
        p50 = prices[len(prices) // 2]
        d50 = designs[len(designs) // 2]
        quads: Counter[str] = Counter()
        for price, design in valid:
            quads[("H" if price >= p50 else "L") + ("H" if design >= d50 else "L")] += 1
        sparse = min(quads, key=quads.get)
        p_lo, p_hi = min(prices), max(prices)
        d_lo, d_hi = min(designs), max(designs)
        if sparse == "LL":
            x, y = [p_lo, p50], [d_lo, d50]
            label = "低价格 × 低设计机会"
        elif sparse == "HL":
            x, y = [p50, p_hi], [d_lo, d50]
            label = "高价格 × 低设计（改进空间）"
        elif sparse == "LH":
            x, y = [p_lo, p50], [d50, d_hi]
            label = "低价格 × 高设计（性价比机会）"
        else:  # HH
            x, y = [p50, p_hi], [d50, d_hi]
            label = "高价格 × 高设计机会"
        return {"x": [round(x[0], 1), round(x[1], 1)], "y": [round(y[0], 1), round(y[1], 1)], "label": label}, None

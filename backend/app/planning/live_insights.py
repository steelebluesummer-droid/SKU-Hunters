"""基于 Feishu Base 明细生成不带猜测的实时洞察结构。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any

from app.data.base_adapter import BaseDataAdapter
from app.schemas.base_data import BaseRecord


def _matches_category(record: BaseRecord, category: str) -> bool:
    target = (category or "").strip().lower()
    if not target:
        return True
    values = (record.category, record.keyword)
    return any(target in (value or "").lower() or (value or "").lower() in target for value in values)

def _records_for_category(adapter: BaseDataAdapter, category: str) -> list[BaseRecord]:
    exact = adapter.search_all("", category=category)
    if exact:
        return exact
    return [record for record in adapter.search_all("") if _matches_category(record, category)]

def _price(value: str | None) -> float:
    match = re.search(r"\d+(?:\.\d+)?", value or "")
    return float(match.group()) if match else 0.0

def _price_bands(records: list[BaseRecord]) -> list[dict[str, Any]]:
    labels = ("0-50元", "50-100元", "100-150元", "150元以上")
    counts = Counter()
    for record in records:
        price = _price(record.price_range)
        if price <= 0:
            continue
        counts["0-50元" if price < 50 else "50-100元" if price < 100 else "100-150元" if price < 150 else "150元以上"] += 1
    total = sum(counts.values())
    if not total:
        return []
    return [{"band": label, "pct": round(counts[label] / total * 100, 1)} for label in labels]

def build_live_insight_bundle(
    category: str,
    brief: dict[str, Any] | None = None,
    adapter: BaseDataAdapter | None = None,
) -> dict[str, Any]:
    """从 Feishu Base 生成五看洞察；未接入的字段保持空值。"""
    source = adapter or BaseDataAdapter()
    records = _records_for_category(source, category)
    if not records:
        raise ValueError(f"Feishu Base 没有匹配品类：{category}")

    evidence = source.build_evidence_refs(records)
    dates = sorted(record.record_date for record in records)
    weeks: dict[str, list[float]] = defaultdict(list)
    platform_heats: dict[str, list[float]] = defaultdict(list)
    keyword_counts: Counter[str] = Counter()
    for record in records:
        current = date.fromisoformat(record.record_date)
        iso = current.isocalendar()
        weeks[f"{iso.year}-W{iso.week:02d}"].append(record.heat_index or 0)
        platform_heats[record.platform.value].append(record.heat_index or 0)
        keyword_counts[record.keyword] += 1

    week_labels = sorted(weeks)
    trend_signals = []
    for platform, heats in sorted(platform_heats.items(), key=lambda item: sum(item[1]), reverse=True):
        label = {"xiaohongshu": "小红书", "tiktok": "TikTok", "bilibili": "B站", "taobao": "淘宝"}.get(platform, platform)
        trend_signals.append({
            "name": f"{label}采集热度",
            "metric": f"{len(heats)} 条记录，平均归一化热度 {sum(heats) / len(heats):.1f}",
            "period": f"{dates[0]} 至 {dates[-1]}",
            "domains": [category],
            "opportunity": "基于真实采集记录，待人工结合内容摘要判断机会",
        })

    top_records = sorted(records, key=lambda record: record.heat_index or 0, reverse=True)
    quotes = [
        {"text": record.summary, "source": record.source_url}
        for record in top_records
        if record.summary and record.source_url
    ][:5]
    products = [
        {
            "name": record.keyword,
            "price": _price(record.price_range),
            "imageUrl": "",
            "sellingPoint": record.summary[:80] if record.summary else "",
            "design": 0,
        }
        for record in top_records[:8]
    ]
    hit_products = [
        {
            "name": record.keyword,
            "index": round(record.heat_index or 0, 2),
            "factors": [record.platform.value],
            "note": record.source_url or "飞书 Base 记录（无来源链接）",
        }
        for record in top_records[:4]
    ]
    ip_records = sorted(
        [record for record in source.search_all("") if record.category == "IP"],
        key=lambda record: record.heat_index or 0,
        reverse=True,
    )[:5]

    snapshot_ids = sorted({record.snapshot_id for record in records if record.snapshot_id})
    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "trendRadar": {
            "processLog": [
                "数据源：飞书 Base 实时明细",
                f"读取 {len(records)} 条匹配「{category}」的采集记录",
                "热度由 BaseRecord.heat_index 聚合，未接入字段不做推断",
            ],
            "signals": trend_signals[:5],
            "heatCurve": {
                "weeks": week_labels,
                "series": [{"name": category, "data": [round(sum(weeks[week]) / len(weeks[week]), 2) for week in week_labels]}],
            },
            "hotWords": [word for word, _ in keyword_counts.most_common(10)],
        },
        "consumerVoice": {
            "processLog": [
                "数据源：飞书 Base 实时明细",
                "Base 当前未提供情感/痛点结构化字段，painPoints 与 scenes 保持空值",
            ],
            "painPoints": [],
            "scenes": [],
            "quotes": quotes,
            "summary": "当前仅展示真实摘要；情感、痛点和场景字段尚未接入。",
        },
        "competitiveMap": {
            "processLog": [
                "数据源：飞书 Base 实时明细",
                "价格带按真实 price_range 统计；设计评分字段尚未接入，统一保持 0",
            ],
            "products": products,
            "gapZone": None,
            "priceBands": _price_bands(records),
            "sellingPoints": [],
        },
        "insightBase": {
            "hitProducts": hit_products,
            "ipPool": [
                {"name": record.brand or record.keyword, "status": "待核验", "heat": str(round(record.heat_index or 0, 2)), "fit": []}
                for record in ip_records
            ],
            "designLanguage": [],
        },
        "trendGallery": {
            "colors": [],
            "patterns": [],
            "shapes": [],
            "expressions": [],
        },
        "dataSource": "feishu",
        "sourceLabel": "飞书 Base · SKU-Hunters 采集数据",
        "evidenceCount": len(evidence),
        "recordCount": len(records),
        "generatedAt": generated_at,
        "dataContext": {
            "data_source": "feishu",
            "snapshot_id": snapshot_ids[-1] if snapshot_ids else "",
            "ingestion_run_id": snapshot_ids[-1] if snapshot_ids else "",
            "record_count": len(records),
            "evidence_count": len(evidence),
            "generated_at": generated_at,
        },
    }

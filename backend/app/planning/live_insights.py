"""基于 Feishu Base 明细生成不带猜测的实时洞察结构。"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any

from app.data.base_adapter import (
    BaseDataAdapter,
    BaseProviderError,
    BaseUnavailable,
    RestrictedQueryPort,
    category_matches,
    normalize_category,
)
from app.data.scoped_views import CompetitorDataView
from app.schemas.base_data import BaseRecord

_LIVE_LOG = logging.getLogger("insights.timing")


def _log_live_node(node, duration_ms, status, data_source="feishu", snapshot_id=None, cache_hit=False):
    """结构化耗时日志（不含 token/app_secret/原始完整记录）"""
    _LIVE_LOG.info(json.dumps({
        "event": "insight_node",
        "node": node,
        "duration_ms": round(duration_ms, 1),
        "status": status,
        "data_source": data_source,
        "snapshot_id": snapshot_id,
        "cache_hit": cache_hit,
    }, ensure_ascii=False))


def _matches_category(record: BaseRecord, category: str) -> bool:
    target = (category or "").strip().lower()
    if not target:
        return True
    # 父品类：明细 category 按子串规则匹配（如「风扇」匹配所有含「扇」子品类）
    if category_matches(record.category, category):
        return True
    values = (record.keyword,)
    return any(target in (value or "").lower() or (value or "").lower() in target for value in values)

def _records_for_category(adapter: BaseDataAdapter, category: str) -> list[BaseRecord]:
    exact = adapter.search_all("", category=category)
    if exact:
        return exact
    return [record for record in adapter.search_all("") if _matches_category(record, category)]

def _normalize_pain_points(raw: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """汇总表 pain_points → 前端契约 [{"text": str, "count": int}]

    再次过滤非法条目：仅接受 list；每项须 dict；text 非空字符串；count 可转非负数。
    count 作为计数必须是整数值（如 417.0 可、26.5 不可）；非整数计数跳过并记录 caveat。
    保证前端永远拿到 list[dict]，不伪造、不抛异常。返回 (结果, caveats)。
    """
    if not isinstance(raw, list):
        return [], []
    out: list[dict[str, Any]] = []
    caveats: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        text = raw_text.strip()
        if not text:
            continue
        count = item.get("count")
        if count is None:
            continue
        try:
            count_f = float(count)
        except (ValueError, TypeError):
            continue
        if count_f < 0:
            continue
        if count_f != int(count_f):
            caveats.append(f"痛点「{text}」计数非整数（{count}），已跳过")
            continue
        out.append({"text": text, "count": int(count_f)})
    return out, caveats


def _normalize_scenes(raw: Any) -> list[dict[str, Any]]:
    """汇总表 scenes → 前端契约 [{"name": str, "value": int}]

    再次过滤非法条目：仅接受 list；每项须 dict；name 非空字符串；value 可转非负数。
    飞书场景值为百分比小数（26.7 等），冻结 schema SceneDist.value 为 int：
    边界转换用 round（26.7→27、21.1→21），不置 0、不截断小数、不伪造。
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        name = raw_name.strip()
        if not name:
            continue
        value = item.get("value")
        if value is None:
            continue
        try:
            value_f = float(value)
        except (ValueError, TypeError):
            continue
        if value_f < 0:
            continue
        out.append({"name": name, "value": round(value_f)})
    return out


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
    # 企划层品类归一化：旧任务「小风扇」等含「扇」子品类统一为父品类「风扇」
    category = normalize_category(category) or ""
    _t0 = time.monotonic()
    try:
        records = _records_for_category(source, category)
        _log_live_node("feishu_detail", (time.monotonic() - _t0) * 1000, "success")
    except Exception:
        _log_live_node("feishu_detail", (time.monotonic() - _t0) * 1000, "error")
        raise
    if not records:
        raise ValueError(f"Feishu Base 没有匹配品类：{category}")

    # 快照统一：明细与汇总读取同一快照，避免混用；有多个快照时取最新并只保留该快照记录
    snapshot_ids = sorted({record.snapshot_id for record in records if record.snapshot_id})
    selected_snapshot = snapshot_ids[-1] if snapshot_ids else None
    if selected_snapshot is not None:
        records = [record for record in records if record.snapshot_id == selected_snapshot]

    # 汇总表读取：汇总表使用独立快照体系，不传明细快照，由 provider 按汇总表自身 category/as_of 规则选择最新行
    # （明细快照与汇总快照不同源，禁止互相复用）
    summary: dict[str, Any] | None = None
    summary_error: str | None = None
    _ts = time.monotonic()
    try:
        summary = source.get_summary(category=category)
        _log_live_node("feishu_summary", (time.monotonic() - _ts) * 1000, "success")
    except (BaseUnavailable, BaseProviderError, ValueError) as exc:
        summary = None
        summary_error = str(exc)
        _log_live_node("feishu_summary", (time.monotonic() - _ts) * 1000, "unavailable")
    summary_snapshot_id = (summary or {}).get("snapshot_id")

    pain_points, pain_caveats = _normalize_pain_points((summary or {}).get("pain_points"))
    scenes = _normalize_scenes((summary or {}).get("scenes"))
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

    # ── 商品级竞品表（base_competitors）────────────────────
    # 优先读取商品级真实竞品；缺失/无匹配则降级 Base 明细样本（不 Mock、不 LLM、不伪造）
    competitor_view = CompetitorDataView(RestrictedQueryPort(source))
    # 竞品表使用自身的快照体系，不套用明细表快照（明细 snapshot 与竞品 snapshot 不同源）
    _tc = time.monotonic()
    try:
        comp_map = competitor_view.get_competitor_map(category)
        _log_live_node("feishu_competitor", (time.monotonic() - _tc) * 1000, "success")
    except Exception:
        _log_live_node("feishu_competitor", (time.monotonic() - _tc) * 1000, "error")
        raise
    # 「是否匹配到竞品表」用 record_count 判断：即使所有商品缺价格无商品卡，也不算降级
    record_count = comp_map.get("record_count", 0)
    product_count = comp_map.get("product_count", 0)
    skipped_count = comp_map.get("skipped_count", 0)
    has_competitors = record_count > 0
    competitor_products = [
        {
            "name": p["name"],
            "price": p["price"],
            "imageUrl": p["imageUrl"] or "",
            "sellingPoint": "、".join(p["sellingPoints"]) if p["sellingPoints"] else "",
            "design": p["designScore"] if p["designScore"] is not None else 0,  # 冻结 schema 占位
            # 商品级扩展字段（前端据此展示真实状态）
            "designScore": p["designScore"],
            "brand": p["brand"],
            "sourceUrl": p["sourceUrl"],
            "sourcePlatform": p["sourcePlatform"],
            "verificationStatus": p["verificationStatus"],
            "priceMin": p["priceMin"],
            "priceMax": p["priceMax"],
            "priceBand": p["priceBand"],
            "sellingPoints": p["sellingPoints"],
            "evidenceQuote": p["evidenceQuote"],
        }
        for p in comp_map["products"]
    ]

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
            "processLog": _consumer_process_log(pain_points, scenes, summary_error, selected_snapshot, summary_snapshot_id) + pain_caveats,
            "painPoints": pain_points,
            "scenes": scenes,
            "quotes": quotes,
            "summary": _consumer_summary(pain_points, scenes, summary_error),
        },
        "competitiveMap": {
            "processLog": (
                ["数据源：飞书 Base 商品竞品表", f"读取 {record_count} 条商品级竞品，{product_count} 条进入商品卡"]
                if has_competitors and product_count > 0
                else ["数据源：飞书 Base 商品竞品表", f"读取 {record_count} 条商品级竞品，其中 {skipped_count} 条因缺少价格未进入商品卡"]
                if has_competitors
                else ["数据源：飞书 Base 商品竞品表", "商品级竞品表暂无匹配，当前仅展示 Base 明细样本；设计评分不伪造"]
            ),
            "products": competitor_products if has_competitors else products,
            "gapZone": comp_map["gap_zone"] if has_competitors else None,
            "gapZoneNote": (
                None
                if (has_competitors and comp_map["gap_zone"])
                else (comp_map["caveats"][0]["reason"] if comp_map["caveats"] else "暂无竞品空白区数据")
            ),
            "priceBands": comp_map["price_bands"] if has_competitors else _price_bands(records),
            "sellingPoints": comp_map["selling_points"] if has_competitors else [],
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
            "snapshot_id": selected_snapshot or "",
            "summary_snapshot_id": summary_snapshot_id or "",
            "competitor_snapshot_id": (comp_map.get("snapshot_id") or "") if has_competitors else "",
            "ingestion_run_id": selected_snapshot or "",
            "record_count": len(records),
            "evidence_count": len(evidence),
            "generated_at": generated_at,
        },
    }


def _consumer_process_log(
    pain_points: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    summary_error: str | None,
    detail_snapshot_id: str | None = None,
    summary_snapshot_id: str | None = None,
) -> list[str]:
    """按真实情况写 consumerVoice 过程日志：不把数据源故障写成暂无数据。

    明细快照（base_records）与汇总快照（base_summaries）属不同数据表快照体系，
    分别从返回数据动态读取，不硬编码。
    """
    if pain_points or scenes:
        log = [
            "数据源：飞书 Base 实时明细",
            f"汇总表快照提供痛点 {len(pain_points)} 条、场景 {len(scenes)} 条",
        ]
    elif summary_error is not None:
        log = [
            "数据源：飞书 Base 实时明细",
            "汇总表读取失败，painPoints 与 scenes 保持空值",
        ]
    else:
        log = [
            "数据源：飞书 Base 实时明细",
            "汇总表字段为空，painPoints 与 scenes 保持空值",
        ]
    if detail_snapshot_id or summary_snapshot_id:
        log.append(f"明细快照：{detail_snapshot_id}；汇总快照：{summary_snapshot_id}")
    return log


def _consumer_summary(
    pain_points: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    summary_error: str | None,
) -> str:
    if pain_points or scenes:
        return "已接入真实汇总痛点与场景；其余仅展示真实摘要。"
    if summary_error is not None:
        return "汇总表读取失败；情感、痛点和场景字段暂为空。"
    return "当前仅展示真实摘要；情感、痛点和场景字段尚未接入。"

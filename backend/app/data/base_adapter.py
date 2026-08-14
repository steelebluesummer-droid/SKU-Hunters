"""Base 数据访问层 — 统一适配器 + provider protocol + mock/fixture provider

约束：
- BaseDataAdapter 只能由 connector_gateway 或数据服务层持有，不能直接注入 Agent。
- 真实配置只从环境变量读取（FEISHU_BASE_TOKEN / FEISHU_DATA_TABLE_ID / FEISHU_SUMMARY_TABLE_ID）。
- 缺少配置时应用可启动；只有真正调用 Base 数据时才抛 BaseUnavailable。
- 当前未接入真实飞书 Base API（无字段映射），真实 provider 一律 fail-closed。
- 不打印 Token、不猜测飞书 API 字段、不伪造真实数据。
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from app.schemas.base_data import BaseQuery, BaseRecord, BaseRecordPage


class BaseUnavailable(Exception):
    """Base 数据源不可用（配置缺失或真实 API 未接入），与「无数据」严格区分"""


class BaseProviderError(Exception):
    """Base provider 调用失败（网络/超时等），与「无数据」严格区分"""


def _has_base_config() -> bool:
    """是否配置了真实飞书 Base 环境变量（只判断存在性，不读取 Token 值）"""
    return bool(os.getenv("FEISHU_BASE_TOKEN")) and bool(os.getenv("FEISHU_DATA_TABLE_ID"))

def _resolve_provider_mode() -> str:
    """解析 Base 数据源模式：mock / feishu / disabled（默认 disabled = 生产 fail-closed）

    - mock：本地 fixture，仅显式开启（开发/演示/测试）
    - feishu：真实飞书 Base（需配置，未接字段映射前仍 fail-closed）
    - disabled：默认，任何 Base 数据调用都抛 BaseUnavailable（生产安全默认）
    """
    return os.getenv("BASE_PROVIDER_MODE", "disabled").strip().lower()

def _provider_for_mode(mode: str) -> BaseProvider:
    """按模式实例化 provider；未知/禁用模式 → BaseUnavailable（fail-closed）"""
    if mode == "mock":
        return MockBaseProvider()
    if mode == "feishu":
        if not _has_base_config():
            raise BaseUnavailable("BASE_PROVIDER_MODE=feishu 但缺少 FEISHU_BASE_TOKEN / FEISHU_DATA_TABLE_ID")
        return FeishuBaseProvider()
    if mode == "disabled":
        raise BaseUnavailable("BASE_PROVIDER_MODE=disabled（默认），Base 数据访问已关闭")
    raise BaseUnavailable(f"未知 BASE_PROVIDER_MODE: {mode!r}")


class BaseProvider(Protocol):
    """Base 数据 provider 抽象接口（真实实现未接入，先定义协议）"""

    def search_records(
        self,
        keyword: str,
        platform: str | None = None,
        category: str | None = None,
        as_of: str | None = None,
        snapshot_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> BaseRecordPage: ...

    def get_summary(
        self,
        category: str | None = None,
        as_of: str | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_date_distribution(
        self,
        keyword: str,
        as_of: str | None = None,
        snapshot_id: str | None = None,
    ) -> list[dict[str, Any]]: ...


# ── 本地 fixture provider（演示/测试用，非真实数据）────────────

_FIXTURE_RECORDS: list[dict[str, Any]] = [
    {
        "record_id": "fixture-001", "keyword": "小风扇", "platform": "xiaohongshu",
        "category": "小风扇", "summary": "便携小风扇夏季通勤需求上升",
        "heat_index": 82.5, "interaction": 1200.0, "brand": "几素",
        "price_range": "39-99 元", "record_date": "2026-08-01",
        "source_url": "https://example.com/fan/001", "snapshot_id": "snap-2026-08-10",
        "ingested_at": "2026-08-10T10:00:00+00:00",
        "raw_value": {"likes": 1200, "comments": 88},
    },
    {
        "record_id": "fixture-002", "keyword": "小风扇", "platform": "bilibili",
        "category": "小风扇", "summary": "B站小风扇测评视频热度高",
        "heat_index": 75.0, "interaction": 900.0, "brand": None,
        "price_range": "49-99 元", "record_date": "2026-08-02",
        "source_url": "https://example.com/fan/002", "snapshot_id": "snap-2026-08-10",
        "ingested_at": "2026-08-10T10:05:00+00:00",
        "raw_value": {"views": 50000, "danmaku": 300},
    },
    {
        "record_id": "fixture-003", "keyword": "保温杯", "platform": "taobao",
        "category": "保温杯", "summary": "保温杯搜索联想词集中在品牌与容量",
        "heat_index": 60.0, "interaction": 400.0, "brand": "哈尔斯",
        "price_range": "59-159 元", "record_date": "2026-08-03",
        "source_url": None, "snapshot_id": "snap-2026-08-10",
        "ingested_at": "2026-08-10T10:10:00+00:00",
        "raw_value": {"suggest_count": 25},
    },
    {
        "record_id": "fixture-004", "keyword": "三丽鸥", "platform": "weibo",
        "category": "IP", "summary": "三丽鸥联名话题讨论活跃",
        "heat_index": 90.0, "interaction": 5000.0, "brand": "三丽鸥",
        "price_range": None, "record_date": "2026-08-04",
        "source_url": "https://example.com/ip/001", "snapshot_id": "snap-2026-08-11",
        "ingested_at": "2026-08-11T09:00:00+00:00",
        "raw_value": {"reposts": 800, "comments": 1500},
    },
    {
        "record_id": "fixture-005", "keyword": "小风扇", "platform": "google_trends",
        "category": "小风扇", "summary": "Google Trends 小风扇搜索热度上升",
        "heat_index": 70.0, "interaction": None, "brand": None,
        "price_range": None, "record_date": "2026-08-05",
        "source_url": "https://example.com/trends/001", "snapshot_id": "snap-2026-08-11",
        "ingested_at": "2026-08-11T09:10:00+00:00",
        "raw_value": {"level": 70, "growth": 12.5},
    },
]


class MockBaseProvider:
    """本地 fixture provider — 未接真实飞书 API，仅用于演示与测试"""

    def __init__(self, records: list[dict[str, Any]] | None = None):
        self._records = [BaseRecord.model_validate(r) for r in (records or _FIXTURE_RECORDS)]

    def _filtered(self, keyword: str | None, platform: str | None, category: str | None, as_of: str | None, snapshot_id: str | None = None) -> list[BaseRecord]:
        result = list(self._records)
        if keyword:
            result = [r for r in result if keyword.lower() in r.keyword.lower()]
        if platform:
            result = [r for r in result if r.platform == platform]
        if category:
            result = [r for r in result if r.category == category]
        if as_of:
            result = [r for r in result if r.record_date <= as_of]  # 不读未来数据
        if snapshot_id:
            result = [r for r in result if r.snapshot_id == snapshot_id]  # 快照锁定
        return result

    def search_records(self, keyword, platform=None, category=None, as_of=None, snapshot_id=None, page=1, page_size=20):
        filtered = self._filtered(keyword, platform, category, as_of, snapshot_id)
        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        page_records = filtered[start:end]
        return BaseRecordPage(
            records=page_records,
            total=total,
            page=page,
            page_size=page_size,
            has_more=end < total,
        )

    def get_summary(self, category=None, as_of=None, snapshot_id=None):
        filtered = self._filtered(None, None, category, as_of)
        if snapshot_id:
            filtered = [r for r in filtered if r.snapshot_id == snapshot_id]
        total_heat = sum(r.heat_index or 0 for r in filtered)
        return {
            "category": category or "all",
            "snapshot_id": snapshot_id,
            "record_count": len(filtered),
            "avg_heat_index": round(total_heat / len(filtered), 2) if filtered else 0.0,
            "brands": sorted({r.brand for r in filtered if r.brand}),
        }

    def get_date_distribution(self, keyword, as_of=None, snapshot_id=None):
        filtered = self._filtered(keyword, None, None, as_of, snapshot_id)
        dist: dict[str, int] = {}
        for r in filtered:
            dist[r.record_date] = dist.get(r.record_date, 0) + 1
        return [{"date": d, "count": c} for d, c in sorted(dist.items())]


class FeishuBaseProvider:
    """真实飞书 Base provider（占位）— 未接入真实字段映射，一律 fail-closed"""

    def __init__(self, token: str | None = None, data_table_id: str | None = None, summary_table_id: str | None = None):
        self._token = token or os.getenv("FEISHU_BASE_TOKEN")
        self._data_table_id = data_table_id or os.getenv("FEISHU_DATA_TABLE_ID")
        self._summary_table_id = summary_table_id or os.getenv("FEISHU_SUMMARY_TABLE_ID")

    def _ensure_config(self) -> None:
        if not self._token or not self._data_table_id:
            raise BaseUnavailable("飞书 Base 配置缺失：FEISHU_BASE_TOKEN / FEISHU_DATA_TABLE_ID")

    def search_records(self, *args, **kwargs):
        self._ensure_config()
        raise BaseUnavailable("真实飞书 Base API 未接入（缺少字段映射），当前仅支持本地 mock provider")

    def get_summary(self, *args, **kwargs):
        self._ensure_config()
        raise BaseUnavailable("真实飞书 Base API 未接入（缺少字段映射），当前仅支持本地 mock provider")

    def get_date_distribution(self, *args, **kwargs):
        self._ensure_config()
        raise BaseUnavailable("真实飞书 Base API 未接入（缺少字段映射），当前仅支持本地 mock provider")


# ── 统一适配器 ────────────────────────────────────────────

class BaseDataAdapter:
    """Base 数据访问层（仅 connector_gateway / 数据服务层持有，不注入 Agent）

    - 延迟初始化 provider，import 阶段不读配置、不失败。
    - session/request 级缓存，缓存 key 含查询条件 + as_of + snapshot_id。
    - 数据源故障（BaseUnavailable/BaseProviderError）与「无数据」（空结果）严格区分。
    """

    def __init__(self, provider: BaseProvider | None = None):
        self._provider = provider
        self._cache: dict[str, Any] = {}

    @property
    def provider(self) -> BaseProvider:
        if self._provider is None:
            self._provider = _provider_for_mode(_resolve_provider_mode())
        return self._provider

    def _cache_key(self, method: str, **kwargs: Any) -> str:
        return json.dumps({"method": method, **kwargs}, sort_keys=True, default=str)

    def search_records(self, keyword, platform=None, category=None, as_of=None, snapshot_id=None, page=1, page_size=20) -> BaseRecordPage:
        # 统一经 BaseQuery 校验：as_of 日期格式、page/page_size 边界、platform 枚举
        query = BaseQuery(keyword=keyword, platform=platform, category=category, as_of=as_of, snapshot_id=snapshot_id, page=page, page_size=page_size)
        key = self._cache_key(
            "search_records", keyword=query.keyword, platform=query.platform,
            category=query.category, as_of=query.as_of, snapshot_id=query.snapshot_id,
            page=query.page, page_size=query.page_size,
        )
        if key in self._cache:
            return self._cache[key]
        result = self.provider.search_records(query.keyword, query.platform, query.category, query.as_of, query.snapshot_id, query.page, query.page_size)
        self._cache[key] = result
        return result

    def search_all(self, keyword="", platform=None, category=None, as_of=None, snapshot_id=None) -> list[BaseRecord]:
        """翻页收集全部记录（供聚合统计使用，避免只统计默认 page_size=20 的第一页）

        含最大页数与无进展保护，防止 provider 异常持续返回 has_more=True 导致死循环。
        """
        records: list[BaseRecord] = []
        page = 1
        max_pages = 100  # 防御上限：正常数据远不会达到，异常时兜底
        while page <= max_pages:
            result = self.search_records(keyword, platform, category, as_of, snapshot_id, page=page, page_size=200)
            records.extend(result.records)
            if not result.has_more:
                break
            if not result.records:
                # 无进展保护：has_more=True 但本页无记录 → provider 异常，终止翻页
                break
            page += 1
        return records

    def get_summary(self, category=None, as_of=None, snapshot_id=None) -> dict[str, Any]:
        query = BaseQuery(category=category, as_of=as_of, snapshot_id=snapshot_id)
        key = self._cache_key("get_summary", category=query.category, as_of=query.as_of, snapshot_id=query.snapshot_id)
        if key in self._cache:
            return self._cache[key]
        result = self.provider.get_summary(query.category, query.as_of, query.snapshot_id)
        self._cache[key] = result
        return result

    def get_date_distribution(self, keyword, as_of=None, snapshot_id=None) -> list[dict[str, Any]]:
        query = BaseQuery(keyword=keyword, as_of=as_of, snapshot_id=snapshot_id)
        key = self._cache_key("get_date_distribution", keyword=query.keyword, as_of=query.as_of, snapshot_id=query.snapshot_id)
        if key in self._cache:
            return self._cache[key]
        result = self.provider.get_date_distribution(query.keyword, query.as_of, query.snapshot_id)
        self._cache[key] = result
        return result

    def compute_heat_index(self, keyword, as_of=None, snapshot_id=None) -> float | None:
        """基于全部记录计算综合热度指数（简单平均，供 TrendDataView 使用）"""
        records = self.search_all(keyword, as_of=as_of, snapshot_id=snapshot_id)
        heats = [r.heat_index for r in records if r.heat_index is not None]
        if not heats:
            return None
        return round(sum(heats) / len(heats), 2)

    def build_evidence_refs(self, records: list[BaseRecord]) -> list[dict[str, str]]:
        """从记录生成可点击证据引用；source_url 缺失/无效的记录被跳过（不伪造链接）"""
        refs: list[dict[str, str]] = []
        for r in records:
            if not r.source_url:
                continue
            refs.append({
                "url": r.source_url,
                "title": f"{r.keyword} · {r.platform}",
                "snippet": (r.summary or "")[:200],
            })
        return refs

    def clear_cache(self) -> None:
        self._cache.clear()


class BaseQueryPort(Protocol):
    """受限查询端口协议 — View 只能通过这组只读方法访问 Base 数据

    这是「应用层能力隔离」的类型契约：View 依赖本协议，而非完整 BaseDataAdapter。
    """

    def search_records(
        self,
        keyword: str,
        platform: str | None = None,
        category: str | None = None,
        as_of: str | None = None,
        snapshot_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> BaseRecordPage: ...

    def search_all(
        self,
        keyword: str = "",
        platform: str | None = None,
        category: str | None = None,
        as_of: str | None = None,
        snapshot_id: str | None = None,
    ) -> list[BaseRecord]: ...

    def get_summary(
        self,
        category: str | None = None,
        as_of: str | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_date_distribution(
        self,
        keyword: str,
        as_of: str | None = None,
        snapshot_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def compute_heat_index(self, keyword: str, as_of: str | None = None, snapshot_id: str | None = None) -> float | None: ...

    def build_evidence_refs(self, records: list[BaseRecord]) -> list[dict[str, str]]: ...

class RestrictedQueryPort:
    """受限查询端口 — 只暴露只读查询方法，隐藏 adapter 的管理方法（如 clear_cache）

    View 持有本端口（而非完整 BaseDataAdapter），公共接口仅限 BaseQueryPort 的只读查询。
    内部仍持有一个 adapter 引用（私有 _adapter），但 View 无法通过本端口调用管理/写方法。
    注意：这仍是应用层能力隔离（Python 反射可绕过），不是进程级安全边界。
    """

    def __init__(self, adapter: BaseDataAdapter):
        self._adapter = adapter

    def search_records(self, keyword, platform=None, category=None, as_of=None, snapshot_id=None, page=1, page_size=20):
        return self._adapter.search_records(keyword, platform, category, as_of, snapshot_id, page, page_size)

    def search_all(self, keyword="", platform=None, category=None, as_of=None, snapshot_id=None):
        return self._adapter.search_all(keyword, platform, category, as_of, snapshot_id)

    def get_summary(self, category=None, as_of=None, snapshot_id=None):
        return self._adapter.get_summary(category, as_of, snapshot_id)

    def get_date_distribution(self, keyword, as_of=None, snapshot_id=None):
        return self._adapter.get_date_distribution(keyword, as_of, snapshot_id)

    def compute_heat_index(self, keyword, as_of=None, snapshot_id=None):
        return self._adapter.compute_heat_index(keyword, as_of, snapshot_id)

    def build_evidence_refs(self, records):
        return self._adapter.build_evidence_refs(records)

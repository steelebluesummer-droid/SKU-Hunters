"""FeishuBaseProvider Mock API 测试 — 假 auth + mock requests.post 验证只读 provider 逻辑

不接真实飞书 API：字段名/表 ID 均为假值，仅验证字段转换、分页、fail-closed、边界处理。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.data.base_adapter import BaseProviderError, BaseUnavailable, FeishuBaseProvider
from app.schemas.base_data import BasePlatform


class _FakeAuth:
    """假认证：返回固定 token，不触发真实 tenant_access_token 获取"""

    def get_token(self) -> str:
        return "fake-token"


class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data
        self.status_code = 200

    def json(self) -> dict:
        return self._data


def _date_ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _record(**fields) -> dict:
    rid = fields.get("record_id", "rec-x")
    return {"record_id": rid, "fields": fields}


def _resp(items, has_more=False, page_token=None, total=None) -> dict:
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "has_more": has_more,
            "page_token": page_token or "",
            "total": total if total is not None else len(items),
            "items": items,
        },
    }


def _base_fields(**overrides) -> dict:
    """构造一条合法的飞书字段（字段名按 feishu-base-mapping.md §四 设计假设）"""
    fields = {
        "record_id": "rec-001",
        "keyword": "小风扇",
        "platform": "xiaohongshu",
        "category": "小风扇",
        "summary": "便携小风扇需求上升",
        "heat_index": 82.5,
        "interaction": 1200,
        "brand": "几素",
        "price_range": "39-99 元",
        "record_date": _date_ms("2026-08-01"),
        "source_url": {"link": "https://example.com/fan/001", "text": "链接"},
        "snapshot_id": "snap-20260814T000000Z-1",
        "ingested_at": _date_ms("2026-08-10"),
        "raw_value": '{"likes": 1200}',
    }
    fields.update(overrides)
    return fields


def _provider_with(monkeypatch, responder):
    """构造 provider，注入假 auth，monkeypatch requests.post 为 responder(url, json)"""
    auth = _FakeAuth()
    monkeypatch.setattr(
        "requests.post",
        lambda url, headers=None, json=None, timeout=None, **kw: _FakeResponse(responder(url, json or {})),
    )
    return FeishuBaseProvider(
        auth=auth, app_token="fake-app", data_table_id="tbl-data", summary_table_id="tbl-summary"
    )


def test_normal_return(monkeypatch):
    """正常返回：飞书字段正确转换为 BaseRecord"""
    def responder(url, body):
        return _resp([_record(**_base_fields())])

    provider = _provider_with(monkeypatch, responder)
    page = provider.search_records("小风扇")
    assert page.total == 1
    r = page.records[0]
    assert r.record_id == "rec-001"
    assert r.keyword == "小风扇"
    assert r.platform == BasePlatform.XIAOHONGSHU
    assert r.heat_index == 82.5
    assert r.record_date == "2026-08-01"
    assert r.source_url == "https://example.com/fan/001"
    assert r.raw_value == {"likes": 1200}


def test_pagination(monkeypatch):
    """分页：page_token 游标翻页拉取全量"""
    pages = {
        "": _resp([_record(**_base_fields(record_id="r1"))], has_more=True, page_token="tok1"),
        "tok1": _resp([_record(**_base_fields(record_id="r2"))], has_more=False),
    }

    def responder(url, body):
        return pages[body.get("page_token") or ""]

    provider = _provider_with(monkeypatch, responder)
    page = provider.search_records("小风扇")
    assert page.total == 2  # 两页都拉取到


def test_missing_fields(monkeypatch):
    """字段缺失：brand/price_range/source_url 缺省 → None（不伪造）"""
    fields = _base_fields(brand=None, price_range=None, source_url=None)

    def responder(url, body):
        return _resp([_record(**fields)])

    provider = _provider_with(monkeypatch, responder)
    r = provider.search_records("小风扇").records[0]
    assert r.brand is None
    assert r.price_range is None
    assert r.source_url is None


def test_permission_error(monkeypatch):
    """权限错误：飞书返回非零 code → BaseProviderError（不伪装成无数据）"""
    def responder(url, body):
        return {"code": 1254001, "msg": "wrong request body", "data": {}}

    provider = _provider_with(monkeypatch, responder)
    with pytest.raises(BaseProviderError):
        provider.search_records("小风扇")


def test_empty_data(monkeypatch):
    """空数据：飞书返回 0 条 → 返回空 BaseRecordPage（不抛异常）"""
    def responder(url, body):
        return _resp([], has_more=False, total=0)

    provider = _provider_with(monkeypatch, responder)
    page = provider.search_records("小风扇")
    assert page.total == 0
    assert page.records == []


def test_snapshot_and_date_filter(monkeypatch):
    """快照与日期过滤：as_of 不读未来，snapshot_id 锁定版本"""
    items = [
        _record(**_base_fields(record_id="r1", record_date=_date_ms("2026-08-01"), snapshot_id="snap-A")),
        _record(**_base_fields(record_id="r2", record_date=_date_ms("2026-08-05"), snapshot_id="snap-A")),
        _record(**_base_fields(record_id="r3", record_date=_date_ms("2026-08-01"), snapshot_id="snap-B")),
    ]

    def responder(url, body):
        return _resp(items)

    provider = _provider_with(monkeypatch, responder)
    # as_of 过滤：只保留 record_date <= 08-02
    page = provider.search_records("小风扇", as_of="2026-08-02")
    assert page.total == 2
    assert {r.record_id for r in page.records} == {"r1", "r3"}
    # snapshot_id 过滤：只保留 snap-A
    page = provider.search_records("小风扇", snapshot_id="snap-A")
    assert page.total == 2
    assert {r.record_id for r in page.records} == {"r1", "r2"}


def test_invalid_platform_skipped(monkeypatch):
    """非法 platform：跳过 + 不归 OTHER（该记录不出现在结果中）"""
    items = [
        _record(**_base_fields(record_id="r1")),
        _record(**_base_fields(record_id="r2", platform="unknown_platform")),
    ]

    def responder(url, body):
        return _resp(items)

    provider = _provider_with(monkeypatch, responder)
    page = provider.search_records("小风扇")
    assert page.total == 1
    assert page.records[0].record_id == "r1"
    # caveat 被记录（不静默吞掉）
    assert len(provider.caveats) == 1
    assert provider.caveats[0]["record_id"] == "r2"
    assert provider.caveats[0]["field"] == "platform"


def test_network_error(monkeypatch):
    """网络/超时错误：requests 异常 → BaseProviderError"""
    import requests

    def raise_request(*args, **kwargs):
        raise requests.ConnectionError("connection timeout")

    auth = _FakeAuth()
    monkeypatch.setattr("requests.post", raise_request)
    provider = FeishuBaseProvider(auth=auth, app_token="fake-app", data_table_id="tbl-data")
    with pytest.raises(BaseProviderError):
        provider.search_records("小风扇")


def test_missing_config_fail_closed(monkeypatch):
    """缺 app_token/table_id → BaseUnavailable（fail-closed）"""
    provider = FeishuBaseProvider(auth=_FakeAuth(), app_token=None, data_table_id=None)
    with pytest.raises(BaseUnavailable):
        provider.search_records("小风扇")


def test_get_summary_reads_summary_table(monkeypatch):
    """get_summary 只读汇总表，不读明细表；无匹配快照 → BaseUnavailable"""
    def responder(url, body):
        if "/tbl-summary/" in url:
            return _resp([_record(record_id="s1", category="小风扇", snapshot_id="snap-A",
                                  record_count=10, avg_heat_index=75.5,
                                  brands='["几素", "哈尔斯"]')])
        return _resp([])

    provider = _provider_with(monkeypatch, responder)
    summary = provider.get_summary(category="小风扇", snapshot_id="snap-A")
    assert summary["record_count"] == 10
    assert summary["avg_heat_index"] == 75.5
    assert summary["brands"] == ["几素", "哈尔斯"]
    # 无匹配快照 → BaseUnavailable（一期不做静默实时聚合降级）
    with pytest.raises(BaseUnavailable):
        provider.get_summary(category="小风扇", snapshot_id="不存在的快照")


def test_http_error_status(monkeypatch):
    """HTTP 4xx/5xx：即使响应体 code=0 也判失败（先查 HTTP 状态码）"""

    class _ErrorResponse:
        status_code = 500

        def json(self):
            return {"code": 0, "msg": "success", "data": {"has_more": False, "items": []}}

    auth = _FakeAuth()
    monkeypatch.setattr("requests.post", lambda *a, **k: _ErrorResponse())
    provider = FeishuBaseProvider(auth=auth, app_token="fake-app", data_table_id="tbl-data")
    with pytest.raises(BaseProviderError):
        provider.search_records("小风扇")


def test_cache_prevents_duplicate_fetch(monkeypatch):
    """请求级缓存：多次 search_records 只拉一次飞书；clear_cache 后重新拉取"""
    call_count = {"n": 0}

    def responder(url, body):
        call_count["n"] += 1
        return _resp([_record(**_base_fields())])

    provider = _provider_with(monkeypatch, responder)
    provider.search_records("小风扇")
    provider.search_records("小风扇")
    assert call_count["n"] == 1  # 缓存命中，不重复拉取

    provider.clear_cache()
    provider.search_records("小风扇")
    assert call_count["n"] == 2  # 清缓存后重新拉取


def test_get_summary_duplicate_snapshot(monkeypatch):
    """汇总表：相同 snapshot_id 多条 → BaseProviderError（歧义，不静默取第一条）"""
    def responder(url, body):
        if "/tbl-summary/" in url:
            return _resp([
                _record(record_id="s1", category="小风扇", snapshot_id="snap-A", record_count=10),
                _record(record_id="s2", category="小风扇", snapshot_id="snap-A", record_count=20),
            ])
        return _resp([])

    provider = _provider_with(monkeypatch, responder)
    with pytest.raises(BaseProviderError):
        provider.get_summary(category="小风扇", snapshot_id="snap-A")


def test_get_summary_selects_latest_as_of(monkeypatch):
    """汇总表：未指定 snapshot_id 时按 as_of 降序选最新"""
    def responder(url, body):
        if "/tbl-summary/" in url:
            return _resp([
                _record(record_id="s1", category="小风扇", snapshot_id="snap-old",
                        as_of=_date_ms("2026-08-01"), record_count=10),
                _record(record_id="s2", category="小风扇", snapshot_id="snap-new",
                        as_of=_date_ms("2026-08-10"), record_count=20),
            ])
        return _resp([])

    provider = _provider_with(monkeypatch, responder)
    summary = provider.get_summary(category="小风扇")
    assert summary["snapshot_id"] == "snap-new"
    assert summary["record_count"] == 20


def test_get_summary_duplicate_as_of(monkeypatch):
    """汇总表：多条相同 as_of（不同 snapshot_id）→ BaseProviderError（歧义）"""
    def responder(url, body):
        if "/tbl-summary/" in url:
            return _resp([
                _record(record_id="s1", category="小风扇", snapshot_id="snap-A",
                        as_of=_date_ms("2026-08-01"), record_count=10),
                _record(record_id="s2", category="小风扇", snapshot_id="snap-B",
                        as_of=_date_ms("2026-08-01"), record_count=20),
            ])
        return _resp([])

    provider = _provider_with(monkeypatch, responder)
    with pytest.raises(BaseProviderError):
        provider.get_summary(category="小风扇")

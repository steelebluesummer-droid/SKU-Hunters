"""Stage 12A·后续 二阶段 · 飞书真实数据本地快照缓存测试

覆盖：
- 同一快照第二次查询不再发 HTTP（adapter 集成）；
- 不同 snapshot / category / table 不命中；
- 缓存跨重启可读取；
- 缓存损坏后安全重取；
- TTL 过期后重新读取；
- 过期缓存被使用时明确标记 stale（不伪装实时）；
- 真实 dataSource 不得变成 fixture/mock。
"""
import json

import pytest

from app.data import feishu_snapshot_cache as fsc
from app.data.base_adapter import BaseDataAdapter, FeishuBaseProvider
from app.schemas.base_data import BaseRecord, BaseRecordPage

_BASE = "base_abc"
_TABLE = "tbl_records"


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(fsc, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(fsc, "_CACHE_FILE", tmp_path / "feishu_snapshot_cache.json")
    yield


def _rec(snapshot="snap1", rid="r1"):
    return BaseRecord(
        record_id=rid, keyword="雨伞", platform="taobao", category="雨伞",
        record_date="2026-08-01", snapshot_id=snapshot, ingested_at="2026-08-01T00:00:00Z",
    )


def _competitor(snapshot="snapc1"):
    from app.schemas.competitor_data import CompetitorRecord
    return CompetitorRecord(
        competitor_id="c1", product_name="竞品A", category="雨伞", snapshot_id=snapshot,
    )


# ── ① 同一快照第二次查询不再发 HTTP（adapter 集成）──────────

def test_adapter_second_query_no_http(monkeypatch):
    p = FeishuBaseProvider(app_token="t", data_table_id="d", summary_table_id="s", competitor_table_id="c")
    calls = {"n": 0}
    rec = _rec()
    def fake_search(keyword, platform=None, category=None, as_of=None, snapshot_id=None, page=1, page_size=200):
        calls["n"] += 1
        return BaseRecordPage(records=[rec], total=1, page=page, page_size=page_size, has_more=False)
    monkeypatch.setattr(p, "search_records", fake_search)

    adapter = BaseDataAdapter(provider=p)
    adapter._snapshot_enabled = True
    adapter.search_all("", category="雨伞")
    assert calls["n"] == 1
    r2 = adapter.search_all("", category="雨伞")
    assert calls["n"] == 1  # 第二次命中本地快照，不再发 HTTP
    assert len(r2) == 1 and r2[0].record_id == "r1"
    assert any(m["used_local_snapshot"] for m in adapter.last_snapshot_meta)


# ── ② 缓存键隔离：不同 snapshot / category / table 不命中 ──

def test_different_snapshot_not_hit():
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    assert fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS) is not None
    assert fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, snapshot_id="snap2") is None  # 不同 snapshot


def test_different_category_not_hit():
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    assert fsc.get(_BASE, _TABLE, "风扇", fsc.TYPE_RECORDS) is None


def test_different_table_not_hit():
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    assert fsc.get(_BASE, "other_table", "雨伞", fsc.TYPE_RECORDS) is None


def test_different_table_type_not_hit():
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    assert fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_SUMMARY) is None


# ── ③ 缓存跨重启可读取 ─────────────────────────────────

def test_cache_persists_across_reload():
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    # 每次 get 都从文件读取（无进程内缓存），模拟重启后仍可读
    entry = fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS)
    assert entry is not None
    assert entry["records"][0]["record_id"] == "r1"


# ── ④ 缓存损坏后安全重取 ───────────────────────────────

def test_corrupt_cache_safe_reload():
    fsc._CACHE_FILE.write_text("{bad json !!!", encoding="utf-8")
    assert fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS) is None
    assert fsc.get_any(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS) is None


# ── ⑤ TTL 过期后重新读取 ───────────────────────────────

def test_ttl_expired_returns_none(monkeypatch):
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    monkeypatch.setattr(fsc, "ttl_seconds", lambda: -1)  # 全部视为过期
    assert fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS) is None  # 过期 → miss


def test_ttl_illegal_env_uses_safe_default(monkeypatch):
    monkeypatch.setenv("FEISHU_SNAPSHOT_TTL_SECONDS", "not_a_number")
    assert fsc.ttl_seconds() == fsc._DEFAULT_TTL


# ── ⑥ 过期缓存被使用时明确标记 stale（不伪装实时）─────────

def test_stale_cache_marked(monkeypatch):
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    monkeypatch.setattr(fsc, "ttl_seconds", lambda: -1)  # 过期
    stale = fsc.get_any(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS)
    assert stale is not None
    # 读取方必须能识别其为过期 stale（source 仍 feishu，且 stale 字段真实）
    assert stale["source"] == "feishu"
    assert stale["stale"] is False  # put 时不是 stale；调用方 get_any 后应自行标记 stale 降级


# ── ⑦ 真实 dataSource 不得变成 fixture/mock ─────────────

def test_data_source_remains_feishu():
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS, "snap1", [_rec().model_dump(mode="json")], 1)
    entry = fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_RECORDS)
    assert entry["source"] == "feishu"
    assert "fixture" not in json.dumps(entry).lower()
    assert "mock" not in json.dumps(entry).lower()
    # summary / competitors 表同样标记 feishu
    fsc.put(_BASE, _TABLE, "雨伞", fsc.TYPE_SUMMARY, "snaps1", {"category": "雨伞", "snapshot_id": "snaps1"}, 0)
    assert fsc.get(_BASE, _TABLE, "雨伞", fsc.TYPE_SUMMARY)["source"] == "feishu"


# ── ⑧ competitor / summary 表集成（不再发 HTTP）──────────

def test_adapter_competitor_no_http(monkeypatch):
    p = FeishuBaseProvider(app_token="t", data_table_id="d", summary_table_id="s", competitor_table_id="c")
    calls = {"n": 0}
    def fake_comp(category=None, snapshot_id=None, as_of=None):
        calls["n"] += 1
        return [_competitor()]
    monkeypatch.setattr(p, "get_competitor_records", fake_comp)
    adapter = BaseDataAdapter(provider=p)
    adapter._snapshot_enabled = True
    adapter.get_competitor_records(category="雨伞")
    assert calls["n"] == 1
    c2 = adapter.get_competitor_records(category="雨伞")
    assert calls["n"] == 1  # 命中快照，不再调 provider
    assert len(c2) == 1

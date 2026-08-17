"""Stage 12A · 洞察二次分析缓存测试

覆盖：
- 相同品类/快照命中缓存；
- 任一快照缺失 → 不命中（安全重算）；
- snapshot / prompt 版本变化 → 新键，不误复用；
- 缓存内容损坏 → 安全重算（返回 None）；
- 重启后缓存仍可恢复；
- 不产生跨品类污染。
"""
import json
import pathlib

import pytest

from app.planning import insight_cache


@pytest.fixture(autouse=True)
def reset_cache_dir(monkeypatch, tmp_path):
    insight_cache._test_reset_cache_dir(tmp_path)
    yield
    insight_cache._test_reset_cache_dir(tmp_path)


def test_same_key_hits_cache():
    k = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    insight_cache.put(k, {"opportunityPool": [{"id": "p1"}], "consumerVoice": {"painPointChains": []}})
    got = insight_cache.get(k)
    assert got["opportunityPool"] == [{"id": "p1"}]


def test_missing_snapshot_no_key():
    """任一快照缺失 → cache_key 返回 None（不命中，安全重算）"""
    assert insight_cache.cache_key("风扇", "", "s1", "c1") is None
    assert insight_cache.cache_key("风扇", "d1", "", "c1") is None
    assert insight_cache.cache_key("风扇", "d1", "s1", "") is None
    assert insight_cache.cache_key("", "d1", "s1", "c1") is None


def test_snapshot_change_new_key():
    """明细快照变化 → 新键，旧缓存不命中"""
    k1 = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    k2 = insight_cache.cache_key("风扇", "d2", "s1", "c1")
    assert k1 != k2
    insight_cache.put(k1, {"x": 1})
    assert insight_cache.get(k2) is None  # 快照变化不误复用


def test_prompt_version_change_new_key(monkeypatch):
    monkeypatch.setattr(insight_cache, "PROMPT_VERSION", "1.0")
    k1 = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    monkeypatch.setattr(insight_cache, "PROMPT_VERSION", "2.0")
    k2 = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    assert k1 != k2


def test_no_cross_category_pollution():
    """不同品类 → 不同键，不跨品类复用"""
    k_fan = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    k_umbrella = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    assert k_fan != k_umbrella
    insight_cache.put(k_fan, {"x": 1})
    assert insight_cache.get(k_umbrella) is None


def test_corrupt_cache_safe_recompute():
    """缓存文件损坏 → get 返回 None（安全重算），不抛异常"""
    k = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    p = pathlib.Path(insight_cache._CACHE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{corrupt json !!", encoding="utf-8")
    assert insight_cache.get(k) is None


def test_cache_persists_across_reload():
    """写入后重新加载（模拟重启）缓存仍有效"""
    k = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    value = {"competitiveMap": {"needDimensions": [{"name": "d"}]}}
    insight_cache.put(k, value)
    # 重新实例化/加载（同一文件）
    loaded = insight_cache.get(k)
    assert loaded["competitiveMap"]["needDimensions"] == [{"name": "d"}]


# ── 四阶段 · 只缓存完整可用增强结果 ─────────────────

def test_incomplete_cache_is_miss():
    """complete=False 的半成品缓存 → get 返回 None（不命中，安全重算）"""
    k = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    insight_cache.put(k, {"competitiveMap": {"needDimensions": []}}, complete=False)
    assert insight_cache.get(k) is None


def test_old_schema_version_is_miss():
    """缓存结构版本过期 → miss"""
    k = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    insight_cache.put(k, {"x": 1}, complete=True)
    f = pathlib.Path(insight_cache._CACHE_FILE)
    data = json.loads(f.read_text(encoding="utf-8"))
    data[k]["cache_schema_version"] = "1"  # 篡改为旧版本
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert insight_cache.get(k) is None


def test_put_metadata_written():
    """写入时记录元数据：schema_version / created_at / complete / node_status / caveats"""
    k = insight_cache.cache_key("风扇", "d1", "s1", "c1")
    insight_cache.put(
        k,
        {"opportunityPool": [{"id": "p1"}]},
        complete=True,
        node_status={"opportunityPool": "ok"},
        caveats=["竞品表不可用"],
    )
    f = pathlib.Path(insight_cache._CACHE_FILE)
    data = json.loads(f.read_text(encoding="utf-8"))
    entry = data[k]
    assert entry["complete"] is True
    assert entry["cache_schema_version"] == insight_cache.CACHE_SCHEMA_VERSION
    assert entry["created_at"]
    assert entry["node_status"]["opportunityPool"] == "ok"
    assert entry["caveats"] == ["竞品表不可用"]
    assert entry["data"]["opportunityPool"] == [{"id": "p1"}]

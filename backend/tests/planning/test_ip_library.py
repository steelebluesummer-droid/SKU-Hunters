"""IP 资源库（扩充）模块测试

覆盖：
1. seed 完整性：33 条、字段结构、id 唯一。
2. 展示字段映射：potential 分档、ipType 预设（styleTags/audienceGroup/matrix）。
3. 别名归一：三丽鸥/海贼王/小黄人/宝可梦/Chiikawa 等别名表。
4. merged_candidate_pool：策展 12 + 扩充 33 并入，同名去重保留并集。
5. get_ip_library：非 feishu 模式下走 seed 档（不受环境配置影响）。
"""

from __future__ import annotations

import os

from app.planning import ip_library


def _seed_only(monkeypatch):
    """强制 seed 档：非 feishu 模式 + 清缓存"""
    monkeypatch.delenv("BASE_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("FEISHU_IP_PARTNERSHIP_TABLE_ID", raising=False)
    ip_library.reset_library_cache()


def test_seed_completeness_33():
    assert len(ip_library.IP_LIBRARY_SEED) == 33
    ids = [ip["ipId"] for ip in ip_library.IP_LIBRARY_SEED]
    assert len(set(ids)) == 33


def test_seed_field_contract():
    required = {
        "ipId", "slug", "name", "ipType", "licensor", "cooperationStatus",
        "cooperationSince", "latestSeries", "productLines", "starProducts",
        "priceMin", "priceMax", "channelStrategy", "ipHeat", "notes", "sourceUrl",
    }
    for ip in ip_library.IP_LIBRARY_SEED:
        missing = required - set(ip.keys())
        assert not missing, f"{ip.get('ipId')} 缺字段 {missing}"
        assert ip["ipType"] in ip_library.TYPE_FILTERS, ip["ipType"]
        assert ip["cooperationStatus"] in ip_library.STATUS_FILTERS, ip["cooperationStatus"]


def test_potential_mapping():
    assert ip_library._potential(10) == 5
    assert ip_library._potential(9) == 5
    assert ip_library._potential(8) == 4
    assert ip_library._potential(7) == 4
    assert ip_library._potential(6) == 3
    assert ip_library._potential(3) == 3
    assert ip_library._potential("bad") == 3


def test_display_fields_by_type():
    rec = {"ipType": "日韩系", "ipHeat": 9}
    out = ip_library.apply_display_fields(rec)
    assert out["potential"] == 5
    assert out["audienceGroup"] == "女性向"
    assert out["styleGroup"] == "可爱萌系"
    assert 0 <= out["matrix"]["x"] <= 1 and 0 <= out["matrix"]["y"] <= 1

    rec2 = ip_library.apply_display_fields({"ipType": "潮玩艺人", "ipHeat": 6})
    assert rec2["styleGroup"] == "潮流个性" and rec2["potential"] == 3

    # 未知 ipType 落默认预设，不抛错
    rec3 = ip_library.apply_display_fields({"ipType": "未知类型", "ipHeat": 5})
    assert rec3["audienceGroup"] == "大众"


def test_alias_normalize():
    assert ip_library.normalize_ip_name("三丽鸥（Sanrio）") == ip_library.normalize_ip_name("三丽鸥")
    assert ip_library.normalize_ip_name("海贼王（ONE PIECE）") == ip_library.normalize_ip_name("海贼王")
    assert ip_library.normalize_ip_name("小黄人（神偷奶爸）") == ip_library.normalize_ip_name("小黄人")
    assert ip_library.normalize_ip_name("Pokémon") == ip_library.normalize_ip_name("宝可梦")
    assert ip_library.normalize_ip_name("Chiikawa（吉伊卡哇）") == ip_library.normalize_ip_name("Chiikawa")


def test_get_ip_library_seed_mode(monkeypatch):
    _seed_only(monkeypatch)
    ips = ip_library.get_ip_library()
    assert len(ips) == 33
    # 展示字段全部补齐
    assert all("potential" in ip and "matrix" in ip and "styleTags" in ip for ip in ips)
    ip_library.reset_library_cache()


def test_merged_candidate_pool_dedup_and_union(monkeypatch):
    _seed_only(monkeypatch)
    curated = [{"name": "三丽鸥", "status": "合作中", "heat": "9", "fit": ["风格：可爱"]}]
    pool = ip_library.merged_candidate_pool(curated)
    # 策展 12 + 扩充 33，同名（含别名）去重后无重复
    keys = [ip_library.normalize_ip_name(p["name"]) for p in pool]
    assert len(keys) == len(set(keys))
    # 三丽鸥（curated 与扩充库 ip-003 同名）保留并集：扩充侧授权信息并入
    sanrio = [p for p in pool if ip_library.normalize_ip_name(p["name"]) == "三丽鸥"][0]
    assert sanrio.get("licensor") == "三丽鸥公司"
    assert sanrio.get("priceBand") == "¥5.98-¥474"
    # 扩充库新 IP（如宝可梦）进入池
    assert any(ip_library.normalize_ip_name(p["name"]) == "宝可梦" for p in pool)
    ip_library.reset_library_cache()


def test_merged_candidate_pool_empty_input(monkeypatch):
    _seed_only(monkeypatch)
    pool = ip_library.merged_candidate_pool([])
    assert len(pool) >= 35  # 12 策展 + 33 扩充 - 同名/别名去重（约 10 个重叠）
    ip_library.reset_library_cache()


def test_feishu_missing_config_falls_back_to_seed(monkeypatch):
    """feishu 模式但未配置表 ID → seed 降级，不抛错"""
    monkeypatch.setenv("BASE_PROVIDER_MODE", "feishu")
    monkeypatch.delenv("FEISHU_IP_PARTNERSHIP_TABLE_ID", raising=False)
    ip_library.reset_library_cache()
    ips = ip_library.get_ip_library()
    assert len(ips) == 33
    ip_library.reset_library_cache()

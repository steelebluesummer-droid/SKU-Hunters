"""Stage 12A·后续 四阶段 · 只缓存完整可用增强结果

验证：
- _write_cache_if_complete：完整 → 可命中；不完整 → 不写可命中缓存（get miss）；
- generate_insights 首次 miss → 生成并写入完整缓存；
- 同快照第二任务 generate → 命中缓存，不再调用 LLM agent；
- 命中结果通过 schema 校验（generate 返回合法 bundle）。
"""
import pytest

from app.planning import insight_cache, repository, service


def _make_plan(pid):
    plan = {
        "plan_id": pid,
        "brief": {"category": "雨伞", "mode": "live", "costLimit": 25},
        "mode": "live",
        "status": "brief_locked",
        "created_at": "2026-08-16T00:00:00+00:00",
    }
    repository._PLANS[pid] = plan
    return plan


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    snapshot = dict(repository._PLANS)
    repository._PLANS.clear()
    monkeypatch.setattr(repository, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(repository, "_STATE_FILE", tmp_path / "plans_state.json")
    monkeypatch.setattr(repository, "_LEGACY_STATE_FILE", tmp_path / "legacy.json")
    insight_cache._test_reset_cache_dir(tmp_path / "cache")
    yield
    repository._PLANS.clear()
    repository._PLANS.update(snapshot)


def _fake_resolve(category, brief):
    return {
        "trendRadar": {"processLog": []},
        "dataContext": {"snapshot_id": "d1", "summary_snapshot_id": "s1", "competitor_snapshot_id": "c1"},
    }


def _patch_full_agents(monkeypatch):
    # build_opportunity_pool 在 service 顶层 import → 需 monkeypatch service 引用
    monkeypatch.setattr(
        service,
        "build_opportunity_pool",
        lambda *a, **k: ([{"id": "p1", "title": "t1", "rank": 1, "confidence": 80, "opportunityType": "design_value"}], ["生成机会池"]),
    )
    monkeypatch.setattr(
        "app.planning.consumer_voice_agent.build_consumer_voice_chains",
        lambda *a, **k: {"userProfile": {}, "painPointChains": [{"painPoint": "伞面易翻"}]},
    )
    monkeypatch.setattr(
        "app.planning.competitive_map_agent.build_competitive_map_analysis",
        lambda *a, **k: {"needDimensions": ["轻量"], "needSatisfaction": [], "opportunityGaps": []},
    )
    monkeypatch.setattr(
        "app.planning.asset_fit_agent.build_asset_fit",
        lambda *a, **k: [{"opportunity_id": "p1"}],
    )


# ── ① _write_cache_if_complete：完整/不完整 ─────────────

def test_write_complete_cache_hits():
    ck = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    bundle = {
        "opportunityPool": [{"id": "p1"}],
        "consumerVoice": {"painPointChains": [{"painPoint": "x"}]},
        "competitiveMap": {"needDimensions": ["轻量"]},
        "assetFit": [{"opportunity_id": "p1"}],
        "trendRadar": {"processLog": []},
    }
    service._write_cache_if_complete(ck, bundle)
    got = insight_cache.get(ck)
    assert got["opportunityPool"] == [{"id": "p1"}]
    assert got["assetFit"] == [{"opportunity_id": "p1"}]


def test_incomplete_not_written_as_hit():
    ck = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    bundle = {
        "opportunityPool": [],  # 缺失 → incomplete
        "consumerVoice": {"painPointChains": [{"painPoint": "x"}]},
        "competitiveMap": {"needDimensions": ["轻量"]},
        "assetFit": [],
        "trendRadar": {"processLog": ["竞品满足矩阵生成失败（LLM 暂不可用）"]},
    }
    service._write_cache_if_complete(ck, bundle)
    assert insight_cache.get(ck) is None  # 半成品不命中


# ── ② generate_insights 首次 miss → 生成并写入 ─────────

def test_generate_insights_first_miss_writes(monkeypatch):
    monkeypatch.setattr(service, "_resolve_insight_bundle", _fake_resolve)
    _patch_full_agents(monkeypatch)
    plan = _make_plan("p1")
    bundle = service.generate_insights(plan)
    assert bundle["competitiveMap"]["needDimensions"] == ["轻量"]
    ck = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    assert insight_cache.get(ck) is not None  # 完整结果已写入可命中缓存


# ── ③ 同快照第二任务 generate → 命中缓存，不调 LLM ──────

def test_generate_insights_second_plan_hits_no_llm(monkeypatch):
    monkeypatch.setattr(service, "_resolve_insight_bundle", _fake_resolve)
    _patch_full_agents(monkeypatch)
    plan1 = _make_plan("p1")
    service.generate_insights(plan1)
    ck = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    assert insight_cache.get(ck) is not None

    # 第二次：把 cm agent 换成计数版；命中缓存则不应被调用
    calls = {"cm": 0}
    def counting_cm(*a, **k):
        calls["cm"] += 1
        return {"needDimensions": ["轻量"], "needSatisfaction": [], "opportunityGaps": []}
    monkeypatch.setattr("app.planning.competitive_map_agent.build_competitive_map_analysis", counting_cm)

    plan2 = _make_plan("p2")
    bundle2 = service.generate_insights(plan2)
    assert calls["cm"] == 0  # 命中缓存，不调 LLM agent
    assert bundle2["competitiveMap"]["needDimensions"] == ["轻量"]  # 命中结果通过 schema（可渲染）


# ── ④ incomplete 缓存不命中 → 走真实生成 ────────────────

def test_incomplete_cache_not_used_reruns(monkeypatch):
    # 预写 incomplete 缓存
    ck = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    insight_cache.put(ck, {"competitiveMap": {"needDimensions": []}}, complete=False)

    monkeypatch.setattr(service, "_resolve_insight_bundle", _fake_resolve)
    calls = {"cm": 0}
    def counting_cm(*a, **k):
        calls["cm"] += 1
        return {"needDimensions": ["轻量"], "needSatisfaction": [], "opportunityGaps": []}
    _patch_full_agents(monkeypatch)
    monkeypatch.setattr("app.planning.competitive_map_agent.build_competitive_map_analysis", counting_cm)

    plan = _make_plan("p1")
    service.generate_insights(plan)
    assert calls["cm"] == 1  # incomplete 缓存为 miss → 真实重新生成


# ── P1-3：落盘失败 → 内存状态回滚（原子性）──────────────

def test_save_failure_rolls_back_memory_state(monkeypatch):
    """_save_state 抛异常时，内存中的 plan 不得提前变为 insights_ready"""
    monkeypatch.setattr(service, "_resolve_insight_bundle", _fake_resolve)
    _patch_full_agents(monkeypatch)

    def boom():
        raise OSError("disk full")

    monkeypatch.setattr(service, "_save_state", boom)

    plan = _make_plan("p_rollback")
    with pytest.raises(OSError):
        service.generate_insights(plan)

    # 回滚：状态仍为 brief_locked，且未写入 insights / data_context
    assert plan["status"] == "brief_locked"
    assert "insights" not in plan
    assert "data_context" not in plan


# ── 二次审查：事务回滚覆盖 data_context / 校验失败不写缓存 ──

def test_data_context_failure_rolls_back_memory_state(monkeypatch):
    """_build_plan_data_context 失败时，内存状态同样回滚（不只 _save_state）"""
    monkeypatch.setattr(service, "_resolve_insight_bundle", _fake_resolve)
    _patch_full_agents(monkeypatch)

    def boom(plan, bundle):
        raise ValueError("dc build failed")

    monkeypatch.setattr(service, "_build_plan_data_context", boom)

    plan = _make_plan("p_dcrollback")
    with pytest.raises(ValueError):
        service.generate_insights(plan)

    # 事务回滚：状态仍为 brief_locked，且未写入 insights / data_context
    assert plan["status"] == "brief_locked"
    assert "insights" not in plan
    assert "data_context" not in plan


def test_cache_not_written_when_final_schema_validation_fails(monkeypatch):
    """最终 schema 校验失败 → 不写可命中缓存、不推进状态（先校验后写缓存）"""
    monkeypatch.setattr(service, "_resolve_insight_bundle", _fake_resolve)
    _patch_full_agents(monkeypatch)

    def fail_validate(*a, **k):
        raise ValueError("schema invalid at final step")

    monkeypatch.setattr(service.InsightBundle, "model_validate", fail_validate)

    plan = _make_plan("p_cachenowrite")
    ck = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    with pytest.raises(ValueError):
        service.generate_insights(plan)

    # 最终校验失败 → 缓存未被写入（可命中缓存应为 None）
    assert insight_cache.get(ck) is None
    # 状态未推进
    assert plan["status"] == "brief_locked"
    assert "insights" not in plan


# ── 三次审查：落盘失败不写共享缓存（严格原子性） ──

def test_cache_not_written_when_save_fails(monkeypatch):
    """落盘失败时，共享缓存不写入（缓存仅在落盘成功后才写）"""
    monkeypatch.setattr(service, "_resolve_insight_bundle", _fake_resolve)
    _patch_full_agents(monkeypatch)

    def boom():
        raise OSError("disk full")

    monkeypatch.setattr(service, "_save_state", boom)

    plan = _make_plan("p_savefail_cache")
    ck = insight_cache.cache_key("雨伞", "d1", "s1", "c1")
    with pytest.raises(OSError):
        service.generate_insights(plan)

    # 落盘失败 → 缓存未被写入（可命中缓存为 None）
    assert insight_cache.get(ck) is None
    assert plan["status"] == "brief_locked"

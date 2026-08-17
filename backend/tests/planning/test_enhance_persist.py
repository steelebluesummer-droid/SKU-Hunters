"""Stage 12A·后续 一阶段 · 旧任务 GET 懒补增强结果持久化

验证 get_insights 对「已有 insights 但缺增强」的旧任务：
- 第一次 GET 补齐增强结果并落盘（enhance_state 记录确定性状态）；
- 模拟重启（清空内存 + 从文件 reload）后增强结果与状态仍保留；
- 第二次 GET 不再触发 LLM；
- LLM 失败时不写入伪造结果（只记 error 状态 + caveat）；
- 两个并发 GET 不产生重复写入或状态覆盖（plan 写锁串行化）。
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.planning import repository, service


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    snapshot = dict(repository._PLANS)
    repository._PLANS.clear()
    monkeypatch.setattr(repository, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(repository, "_STATE_FILE", tmp_path / "plans_state.json")
    monkeypatch.setattr(repository, "_LEGACY_STATE_FILE", tmp_path / "legacy_plans_state.json")
    # 洞察缓存同样隔离到 tmp_path：避免全量跑时命中其他用例写入的共享缓存
    from app.planning import insight_cache
    monkeypatch.setattr(insight_cache, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(insight_cache, "_CACHE_FILE", tmp_path / "cache" / "insight_analysis_cache.json")
    yield
    repository._PLANS.clear()
    repository._PLANS.update(snapshot)


def _make_legacy_plan(pid="p_legacy"):
    """模拟旧任务：已有 insights（含 trendRadar/dataContext），缺增强节点"""
    plan = {
        "plan_id": pid,
        "brief": {"category": "雨伞", "mode": "live", "costLimit": 25},
        "mode": "live",
        "status": "insights_ready",
        "created_at": "2026-08-16T00:00:00+00:00",
        "insights": {
            "trendRadar": {"processLog": []},
            "dataContext": {"snapshot_id": "snap1", "summary_snapshot_id": "s1", "competitor_snapshot_id": "c1"},
        },
    }
    repository._PLANS[pid] = plan
    return plan


# ── 成功 fake agents：competitiveMap / assetFit 补齐，pool/cv/enrichment 失败 ──

def _patch_agents(monkeypatch, cm_ret, af_ret, pool_ret=([], []), cv_ret=None, enrich_ret=None, counter=None):
    def _wrapped(fn, name):
        def wrapper(*a, **k):
            if counter is not None:
                counter[name] = counter.get(name, 0) + 1
            return fn(*a, **k)
        return wrapper

    _pool_fn = _wrapped(lambda *a, **k: pool_ret, "pool")
    monkeypatch.setattr(
        "app.planning.opportunity_discovery.build_opportunity_pool", _pool_fn
    )
    # service 通过 from-import 绑定函数，需同时 patch service 侧引用才真正生效
    monkeypatch.setattr("app.planning.service.build_opportunity_pool", _pool_fn)
    monkeypatch.setattr(
        "app.planning.consumer_voice_agent.build_consumer_voice_chains",
        _wrapped(lambda *a, **k: cv_ret, "cv"),
    )
    monkeypatch.setattr(
        "app.planning.competitive_map_agent.build_competitive_map_analysis",
        _wrapped(lambda *a, **k: cm_ret, "cm"),
    )
    monkeypatch.setattr(
        "app.planning.asset_fit_agent.build_asset_fit",
        _wrapped(lambda *a, **k: af_ret, "af"),
    )
    monkeypatch.setattr(
        "app.planning.insight_enrichment.build_enrichment",
        _wrapped(lambda *a, **k: enrich_ret, "enrich"),
    )


def _success_cm():
    return {"needDimensions": ["轻量", "防晒"], "needSatisfaction": [], "opportunityGaps": []}


def _success_af():
    return [{"opportunity_id": "p1"}]


# ── ① 第一次 GET 补齐增强结果并持久化 ─────────────────

def test_first_get_fills_enhancements_and_persists(monkeypatch):
    plan = _make_legacy_plan()
    _patch_agents(monkeypatch, _success_cm(), _success_af())

    service.get_insights(plan)

    b = plan["insights"]
    assert b["competitiveMap"]["needDimensions"] == ["轻量", "防晒"]
    assert b["assetFit"] == [{"opportunity_id": "p1"}]
    es = plan["enhance_state"]
    assert es["competitiveMap"]["status"] == "ok"
    assert es["assetFit"]["status"] == "ok"
    assert es["opportunityPool"]["status"] == "error"  # pool 失败（返回空）→ 记 error 不伪造
    # 已落盘：文件内容含增强与状态
    payload = repository._load_state()
    reloaded = payload["p_legacy"]
    assert reloaded["insights"]["competitiveMap"]["needDimensions"] == ["轻量", "防晒"]
    assert reloaded["enhance_state"]["assetFit"]["status"] == "ok"


# ── ② 清空内存后重新加载仍保留增强结果 ─────────────────

def test_reload_keeps_enhancements_and_state(monkeypatch):
    plan = _make_legacy_plan()
    _patch_agents(monkeypatch, _success_cm(), _success_af())
    service.get_insights(plan)

    # 模拟重启：清空内存，从文件恢复
    repository._PLANS.clear()
    loaded = repository._load_state()
    reloaded_plan = loaded["p_legacy"]
    assert reloaded_plan["insights"]["competitiveMap"]["needDimensions"] == ["轻量", "防晒"]
    assert reloaded_plan["insights"]["assetFit"] == [{"opportunity_id": "p1"}]
    assert reloaded_plan["enhance_state"]["competitiveMap"]["status"] == "ok"
    assert reloaded_plan["enhance_state"]["assetFit"]["status"] == "ok"


# ── ③ 第二次 GET 不再调用 LLM ─────────────────────────

def test_second_get_does_not_retrigger_llm(monkeypatch):
    plan = _make_legacy_plan()
    counter = {}
    _patch_agents(monkeypatch, _success_cm(), _success_af(), counter=counter)
    service.get_insights(plan)
    assert counter.get("cm", 0) == 1

    # 第二次 GET：enhance_state 已 ok → 不再调 agent
    service.get_insights(plan)
    assert counter.get("cm", 0) == 1
    assert counter.get("af", 0) == 1
    assert counter.get("enrich", 0) == 1  # enrich 失败记 error 后也不再重试


# ── ④ LLM 失败时不写入伪造结果 ─────────────────────────

def test_llm_failure_does_not_write_fake_results(monkeypatch):
    plan = _make_legacy_plan()
    _patch_agents(monkeypatch, None, None)  # cm/af 全失败

    service.get_insights(plan)

    b = plan["insights"]
    assert not b.get("competitiveMap", {}).get("needDimensions")
    assert not b.get("assetFit")
    es = plan["enhance_state"]
    assert es["competitiveMap"]["status"] == "error"
    assert es["assetFit"]["status"] == "error"
    # 落盘后无伪造增强
    payload = repository._load_state()
    rb = payload["p_legacy"]["insights"]
    assert not rb.get("competitiveMap", {}).get("needDimensions")
    assert not rb.get("assetFit")


# ── ⑤ 两个并发 GET 不产生重复写入或状态覆盖 ─────────────

def test_concurrent_gets_serialized_no_dup_write(monkeypatch):
    plan = _make_legacy_plan()
    counter = {}
    _patch_agents(monkeypatch, _success_cm(), _success_af(), counter=counter)

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(service.get_insights, plan) for _ in range(2)]
        [f.result(timeout=20) for f in futs]

    # 锁串行化：第一个补齐并记录状态，第二个进入时已 ok → cm 只调 1 次
    assert counter.get("cm", 0) == 1
    assert plan["enhance_state"]["competitiveMap"]["status"] == "ok"
    assert plan["insights"]["competitiveMap"]["needDimensions"] == ["轻量", "防晒"]
    # 落盘一致
    payload = repository._load_state()
    assert payload["p_legacy"]["enhance_state"]["competitiveMap"]["status"] == "ok"


# ── P1-4：旧任务增强失败按时间退避重试 ──────────────

def test_enhance_error_retried_after_backoff(monkeypatch):
    """error 节点冷却期内不重试；超过冷却期后允许重试（一次临时故障不永久放弃）"""
    from datetime import datetime, timedelta, timezone

    plan = _make_legacy_plan("p_retry")
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(seconds=30)).isoformat()
    old = (now - timedelta(seconds=400)).isoformat()
    plan["enhance_state"] = {
        "opportunityPool": {"status": "ok", "ts": recent},
        "consumerVoice": {"status": "ok", "ts": recent},
        "assetFit": {"status": "ok", "ts": recent},
        "enrichment": {"status": "ok", "ts": recent},
        "competitiveMap": {"status": "error", "ts": recent, "caveat": "LLM 不可用"},
    }
    counter = {}
    _patch_agents(monkeypatch, _success_cm(), _success_af(), counter=counter)

    # 冷却期内：不重试，competitiveMap 保持 error，cm agent 未被调用
    service.get_insights(plan)
    assert plan["enhance_state"]["competitiveMap"]["status"] == "error"
    assert counter.get("cm", 0) == 0

    # 超过冷却期：允许重试 → cm agent 被调用，成功则节点转 ok
    plan["enhance_state"]["competitiveMap"]["ts"] = old
    service.get_insights(plan)
    assert counter.get("cm", 0) == 1
    assert plan["enhance_state"]["competitiveMap"]["status"] == "ok"


# ── 三次审查：无时间戳的 error 节点允许重试（不永久放弃） ──

def test_enhance_error_without_ts_is_retried(monkeypatch):
    """旧数据 error 节点缺少 ts 时，允许重试并补写时间戳（避免永久跳过）"""
    plan = _make_legacy_plan("p_nots")
    plan["enhance_state"] = {
        "opportunityPool": {"status": "ok", "ts": "x"},
        "consumerVoice": {"status": "ok", "ts": "x"},
        "assetFit": {"status": "ok", "ts": "x"},
        "enrichment": {"status": "ok", "ts": "x"},
        "competitiveMap": {"status": "error"},  # 无 ts 的旧错误节点
    }
    counter = {}
    _patch_agents(monkeypatch, _success_cm(), _success_af(), counter=counter)

    service.get_insights(plan)
    # 无 ts → 允许重试：cm agent 被调用，成功后转 ok 并补写 ts
    assert counter.get("cm", 0) == 1
    assert plan["enhance_state"]["competitiveMap"]["status"] == "ok"
    assert "ts" in plan["enhance_state"]["competitiveMap"]

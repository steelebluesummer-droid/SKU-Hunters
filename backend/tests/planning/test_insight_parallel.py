"""Stage 12A · 洞察链路并行化测试（fake LLM + 可控 sleep）

验证 competitive map 与 asset fit 在 consumerVoice 完成后并行执行：
- 并行阶段耗时接近 max(A,B)，而非 A+B；
- 任一 Agent 失败只影响对应模块，写入 processLog caveat，不污染其他模块；
- 输出结构一致。
"""
import time

from app.planning import service


def _make_live_plan():
    return {
        "plan_id": "p_parallel",
        "brief": {"category": "风扇", "mode": "live", "costLimit": 25},
    }


def _make_bundle():
    """已含 opportunityPool + consumerVoice（并行前置已完成）"""
    return {
        "opportunityPool": [{"id": "p1"}],
        "consumerVoice": {"painPointChains": [{"id": "c1"}]},
        "competitiveMap": {},   # 无 needDimensions → 需要计算
        "assetFit": [],          # 空列表 → 需要计算
        "trendRadar": {"processLog": []},
        "dataContext": {"snapshot_id": "snap1"},
    }


def test_parallel_competitive_asset_takes_about_max(monkeypatch):
    """两个 0.3s 的 agent 并行，总耗时接近 max≈0.3s（而非 0.6s）"""
    def fake_cm(category, snapshot, brief):
        time.sleep(0.3)
        return {"needDimensions": [{"name": "d1"}], "needSatisfaction": [], "opportunityGaps": []}

    def fake_af(category, snapshot, brief):
        time.sleep(0.3)
        return [{"concept": "x", "designLanguage": ""}]

    monkeypatch.setattr("app.planning.competitive_map_agent.build_competitive_map_analysis", fake_cm)
    monkeypatch.setattr("app.planning.asset_fit_agent.build_asset_fit", fake_af)

    plan = _make_live_plan()
    bundle = _make_bundle()
    t0 = time.monotonic()
    service._ensure_parallel_competitive_asset(plan, bundle, "feishu", "snap1")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"并行耗时 {elapsed:.2f}s 应接近 max(A,B)≈0.3s（串行会约 0.6s）"
    # 输出结构一致
    assert bundle["competitiveMap"]["needDimensions"] == [{"name": "d1"}]
    assert bundle["assetFit"] == [{"concept": "x", "designLanguage": ""}]


def test_parallel_one_failure_does_not_pollute_other(monkeypatch):
    """competitive map 失败、asset fit 成功 → 失败只写 caveat，不污染 asset fit"""
    def fake_cm(category, snapshot, brief):
        return None  # 失败（LLM 不可用）

    def fake_af(category, snapshot, brief):
        return [{"concept": "x", "designLanguage": ""}]

    monkeypatch.setattr("app.planning.competitive_map_agent.build_competitive_map_analysis", fake_cm)
    monkeypatch.setattr("app.planning.asset_fit_agent.build_asset_fit", fake_af)

    plan = _make_live_plan()
    bundle = _make_bundle()
    service._ensure_parallel_competitive_asset(plan, bundle, "feishu", "snap1")
    # asset fit 正常写入
    assert bundle["assetFit"] == [{"concept": "x", "designLanguage": ""}]
    # competitive map 失败：不写 needDimensions，只写 processLog caveat
    assert "needDimensions" not in bundle["competitiveMap"]
    assert any("竞品满足矩阵生成失败" in str(p) for p in bundle["trendRadar"]["processLog"])


def test_parallel_both_configured_only_one_required(monkeypatch):
    """assetFit 已存在 → 只计算 competitive map，asset fit 保留原值"""
    def fake_cm(category, snapshot, brief):
        return {"needDimensions": [{"name": "d1"}], "needSatisfaction": [], "opportunityGaps": []}

    monkeypatch.setattr("app.planning.competitive_map_agent.build_competitive_map_analysis", fake_cm)

    plan = _make_live_plan()
    bundle = _make_bundle()
    bundle["assetFit"] = [{"concept": "已存在", "designLanguage": ""}]  # 已有 → 不重新计算
    service._ensure_parallel_competitive_asset(plan, bundle, "feishu", "snap1")
    assert bundle["assetFit"] == [{"concept": "已存在", "designLanguage": ""}]
    assert bundle["competitiveMap"]["needDimensions"] == [{"name": "d1"}]

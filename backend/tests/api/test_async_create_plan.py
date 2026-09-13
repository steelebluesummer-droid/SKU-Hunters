"""异步新建企划端点测试 — POST /plans/async：立即 202 + 后台阶段推进 + 失败落 failed"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.planning import router
from app.planning import pipeline, repository

app = FastAPI()
app.include_router(router)

BRIEF = {
    "theme": "2027夏季户外生活系列",
    "category": "小风扇",
    "price_range": [39, 99],
}


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    """异步后台任务使用临时状态文件，避免测试竞争真实运行态 JSON。"""
    snapshot = dict(repository._PLANS)
    repository._PLANS.clear()
    monkeypatch.setattr(repository, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(repository, "_STATE_FILE", tmp_path / "plans_state.json")
    monkeypatch.setattr(repository, "_LEGACY_STATE_FILE", tmp_path / "legacy_plans_state.json")
    yield
    repository._PLANS.clear()
    repository._PLANS.update(snapshot)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_async_create_returns_202_running_and_completes(client):
    """立即返回 running；后台跑完洞察+机会，stage=done、状态 opportunities_ready"""
    r = client.post("/api/v1/plans/async", json=BRIEF)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "running"
    plan_id = body["plan_id"]

    # TestClient 在响应返回前执行 BackgroundTasks
    plan = pipeline.get_plan(plan_id)
    assert plan is not None
    assert plan["status"] == "opportunities_ready"
    assert plan["stage"] == "done"

    # 详情端点透出 stage
    detail = client.get(f"/api/v1/plans/{plan_id}").json()
    assert detail["stage"] == "done"
    assert detail["error_summary"] == ""


def test_async_create_failure_marks_plan_failed(client, monkeypatch):
    """管线异常 → plan 落 failed，stage=failed，带错误摘要；进程不崩"""
    def _boom(plan):
        raise RuntimeError("数据源断开")

    monkeypatch.setattr(pipeline, "generate_insights", _boom)

    r = client.post("/api/v1/plans/async", json=BRIEF)
    assert r.status_code == 202, r.text
    plan_id = r.json()["plan_id"]

    plan = pipeline.get_plan(plan_id)
    assert plan["status"] == "failed"
    assert plan["stage"] == "failed"
    assert "失败" in plan["error_summary"]

    detail = client.get(f"/api/v1/plans/{plan_id}").json()
    assert detail["status"] == "failed"
    assert detail["error_summary"]

    # 列表也能看到 failed 任务与 stage
    plans = client.get("/api/v1/plans").json()["plans"]
    mine = [p for p in plans if p["plan_id"] == plan_id]
    assert mine and mine[0]["status"] == "failed" and mine[0]["stage"] == "failed"


def test_async_create_invalid_brief_returns_422(client):
    """BRIEF 校验失败 → 422，不建档不跑后台"""
    r = client.post("/api/v1/plans/async", json={"theme": "缺字段"})
    assert r.status_code == 422


def test_sync_create_endpoint_untouched(client):
    """既有同步端点 POST /plans 契约不变：201 + brief_locked（同步建档）"""
    r = client.post("/api/v1/plans", json=BRIEF)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "brief_locked"
    # 同步创建无 stage
    plan = pipeline.get_plan(body["plan_id"])
    assert not plan.get("stage")

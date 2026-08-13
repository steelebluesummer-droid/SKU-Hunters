"""企划工作室 API 端点测试 — HTTP 层契约与错误路径

管线逻辑由 tests/planning/test_pipeline.py 锁定；本文件锁 HTTP 层：
状态码、错误码（BRIEF_INVALID/PLAN_NOT_FOUND/OPPORTUNITY_*…）、响应形状。
"""

import pytest
from app.api.planning import router
from app.planning import pipeline
from fastapi import FastAPI
from fastapi.testclient import TestClient

VALID_BRIEF = {
    "theme": "2027夏季户外生活系列",
    "category": "小风扇",
    "priceRange": [39, 99],
    "costLimit": 25,
}


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    snapshot = dict(pipeline._PLANS)
    pipeline._PLANS.clear()
    monkeypatch.setattr(pipeline, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "_STATE_FILE", tmp_path / "plans_state.json")
    yield
    pipeline._PLANS.clear()
    pipeline._PLANS.update(snapshot)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _create(client, brief=None) -> str:
    resp = client.post("/api/v1/plans", json={"brief": brief or dict(VALID_BRIEF)})
    assert resp.status_code == 201
    return resp.json()["plan_id"]


# ── ① 创建任务 ───────────────────────────────────────────


def test_create_plan_201_camelcase_roundtrip(client):
    plan_id = _create(client)
    detail = client.get(f"/api/v1/plans/{plan_id}").json()
    assert detail["status"] == "brief_locked"
    # camelCase 契约不得被吞（回归：alias 修复）；内部存储为 snake_case
    assert detail["brief"]["cost_limit"] == 25
    assert detail["brief"]["price_range"] == [39, 99]


def test_create_plan_accepts_bare_brief(client):
    """兼容直接传 brief（不包一层 {"brief": ...}）"""
    resp = client.post("/api/v1/plans", json=dict(VALID_BRIEF))
    assert resp.status_code == 201


def test_create_plan_422_on_invalid_brief(client):
    resp = client.post("/api/v1/plans", json={"brief": {"category": "小风扇"}})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "BRIEF_INVALID"


# ── 404 路径 ─────────────────────────────────────────────


def test_plan_not_found_404(client):
    resp = client.get("/api/v1/plans/no-such-plan")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "PLAN_NOT_FOUND"


def test_insights_opportunities_404_on_missing_plan(client):
    for path in ("insights", "opportunities"):
        resp = client.get(f"/api/v1/plans/no-such-plan/{path}")
        assert resp.status_code == 404


# ── ②③ 洞察与机会 ────────────────────────────────────────


def test_insights_shape(client):
    plan_id = _create(client)
    resp = client.get(f"/api/v1/plans/{plan_id}/insights")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_id"] == plan_id
    assert set(body) >= {"trendRadar", "consumerVoice", "competitiveMap", "insightBase", "trendGallery"}
    assert body["trendRadar"]["processLog"]


def test_opportunities_carry_process_log(client):
    plan_id = _create(client)
    body = client.get(f"/api/v1/plans/{plan_id}/opportunities").json()
    assert len(body["opportunities"]) == 3
    assert len(body["processLog"]) == 4  # 机会生成思考过程（导师专项）


# ── ④⑤⑥ 企划卡 ─────────────────────────────────────────


def test_plan_card_requires_opportunity_id(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/plan-card", json={})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "OPPORTUNITY_REQUIRED"


def test_plan_card_404_on_unknown_opportunity(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/plan-card", json={"opportunity_id": "opp_1"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "OPPORTUNITY_NOT_FOUND"


def test_plan_card_ok_with_cost_check_and_process_log(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/plan-card", json={"opportunity_id": "ip-collect"})
    assert resp.status_code == 200
    card = resp.json()["plan_card"]
    assert card["costCheck"]["passed"] is True
    assert card["processLog"][-1].startswith("成本校验：")
    # 状态推进
    assert client.get(f"/api/v1/plans/{plan_id}").json()["status"] == "plan_card_ready"


# ── 改稿与归档的状态机约束 ────────────────────────────────


def test_revise_422_without_message(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/revise", json={"message": "  "})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "MESSAGE_REQUIRED"


def test_revise_409_before_plan_card(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/revise", json={"message": "配色柔和一点"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "PLAN_CARD_NOT_READY"


def test_archive_409_before_plan_card(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/archive")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "PLAN_CARD_NOT_READY"


def test_full_chain_create_to_archive(client):
    plan_id = _create(client)
    client.post(f"/api/v1/plans/{plan_id}/plan-card", json={"opportunity_id": "healing-nature"})
    revise = client.post(f"/api/v1/plans/{plan_id}/revise", json={"message": "加一个挂绳"})
    assert revise.status_code == 200
    assert revise.json()["reply"]
    archive = client.post(f"/api/v1/plans/{plan_id}/archive")
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"
    # 归档后只读接口不降级状态
    client.get(f"/api/v1/plans/{plan_id}/insights")
    assert client.get(f"/api/v1/plans/{plan_id}").json()["status"] == "archived"


# ── 策展数据独立页 ────────────────────────────────────────


def test_curated_pages(client):
    assert client.get("/api/v1/insight-base").json()["hitProducts"]
    assert client.get("/api/v1/trend-gallery").json()["colors"]
    assert client.get("/api/v1/data-board").json()["categoryRank"]

"""洞察生成失败错误契约测试 — 失败可见性（Stage 12B 前置修复）

锁定：
1. action_generate_insights 对已知异常返回结构化错误（code/message/plan_id/request_id）；
2. 失败后 plan.status 保持 brief_locked（不推进、不落盘半成品）；
3. 未知异常 → 500 INTERNAL_ERROR，不泄露内部细节；
4. 不打印 token/prompt/完整原始数据（响应体不含密钥字段）。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import planning as planning_api
from app.api.planning import router
from app.data.base_adapter import BaseProviderError, BaseUnavailable
from app.planning import repository
from app.planning.insight_resolver import LLMGenerationError
from app.planning.service import StateTransitionError

VALID_BRIEF = {
    "theme": "2027夏季户外生活系列",
    "category": "小风扇",
    "priceRange": [39, 99],
    "costLimit": 25,
}


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
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
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _create(client) -> str:
    resp = client.post("/api/v1/plans", json={"brief": dict(VALID_BRIEF)})
    assert resp.status_code == 201
    return resp.json()["plan_id"]


def _assert_structured_error(resp, status, code):
    assert resp.status_code == status
    err = resp.json()["detail"]["error"]
    assert err["code"] == code
    assert isinstance(err.get("message"), str) and err["message"]
    assert err.get("plan_id")
    assert err.get("request_id")
    return err


def test_llm_failure_503_contract_status_stays_brief_locked(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise LLMGenerationError("LLM 服务不可用")

    monkeypatch.setattr(planning_api.pipeline, "generate_insights", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-insights")
    err = _assert_structured_error(resp, 503, "LLM_UNAVAILABLE")
    assert err["plan_id"] == plan_id
    # 前端只返回固定文案，不泄露底层异常文本
    assert err["message"] == "AI 洞察生成暂时不可用，请稍后重试"
    assert "LLM 服务不可用" not in err["message"]
    # 失败后状态仍为 brief_locked（不推进、不落盘半成品）
    assert client.get(f"/api/v1/plans/{plan_id}").json()["status"] == "brief_locked"


def test_base_unavailable_503_contract(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise BaseUnavailable("飞书数据源不可用")

    monkeypatch.setattr(planning_api.pipeline, "generate_insights", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-insights")
    _assert_structured_error(resp, 503, "BASE_UNAVAILABLE")
    assert client.get(f"/api/v1/plans/{plan_id}").json()["status"] == "brief_locked"


def test_base_provider_error_503_contract(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise BaseProviderError("飞书返回异常")

    monkeypatch.setattr(planning_api.pipeline, "generate_insights", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-insights")
    _assert_structured_error(resp, 503, "BASE_UNAVAILABLE")
    assert client.get(f"/api/v1/plans/{plan_id}").json()["status"] == "brief_locked"


def test_unknown_exception_500_contract(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise RuntimeError("unexpected internal bug")

    monkeypatch.setattr(planning_api.pipeline, "generate_insights", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-insights")
    err = _assert_structured_error(resp, 500, "INTERNAL_ERROR")
    assert err["plan_id"] == plan_id
    # 未知异常不向前端泄露内部细节
    assert "unexpected internal bug" not in err["message"]
    assert client.get(f"/api/v1/plans/{plan_id}").json()["status"] == "brief_locked"


def test_success_200_status_insights_ready(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-insights")
    assert resp.status_code == 200
    assert resp.json()["status"] == "insights_ready"
    assert resp.json()["plan_id"] == plan_id


def test_failure_response_contains_no_secrets(client, monkeypatch):
    """响应体不泄露异常中的 URL/Token/请求内容"""
    plan_id = _create(client)
    # 构造一个含敏感信息的底层异常，验证前端响应不会原样回显
    leaky_msg = (
        "GET https://open.feishu.cn/open-apis/base/v1/tables?app_token=secret_tok_123 "
        "HTTP 401 APP_SECRET invalid sk-live-abcdef123456 "
        "body: {\"prompt\": \"secret prompt\"}"
    )

    def boom(plan):
        raise LLMGenerationError(leaky_msg)

    monkeypatch.setattr(planning_api.pipeline, "generate_insights", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-insights")
    body = resp.text
    # 异常中的 URL、token、secret、prompt 片段均不得出现在响应体
    assert "secret_tok_123" not in body
    assert "sk-live-abcdef123456" not in body
    assert "secret prompt" not in body
    assert "open.feishu.cn" not in body
    # 返回的是固定脱敏文案
    assert "AI 洞察生成暂时不可用，请稍后重试" in body


# ── 三次审查补充：opportunities / revise / archive 统一错误契约 ──

def _assert_code_message(resp, status, code, message):
    """无 plan_id/request_id 的通用错误契约断言（code + 固定 message）"""
    assert resp.status_code == status
    err = resp.json()["detail"]["error"]
    assert err["code"] == code
    assert err["message"] == message
    return err


def test_generate_opportunities_state_transition_409(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise StateTransitionError("brief_locked", "insights_ready", "generate-opportunities")

    monkeypatch.setattr(planning_api.pipeline, "generate_opportunities", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-opportunities")
    _assert_code_message(resp, 409, "INVALID_TRANSITION", "当前任务状态不允许执行该操作")


def test_generate_opportunities_llm_503(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise LLMGenerationError("LLM 服务不可用 secret_tok_123")

    monkeypatch.setattr(planning_api.pipeline, "generate_opportunities", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-opportunities")
    _assert_code_message(resp, 503, "LLM_UNAVAILABLE", "AI 洞察生成暂时不可用，请稍后重试")
    # 不泄露底层异常文本
    assert "secret_tok_123" not in resp.text


def test_generate_opportunities_base_503(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise BaseUnavailable("飞书数据源不可用")

    monkeypatch.setattr(planning_api.pipeline, "generate_opportunities", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/generate-opportunities")
    _assert_code_message(resp, 503, "BASE_UNAVAILABLE", "数据源暂时不可用，请稍后重试")


def test_revise_requires_message_422(client):
    plan_id = _create(client)
    resp = client.post(f"/api/v1/plans/{plan_id}/revise", json={})
    _assert_code_message(resp, 422, "MESSAGE_REQUIRED", "message 必填")


def test_revise_state_transition_409(client, monkeypatch):
    plan_id = _create(client)
    repository._PLANS[plan_id]["plan_card"] = {"card": {}}

    def boom(plan, message):
        raise StateTransitionError("insights_ready", "brief_locked", "revise")

    monkeypatch.setattr(planning_api.pipeline, "revise_plan", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/revise", json={"message": "调整定价"})
    _assert_code_message(resp, 409, "INVALID_TRANSITION", "当前任务状态不允许执行该操作")


def test_archive_state_transition_409(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise StateTransitionError("insights_ready", "brief_locked", "archive")

    monkeypatch.setattr(planning_api.pipeline, "archive_plan", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/archive")
    _assert_code_message(resp, 409, "INVALID_TRANSITION", "当前任务状态不允许执行该操作")


def test_archive_plan_card_not_ready_409(client, monkeypatch):
    plan_id = _create(client)

    def boom(plan):
        raise ValueError("no plan card")

    monkeypatch.setattr(planning_api.pipeline, "archive_plan", boom)
    resp = client.post(f"/api/v1/plans/{plan_id}/actions/archive")
    _assert_code_message(resp, 409, "PLAN_CARD_NOT_READY", "企划卡尚未就绪，无法执行此操作")


# ── 三次审查补充：BRIEF_INVALID 字段级脱敏，不回显输入值 ──

def test_brief_invalid_field_level_sanitized(client):
    """BRIEF 校验失败返回字段级固定错误，不回显用户输入值"""
    secret_value = "sk-live-supersecret"
    resp = client.post(
        "/api/v1/plans",
        json={
            "brief": {
                "theme": "主题",
                "category": "小风扇",
                "priceRange": secret_value,  # 类型错误，原 str(e) 会回显该值
                "costLimit": 25,
            }
        },
    )
    assert resp.status_code == 422
    err = resp.json()["detail"]["error"]
    assert err["code"] == "BRIEF_INVALID"
    assert err["message"].startswith("企划约束不合法")
    # 不回显用户输入值
    assert secret_value not in resp.text

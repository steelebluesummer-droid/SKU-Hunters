"""Stage 12A·后续 三阶段 · 统一 LLM 重试策略测试

验证重试分层纪律：
- 网络/超时/空响应重试只由 llm.complete 负责；调用方收到 None 后直接 break，不叠加 range(2)。
- JSON/契约失败由调用方负责（range(2) 重试），但不触发 llm.complete 内部的网络重试叠加。
- 空响应不产生无限重试。
- LLM_TIMEOUT / LLM_MAX_RETRIES 非法时用安全默认，不崩溃。
- 失败日志含 node / status / elapsed_ms，不含 prompt。
- strict real 失败返回 None，不伪造结果。
"""
import logging

import openai

from app.engine import llm as llm_mod
from app.planning.consumer_voice_agent import build_consumer_voice_chains


def _cv_bundle():
    return {
        "consumerVoice": {"painPoints": [{"text": "伞面易翻"}], "quotes": []},
        "opportunityPool": [],
    }


# ── ① 网络/超时失败：调用方不叠加重试 ─────────────────

def test_network_failure_no_caller_stack(monkeypatch):
    calls = {"n": 0}
    def fake_complete(*a, **k):
        calls["n"] += 1
    monkeypatch.setattr("app.engine.llm.complete", fake_complete)
    res = build_consumer_voice_chains("雨伞", _cv_bundle(), {})
    assert res is None
    assert calls["n"] == 1  # 调用方收到 None → break，不再 range(2) 叠加


# ── ② JSON/契约失败：调用方重试 range(2)，不叠加底层 ──

def test_json_failure_retries_in_caller(monkeypatch):
    calls = {"n": 0}
    def fake_complete(*a, **k):
        calls["n"] += 1
        return "not valid json"
    monkeypatch.setattr("app.engine.llm.complete", fake_complete)
    res = build_consumer_voice_chains("雨伞", _cv_bundle(), {})
    assert res is None
    assert calls["n"] == 2  # JSON 契约失败 → 调用方重试一次（range(2)）


# ── ③ 空响应不产生无限重试 ───────────────────────────

def test_empty_response_not_infinite(monkeypatch):
    calls = {"n": 0}
    def fake_complete(*a, **k):
        calls["n"] += 1
    monkeypatch.setattr("app.engine.llm.complete", fake_complete)
    build_consumer_voice_chains("雨伞", _cv_bundle(), {})
    assert calls["n"] == 1  # 一次即止，不无限重试


# ── ④ 非法环境变量用安全默认 ─────────────────────────

def test_illegal_env_safe_defaults(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "abc")
    monkeypatch.setenv("LLM_MAX_RETRIES", "xyz")
    assert llm_mod._env_float("LLM_TIMEOUT", 45.0, "LLM_TIMEOUT") == 45.0
    assert llm_mod._env_int("LLM_MAX_RETRIES", 1, "LLM_MAX_RETRIES") == 1


# ── ⑤ 失败日志含节点和耗时 ───────────────────────────

def test_llm_log_contains_node_and_elapsed(caplog, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    caplog.set_level(logging.INFO, logger="llm")

    class FakeCreate:
        def __call__(self, **kw):
            raise TimeoutError("timeout")

    class FakeCompletions:
        create = FakeCreate()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: FakeClient())
    llm_mod.complete("s", "u", node="test_node")

    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert "test_node" in joined
    assert '"status"' in joined
    assert "elapsed_ms" in joined
    assert '"reason": "TimeoutError"' in joined
    # 不打印完整 prompt / 密钥
    assert "your_key" not in joined and "api_key" not in joined


# ── ⑥ strict real 失败不返回 Mock/fixture ─────────────

def test_failure_returns_none_not_mock(monkeypatch):
    calls = {"n": 0}
    def fake_complete(*a, **k):
        calls["n"] += 1
    monkeypatch.setattr("app.engine.llm.complete", fake_complete)
    res = build_consumer_voice_chains("雨伞", _cv_bundle(), {})
    # 失败返回 None（调用方降级），而非伪造 consumerVoice 结果
    assert res is None

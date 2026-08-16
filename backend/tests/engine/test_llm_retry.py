"""Stage 12A · LLM 超时与重试测试（mock OpenAI client）

验证：
- 单次失败后重试成功；
- 连续失败（含重试）返回 None（降级，不包装成 success）；
- LLM_TIMEOUT / LLM_MAX_RETRIES 环境变量生效并传给 client。
"""
import openai

from app.engine import llm as llm_mod


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.content = content
        self.choices = [_Choice(content)]


def test_llm_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm_mod.complete("s", "u") is None


def test_llm_retry_success_on_second(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    calls = {"n": 0}

    class FakeCreate:
        def __call__(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("simulated timeout")
            return _Resp("ok")

    class FakeCompletions:
        create = FakeCreate()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: FakeClient())
    assert llm_mod.complete("s", "u") == "ok"
    assert calls["n"] == 2  # 首次失败 + 重试成功


def test_llm_retry_all_fail_returns_none(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    calls = {"n": 0}

    class FakeCreate:
        def __call__(self, **kw):
            calls["n"] += 1
            raise TimeoutError("always fail")

    class FakeCompletions:
        create = FakeCreate()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: FakeClient())
    assert llm_mod.complete("s", "u") is None  # 失败不包装成 success
    assert calls["n"] == 2  # 默认重试 1 次 → 共 2 次尝试


def test_llm_timeout_env_passed_to_client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_TIMEOUT", "45")
    captured = {}

    class FakeCompletions:
        create = lambda self, **kw: _Resp("ok")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

        def __init__(self, **kw):
            captured["timeout"] = kw.get("timeout")

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: FakeClient(**kw))
    llm_mod.complete("s", "u")
    assert captured["timeout"] == 45


def test_llm_max_retries_env_controls_attempts(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")  # 不重试
    calls = {"n": 0}

    class FakeCreate:
        def __call__(self, **kw):
            calls["n"] += 1
            raise TimeoutError("fail")

    class FakeCompletions:
        create = FakeCreate()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: FakeClient())
    assert llm_mod.complete("s", "u") is None
    assert calls["n"] == 1  # 重试次数=0 → 仅 1 次尝试

"""LLM 客户端 — 多供应商适配，优雅降级

支持任意 OpenAI 兼容接口（智谱/豆包/DeepSeek/通义均为该格式）。
换供应商只改环境变量，不改代码：

    # .env 示例（智谱，开发期免费主力）
    LLM_PROVIDER=zhipu
    LLM_API_KEY=your_key

    # .env 示例（豆包，演示期主力）
    LLM_PROVIDER=volcengine
    LLM_API_KEY=your_key

设计纪律（对应趋势官已验证的降级机制）：
- 无 Key / 调用失败 → 返回 None，由 Agent 的规则引擎兜底
- LLM 是增强层，不是硬依赖——Demo 任何环境下可运行
"""

from __future__ import annotations

import json
import logging
import os
import time

_LOG = logging.getLogger("llm")


# 各供应商的 base_url 与推荐模型（全部为 OpenAI 兼容格式）
PROVIDERS: dict[str, dict[str, str]] = {    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",          # 永久免费，无 Token 上限
    },
    "volcengine": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-flash",         # 演示期主力，贴赛题
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",        # V4 Flash 永久免费
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k3",                # Kimi K3
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-flash",           # 每日免费调用额度
    },
}


def get_llm_config() -> dict[str, str] | None:
    """读取 LLM 配置；未配置返回 None（触发降级）"""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    provider = os.getenv("LLM_PROVIDER", "zhipu")
    preset = PROVIDERS.get(provider, PROVIDERS["zhipu"])
    return {
        "api_key": api_key,
        "base_url": os.getenv("LLM_BASE_URL", preset["base_url"]),
        "model": os.getenv("LLM_MODEL", preset["model"]),
    }


# Prompt 保险丝：连接器 payload 不可控（热搜词条/评论文本可能超长），
# user prompt 超限时取首尾、截中段并显式标记。指令在 system prompt 不受影响。
# 各 Agent 已有条数帽，这是最后一道总量兜底；可用 LLM_MAX_PROMPT_CHARS 覆盖。
MAX_PROMPT_CHARS = int(os.getenv("LLM_MAX_PROMPT_CHARS", "12000"))


def cap_user_prompt(text: str, max_chars: int | None = None) -> str:
    """超长 user prompt 截断：保留首尾（Brief 在头、反馈/历史在尾），截中段。"""
    limit = max_chars if max_chars is not None else MAX_PROMPT_CHARS
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    omitted = len(text) - head - tail
    return (f"{text[:head]}\n……（材料过长，中段 {omitted} 字符已省略）……\n"
            f"{text[-tail:]}")


def _env_float(name: str, default: float, label: str) -> float:
    """读取浮点环境变量；非法时用安全默认并记录配置错误（不崩溃）"""
    raw = os.getenv(name, str(default))
    try:
        v = float(raw)
        return v if v > 0 else default
    except (ValueError, TypeError):
        _LOG.warning("%s 非法（%r），使用安全默认 %s", label, raw, default)
        return default


def _env_int(name: str, default: int, label: str) -> int:
    """读取整数环境变量；非法时用安全默认并记录配置错误（不崩溃）"""
    raw = os.getenv(name, str(default))
    try:
        v = int(raw)
        return v if v >= 0 else default
    except (ValueError, TypeError):
        _LOG.warning("%s 非法（%r），使用安全默认 %s", label, raw, default)
        return default


def complete(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    node: str = "llm",
) -> str | None:
    """统一调用入口。任何失败返回 None——调用方负责降级。

    重试纪律（第三阶段统一）：
    - 网络/超时/空响应重试由本函数负责（最多 LLM_MAX_RETRIES+1 次，默认 2 次）；
    - JSON/契约失败由调用方负责（见各 Agent 的 range(MAX_LLM_CALLS)）；
    - 两者互不叠加：本函数重试完网络失败返回 None 后，调用方**不再**为网络失败重试。

    Args:
        system_prompt: Agent 角色 prompt（prompts/ 目录下的模板）
        user_prompt: 本次任务的具体输入
        temperature: 默认 0.3（决策场景求稳，不求发散）
        max_tokens: 输出上限
        node: 调用节点名（用于结构化日志，不含密钥/完整 prompt）

    Returns:
        模型输出文本；未配置 Key 或调用失败返回 None

    注意：推理模型（如 deepseek-v4-pro）的 reasoning tokens 计入
    max_tokens——预算太小会被思考过程吃光导致返回空串。调用方对
    复杂任务应给 6000+ 预算（实测该类任务 reasoning 约 2000+ tokens）。
    """
    config = get_llm_config()
    if config is None:
        return None

    timeout = _env_float("LLM_TIMEOUT", 45.0, "LLM_TIMEOUT")
    max_retries = _env_int("LLM_MAX_RETRIES", 1, "LLM_MAX_RETRIES")
    try:
        import openai
    except ImportError:  # pragma: no cover
        return None

    for attempt in range(max_retries + 1):
        t0 = time.monotonic()
        try:
            client = openai.OpenAI(
                api_key=config["api_key"],
                base_url=config["base_url"],
                timeout=timeout,
            )
            resp = client.chat.completions.create(
                model=config["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": cap_user_prompt(user_prompt)},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            _LOG.info(json.dumps({
                "event": "llm_call", "node": node,
                "attempt": attempt + 1,
                "status": "success" if content else "error",
                "reason": "" if content else "empty",
                "elapsed_ms": elapsed_ms,
            }, ensure_ascii=False))
            if content:
                return content
        except Exception as exc:  # noqa: BLE001 — LLM 故障刻意降级，不阻塞会议
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            _LOG.info(json.dumps({
                "event": "llm_call", "node": node,
                "attempt": attempt + 1,
                "status": "error",
                "reason": type(exc).__name__,
                "elapsed_ms": elapsed_ms,
            }, ensure_ascii=False))
            # 降级纪律：单次失败未达重试上限则重试，否则返回 None（调用方降级）
            if attempt >= max_retries:
                return None
    return None


def load_prompt(agent_name: str) -> str:
    """加载 prompts/ 目录下的角色模板"""
    from pathlib import Path

    prompt_path = (
        Path(__file__).resolve().parent.parent.parent
        / "prompts" / f"{agent_name}.txt"
    )
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""

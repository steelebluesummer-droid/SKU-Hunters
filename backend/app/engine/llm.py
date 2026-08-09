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

import os

# 各供应商的 base_url 与推荐模型（全部为 OpenAI 兼容格式）
PROVIDERS: dict[str, dict[str, str]] = {
    "zhipu": {
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


def complete(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str | None:
    """统一调用入口。任何失败返回 None——调用方负责降级。

    Args:
        system_prompt: Agent 角色 prompt（prompts/ 目录下的模板）
        user_prompt: 本次任务的具体输入
        temperature: 默认 0.3（决策场景求稳，不求发散）
        max_tokens: 输出上限

    Returns:
        模型输出文本；未配置 Key 或调用失败返回 None
    """
    config = get_llm_config()
    if config is None:
        return None

    try:
        import openai

        client = openai.OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
        )
        resp = client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception:  # noqa: BLE001 — LLM 故障刻意降级，不阻塞会议
        # 降级纪律：LLM 故障不阻塞会议，规则引擎兜底
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

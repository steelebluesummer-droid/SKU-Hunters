"""即梦文生图客户端 — 火山引擎视觉服务（AK/SK V4 签名）

调用链路：CVSync2AsyncSubmitTask 提交任务 → 轮询 CVSync2AsyncGetResult 取图。

环境变量（backend/.env）：
    VOLC_ACCESS_KEY_ID / VOLC_SECRET_ACCESS_KEY  AK/SK（必填，缺则降级）
    JIMENG_REQ_KEY    模型 req_key，默认 jimeng_t2i_v40（即梦图片生成 4.0）
    JIMENG_TIMEOUT    轮询总超时秒数，默认 60

降级纪律（与 LLM 客户端一致）：未配置 Key 或任何调用失败 → 返回 fallback，
不阻塞企划卡生成；前端收到 None 显示占位图。

注意：req_key / 字段名以火山引擎官方文档为准，首次实跑如报错按报错信息调整。
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import os
import time

_HOST = "visual.volcengineapi.com"
_REGION = "cn-north-1"
_SERVICE = "cv"
_VERSION = "2022-08-31"
_ACTION_SUBMIT = "CVSync2AsyncSubmitTask"
_ACTION_QUERY = "CVSync2AsyncGetResult"

_LOGGER = logging.getLogger("services.jimeng")


def _get_config() -> dict[str, str] | None:
    ak = os.getenv("VOLC_ACCESS_KEY_ID")
    sk = os.getenv("VOLC_SECRET_ACCESS_KEY")
    if not ak or not sk:
        return None
    return {
        "ak": ak,
        "sk": sk,
        "req_key": os.getenv("JIMENG_REQ_KEY", "jimeng_t2i_v40"),
        "timeout": float(os.getenv("JIMENG_TIMEOUT", "60")),
    }


# ── 火山引擎 V4 签名（HMAC-SHA256，与 AWS SigV4 同构）──────────

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signed_request(ak: str, sk: str, action: str, body: dict) -> object:
    """构造签名后的 POST 请求对象（httpx.Request），调用方负责发送"""
    import httpx

    now = datetime.datetime.now(datetime.timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = now.strftime("%Y%m%d")

    payload = json.dumps(body, ensure_ascii=False)
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    content_type = "application/json"

    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (
        f"content-type:{content_type}\nhost:{_HOST}\n"
        f"x-content-sha256:{payload_hash}\nx-date:{x_date}\n"
    )
    canonical_request = (
        f"POST\n/\nAction={action}&Version={_VERSION}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    credential_scope = f"{short_date}/{_REGION}/{_SERVICE}/request"
    string_to_sign = (
        f"HMAC-SHA256\n{x_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )
    k_date = _sign(sk.encode("utf-8"), short_date)
    k_region = _sign(k_date, _REGION)
    k_service = _sign(k_region, _SERVICE)
    k_signing = _sign(k_service, "request")
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": content_type,
        "Host": _HOST,
        "X-Date": x_date,
        "X-Content-Sha256": payload_hash,
        "Authorization": (
            f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }
    return httpx.Request(
        "POST",
        f"https://{_HOST}/?Action={action}&Version={_VERSION}",
        headers=headers,
        content=payload.encode("utf-8"),
    )


def _post(ak: str, sk: str, action: str, body: dict) -> dict:
    import httpx

    req = _signed_request(ak, sk, action, body)
    with httpx.Client(timeout=30) as client:
        resp = client.send(req)
    if resp.status_code != 200:  # 保留火山返回体，便于区分限流 / 审核 / 参数等真实原因
        raise RuntimeError(f"{action} HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data.get("code") not in (10000, None):  # 视觉服务成功码 10000
        raise RuntimeError(f"{action} 失败: {data.get('code')} {data.get('message')}")
    return data


def _generate_once(config: dict, prompt: str, size: str) -> str | None:
    """单次「提交 + 轮询」；成功返回 URL，超时/任务失效返回 None，网络或协议异常抛出。"""
    width, height = (int(x) for x in size.split("x"))
    submit = _post(config["ak"], config["sk"], _ACTION_SUBMIT, {
        "req_key": config["req_key"],
        "prompt": prompt,
        "seed": -1,
        "scale": 0.5,
        "width": width,
        "height": height,
        "use_pre_llm": True,   # LLM 扩写 prompt，出图更稳
        "use_sr": True,        # 超分
        "return_url": True,
    })
    task_id = submit["data"]["task_id"]

    deadline = time.time() + config["timeout"]
    while time.time() < deadline:
        time.sleep(2)
        result = _post(config["ak"], config["sk"], _ACTION_QUERY, {
            "req_key": config["req_key"],
            "task_id": task_id,
            "req_json": json.dumps({"return_url": True}),
        })
        data = result.get("data", {})
        status = data.get("status")
        if status == "done":
            urls = data.get("image_urls") or []
            return urls[0] if urls else None
        if status in ("not_found", "expired"):
            _LOGGER.warning("即梦任务失效 status=%s task_id=%s", status, task_id)
            return None
    _LOGGER.warning("即梦出图轮询超时（>%.0fs）task_id=%s", config["timeout"], task_id)
    return None


def generate_concept_image(
    prompt: str,
    size: str = "1024x1024",
    fallback: str | None = None,
    retries: int = 1,
) -> str | None:
    """文生图：prompt → 图片 URL；未配置或最终失败返回 fallback（默认 None）

    失败不再静默：超时 / 任务失效 / 异常都记 warning（不打印 AK/SK），并对瞬时失败重试一次，
    连续两次出图（企划卡 + 企划案）时单次抖动不至于让概念图落空。
    """
    config = _get_config()
    if config is None:
        return fallback

    for attempt in range(retries + 1):
        try:
            url = _generate_once(config, prompt, size)
            if url:
                return url
        except Exception as exc:  # noqa: BLE001 — 出图故障刻意降级，前端用占位图，但要留痕
            msg = str(exc)
            _LOGGER.warning(
                "即梦出图第 %d 次调用异常：%s: %s",
                attempt + 1, type(exc).__name__, msg[:200],
            )
            if "50413" in msg or "Risk Not Pass" in msg:
                # 文本风控对同一 prompt 确定性复现，重试无意义，直接交给上层换安全 prompt 兜底
                break
        if attempt < retries:
            time.sleep(4)  # 间隔 4s，跨过瞬时 400 / 限流的短故障窗口
    return fallback

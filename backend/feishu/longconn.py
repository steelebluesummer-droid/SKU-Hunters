"""飞书长连接（WebSocket）生命周期 —— 在 FastAPI 进程内常驻接收群事件

为什么用长连接：后端主动建 WebSocket，无需公网回调地址 / 内网穿透；
事件包含「群消息 im.message.receive_v1」与「卡片回传 card.action.trigger」。

关键纪律（均已核对官方 SDK / 文档并由探针真机验证）：
- 全局只允许一条连接：长连接为集群模式、事件不广播，多 client 只会随机一条收到，
  因此本模块用单例 + 应用单进程启动（uvicorn 不带 --reload / 多 worker）；
- 事件回调须快速返回：重活丢给 group_bot 的线程池，本层只做解析与分发；
- 卡片回传必须 3 秒内回 P2CardActionTriggerResponse（这里只回 toast，不等业务）；
- 仅 @机器人 才响应（群消息判定 mentions 含 mentioned_type=bot；私聊直接响应）；
- 子线程跑 client.start() 前需把 SDK 模块全局 loop 设为当前线程 loop。

开关：FEISHU_LONGCONN 不为 "0/false/off" 即启用；缺 APP_ID/SECRET 则不启用（仅告警）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time

from feishu.config import FeishuConfig
from feishu.group_bot import get_group_bot

logger = logging.getLogger(__name__)

_state = {"started": False, "connected_at": "", "last_event_at": ""}
_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = False


def _configure_logging() -> None:
    """让 feishu.* 与 lark SDK 的 INFO 日志输出到 stderr（进而进后端日志文件），便于联调排错。"""
    fmt = logging.Formatter("[%(name)s] %(asctime)s %(levelname)s %(message)s")
    for name in ("feishu", "lark"):
        lg = logging.getLogger(name)
        if not lg.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(fmt)
            lg.addHandler(handler)
        lg.setLevel(logging.INFO)


_configure_logging()


def _enabled() -> bool:
    flag = os.getenv("FEISHU_LONGCONN", "1").strip().lower()
    return flag not in ("0", "false", "off", "no")


def is_running() -> bool:
    return _state["started"]


def status() -> dict:
    return dict(_state)


# ── 事件分发 ────────────────────────────────────────────────

def _is_at_bot(message) -> bool:
    """群消息仅在 @机器人 时响应；私聊（p2p）直接响应"""
    chat_type = getattr(message, "chat_type", "") or ""
    if chat_type == "p2p":
        return True
    mentions = getattr(message, "mentions", None) or []
    for m in mentions:
        if getattr(m, "mentioned_type", "") == "bot":
            return True
    return False


def _on_message(data) -> None:
    """im.message.receive_v1：只解析 + 丢后台，事件线程不阻塞"""
    try:
        event = data.event
        message = event.message
        sender = getattr(event, "sender", None)
        # 忽略机器人/应用自己发的消息，防止回环
        sender_type = getattr(sender, "sender_type", "") or ""
        if sender_type and sender_type != "user":
            return
        if getattr(message, "message_type", "") != "text":
            return  # 群闭环只处理文本指令（非文本静默忽略）
        if not _is_at_bot(message):
            return

        user_id = getattr(getattr(sender, "sender_id", None), "open_id", "") or ""
        chat_id = getattr(message, "chat_id", "") or ""
        try:
            content = json.loads(getattr(message, "content", "") or "{}")
        except (ValueError, TypeError):
            content = {}
        text = str(content.get("text", "") or "")
        if not chat_id or not user_id:
            return
        _state["last_event_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info("长连接收到群指令 chat=%s user=%s 文本长度=%d", chat_id, user_id[:6] + "***", len(text))
        get_group_bot().enqueue_message(chat_id, user_id, text)
    except Exception:  # noqa: BLE001 — 入站解析绝不能炸掉 SDK 连接
        logger.exception("分发群消息事件异常（已忽略，不影响长连接）")


def _on_card_action(data):
    """card.action.trigger：3 秒内回 toast + 按需回传替换卡片(raw)；重业务由 group_bot 丢后台"""
    from lark_oapi.event.callback.model.p2_card_action_trigger import (
        P2CardActionTriggerResponse,
    )

    try:
        ev = data.event
        user_id = getattr(getattr(ev, "operator", None), "open_id", "") or ""
        chat_id = getattr(getattr(ev, "context", None), "open_chat_id", "") or ""
        action = getattr(ev, "action", None)
        value = getattr(action, "value", None) or {}
        form_value = getattr(action, "form_value", None) or {}
        _state["last_event_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        result = get_group_bot().handle_card_action(value, form_value, user_id, chat_id) or {}
        # toast 给即时浮层提示；card(raw) 让飞书用新卡片同步替换被点击的那张，做到"点完卡片就变样"
        payload = {
            "toast": {"type": result.get("type", "info"), "content": result.get("content", "")}
        }
        new_card = result.get("card")
        if isinstance(new_card, dict):
            payload["card"] = {"type": "raw", "data": new_card}
        return P2CardActionTriggerResponse(payload)
    except Exception:  # noqa: BLE001 — 回调必须有响应，否则客户端报交互错误
        logger.exception("处理卡片回传异常（回错误 toast，连接不受影响）")
        return P2CardActionTriggerResponse(
            {"toast": {"type": "error", "content": "操作处理失败，请稍后重试"}}
        )


# ── 连接生命周期 ────────────────────────────────────────────

def _build_client():
    import lark_oapi as lark

    config = FeishuConfig.from_env()
    handler = (
        lark.EventDispatcherHandler.builder("", "")  # 长连接模式校验参数留空
        .register_p2_im_message_receive_v1(_on_message)
        .register_p2_card_action_trigger(_on_card_action)
        .build()
    )
    return lark.ws.Client(
        config.app_id,
        config.app_secret,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
        auto_reconnect=True,
    )


def _run_forever() -> None:
    from lark_oapi.ws import client as ws_internal

    # 预热 IP 资源库（首次可能拉飞书表，避免首个卡片回调超过 3 秒）
    try:
        from feishu import nl_brief
        nl_brief.list_ip_options()
    except Exception:  # noqa: BLE001
        logger.exception("IP 资源库预热失败（不影响长连接，首次使用时再加载）")

    # SDK 模块在导入时于主线程建过全局 loop，工作线程需把它设为当前 loop
    try:
        asyncio.set_event_loop(ws_internal.loop)
    except Exception:  # noqa: BLE001
        pass

    global _stop
    while not _stop:
        try:
            client = _build_client()
            _state["connected_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.info("飞书长连接启动中…（成功后 SDK 输出 connected to wss://...）")
            client.start()  # 正常情况下阻塞常驻、内部自动重连
        except Exception:  # noqa: BLE001 — start 异常退出时外层兜底重连，不长时间掉线
            logger.exception("飞书长连接异常退出，5 秒后重连")
        if _stop:
            break
        time.sleep(5)


def start_feishu_longconn() -> bool:
    """在后台 daemon 线程启动飞书长连接（幂等：只启动一次）。返回是否已启动。"""
    global _thread, _stop
    if not _enabled():
        logger.info("FEISHU_LONGCONN 已关闭，跳过飞书长连接启动")
        return False
    config = FeishuConfig.from_env()
    if not (config.app_id and config.app_secret):
        logger.warning("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET，飞书长连接不启动（群机器人闭环不可用）")
        return False

    global _state
    with _lock:
        if _state["started"]:
            return True
        _stop = False
        _thread = threading.Thread(
            target=_run_forever, name="feishu-longconn", daemon=True
        )
        _thread.start()
        _state["started"] = True
    logger.info("飞书长连接后台线程已拉起 app_id=%s（Secret 不打印）", config.app_id)
    return True


def stop_feishu_longconn() -> None:
    """停止长连接（主要用于测试/优雅关停；daemon 线程随进程退出也会结束）"""
    global _stop, _thread
    _stop = True
    _thread = None

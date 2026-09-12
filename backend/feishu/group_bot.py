"""飞书群机器人闭环编排器（长连接入站后的业务大脑）

闭环（与用户确认的五项决策一致）：
  群里 @机器人 一句话提需求
    → NL 解析品类/IP/价格/人群（feishu.nl_brief）
    → 缺“品类/联名IP”或 IP 不在资源库：发【表单卡片 2.0】补全（IP 只能从资源库下拉选）
    → 信息齐全：同进程直调 pipeline 跑 五看洞察 → 机会
    → 机会卡点：发三张方向卡，人点选（不全自动）
    → 点选后：生成企划卡（即梦出图）→ 归档 → 归档卡发回发起群

工程约束：
- 长连接事件回调要求 3 秒内响应，重活（洞察约 1 分钟、出图约 30 秒）一律丢线程池，
  回调只回一个 toast；
- 仅 @机器人 才会进入本模块（是否@由 longconn 层判定）；
- 按 (chat_id, 发起人 open_id) 隔离会话并防重入；
- 全程 fail-loud：任何阶段失败都往群里发明确错误（不静默吞），但不回显密钥/堆栈。
"""

from __future__ import annotations

import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.planning import pipeline
from app.planning.insight_resolver import LLMGenerationError
from app.planning.repository import _snake_keys
from app.schemas.planning import PlanBrief
from app.planning.service import StateTransitionError

from feishu import cards_v2, nl_brief
from feishu.auth import FeishuAuth
from feishu.bot import FeishuBot
from feishu.config import FeishuConfig

logger = logging.getLogger(__name__)

_AT_PLACEHOLDER = re.compile(r"@_user_\d+\s*")
_AT_NAME = re.compile(r"@[^\s@]+")


def _strip_mention(text: str) -> str:
    """去掉群消息里 @机器人 的占位符（@_user_1）与裸 @名，得到纯需求文本"""
    if not text:
        return ""
    text = _AT_PLACEHOLDER.sub("", text)
    text = _AT_NAME.sub("", text)
    return text.strip()


class GroupBot:
    """单例：持有出站 bot、后台线程池、会话在途状态"""

    def __init__(self) -> None:
        config = FeishuConfig.from_env()
        self.bot = FeishuBot(FeishuAuth(config))
        # live 管线较重（LLM+即梦），群里低并发：2 个 worker 足够且避免同时烧太多 LLM
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="group-bot")
        # 会话在途标记：(chat_id, user_id) -> "insights" / "plan_card"，防同一人重复发起
        self._running: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    # ── 出站小工具 ──────────────────────────────────────────

    def _frontend_base(self) -> str:
        return os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

    def _send_text(self, chat_id: str, text: str) -> None:
        try:
            self.bot.send_text(chat_id, text)
        except Exception:  # noqa: BLE001 — 出站失败不拖垮后台线程
            logger.exception("群消息发送失败 chat=%s", chat_id)

    def _send_card(self, chat_id: str, card: dict[str, Any]) -> None:
        try:
            self.bot.send_card(chat_id, card)
        except Exception:  # noqa: BLE001
            logger.exception("群卡片发送失败 chat=%s", chat_id)

    def _is_running(self, key: tuple[str, str]) -> str | None:
        with self._lock:
            return self._running.get(key)

    def _set_running(self, key: tuple[str, str], stage: str) -> None:
        with self._lock:
            self._running[key] = stage

    def _clear_running(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._running.pop(key, None)

    def _submit(self, fn, *args, **kwargs):
        """提交后台任务，并回捞 worker 内未捕获异常（线程池默认会静默吞掉）"""
        future = self._pool.submit(fn, *args, **kwargs)

        def _on_done(fut):
            exc = fut.exception()
            if exc is not None:
                logger.exception("群闭环后台任务未捕获异常: %s", exc, exc_info=exc)

        future.add_done_callback(_on_done)
        return future

    # ── 入站：群消息 ────────────────────────────────────────

    def enqueue_message(self, chat_id: str, user_id: str, raw_text: str) -> None:
        """事件线程入口：把消息处理整体丢后台线程，保证长连接事件分发不被阻塞"""
        logger.info("enqueue_message chat=%s 原文长度=%d", chat_id, len(raw_text or ""))
        self._submit(self.handle_message, chat_id, user_id, raw_text)

    def handle_message(self, chat_id: str, user_id: str, raw_text: str) -> None:
        """处理一条 @机器人 的群文本消息（由 longconn 在事件线程调用，需快速返回）"""
        logger.info("handle_message 开始 user=%s", (user_id or "")[:6] + "***")
        key = (chat_id, user_id)
        stage = self._is_running(key)
        if stage:
            self._send_text(chat_id, f"上一个企划任务正在「{stage}」中，请稍候～完成后我会发卡片到群里。")
            return

        text = _strip_mention(raw_text)
        if not text:
            self._send_text(
                chat_id,
                "你好，我是趋势官。直接告诉我想做的品类和联名 IP 即可，例如：\n"
                "“做一款保温杯，和三丽鸥联名”。",
            )
            return

        try:
            parsed = nl_brief.parse_brief_text(text)
        except Exception:  # noqa: BLE001 — 解析器自身已降级，这里兜底不阻塞
            logger.exception("NL 需求解析异常，按缺字段处理")
            parsed = {"category": "", "ip_raw": "", "ip_match": None, "audience": "", "price_range": None}
        logger.info("需求解析完成 text=%r parsed=%s", text, parsed)

        missing = []
        note_lines = ["请补全以下信息后点「开始生成企划」（**品类 + 联名 IP 为必填**）："]
        if not parsed.get("category"):
            missing.append("category")
        ip_match = parsed.get("ip_match")
        ip_raw = parsed.get("ip_raw", "")
        if not ip_match:
            missing.append("ip")
            if ip_raw:
                note_lines.insert(0, f"⚠️ IP 资源库中无『{ip_raw}』，请从下方 IP 下拉里重选（仅支持资源库内 IP）。")

        if missing:
            logger.info("缺必填字段 %s（ip_raw=%r），发送补全表单卡", missing, ip_raw)
            prefill = {
                "category": parsed.get("category", ""),
                "audience": parsed.get("audience", ""),
                "price_range": (
                    f"{parsed['price_range'][0]:g}-{parsed['price_range'][1]:g}"
                    if parsed.get("price_range") else ""
                ),
            }
            card = cards_v2.brief_form_card(
                session_key=self._session_key(key),
                ip_names=nl_brief.list_ip_options(),
                prefill=prefill,
                note="\n".join(note_lines),
            )
            self._send_card(chat_id, card)
            return

        # 信息齐全 → 后台跑管线
        logger.info("信息齐全，启动管线 category=%s ip=%s", parsed["category"], ip_match)
        self._kickoff(chat_id, user_id, parsed["category"], ip_match,
                      parsed.get("audience", ""), parsed.get("price_range"))

    # ── 入站：卡片回调（表单提交 / 机会点选）──────────────────

    def handle_card_action(
        self,
        value: dict[str, Any],
        form_value: dict[str, Any],
        user_id: str,
        chat_id: str,
    ) -> dict[str, str]:
        """处理 card.action.trigger。返回 toast dict（{type,content}），由 longconn 回给飞书。"""
        value = value or {}
        form_value = form_value or {}
        act = value.get("act", "")
        key = (chat_id, user_id)
        logger.info("handle_card_action act=%s value=%s form_value=%s", act, value, form_value)

        if act == "submit_brief":
            category = str(form_value.get("category", "")).strip()
            ip_name = str(form_value.get("ip", "")).strip()
            audience = str(form_value.get("audience", "")).strip()
            price_range = nl_brief.parse_price_range(form_value.get("price_range"))

            if not category:
                return {"type": "error", "content": "请填写品类"}
            if not ip_name:
                return {"type": "error", "content": "请从资源库选择联名 IP"}
            # 双保险：下拉值必须确实在资源库内（拒绝任何库外 IP）
            if ip_name not in nl_brief.list_ip_options():
                matched = nl_brief.match_ip(ip_name)
                if not matched:
                    return {"type": "error", "content": "该 IP 不在资源库，请用下拉选择"}
                ip_name = matched
            if self._is_running(key):
                return {"type": "info", "content": "上一个任务仍在进行中，请稍候"}

            self._kickoff(chat_id, user_id, category, ip_name, audience, price_range)
            return {"type": "success", "content": "已收到，开始生成企划（约 1-2 分钟），完成后发群里"}

        if act == "pick_opp":
            plan_id = str(value.get("plan_id", ""))
            opp_id = str(value.get("opp_id", ""))
            if not plan_id or not opp_id:
                return {"type": "error", "content": "方向参数缺失"}
            plan = pipeline.get_plan(plan_id)
            if plan is None:
                return {"type": "error", "content": "任务不存在或已被清理"}
            if plan.get("status") != "opportunities_ready":
                return {"type": "info", "content": f"当前任务状态为 {plan.get('status')}，无需重复选择"}
            if not any(o.get("id") == opp_id for o in plan.get("opportunities", [])):
                return {"type": "error", "content": "该方向不存在，请重新选择"}
            if self._is_running(key):
                return {"type": "info", "content": "正在处理中，请稍候"}
            self._set_running(key, "plan_card")
            logger.info("用户点选方向 plan_id=%s opp_id=%s，后台生成企划卡", plan_id, opp_id)
            self._submit(self._run_card_and_archive, chat_id, key, plan_id, opp_id)
            return {"type": "success", "content": "已选定方向，正在生成企划卡与概念图…"}

        return {"type": "info", "content": "未识别的卡片操作"}

    # ── 后台编排 ────────────────────────────────────────────

    def _session_key(self, key: tuple[str, str]) -> str:
        return f"{key[0]}|{key[1]}"

    def _kickoff(self, chat_id, user_id, category, ip_name, audience, price_range) -> None:
        key = (chat_id, user_id)
        self._set_running(key, "五看洞察")
        self._send_text(
            chat_id,
            f"✅ 已受理：{ip_name} × {category} 联名企划\n"
            "正在做五看洞察与机会分析（约 1 分钟），完成后我会把可选方向发到群里。",
        )
        self._submit(
            self._run_insights, chat_id, key,
            dict(category=category, ip_name=ip_name, audience=audience, price_range=price_range),
        )

    def _run_insights(self, chat_id: str, key: tuple[str, str], draft: dict[str, Any]) -> None:
        plan_id = ""
        logger.info("_run_insights 开始 draft=%s", draft)
        try:
            brief = nl_brief.build_brief(
                category=draft["category"],
                ip_display=draft["ip_name"],
                audience=draft.get("audience", ""),
                price_range=draft.get("price_range"),
            )
            # 与 HTTP 入口一致：先过 PlanBrief 契约校验
            PlanBrief.model_validate(_snake_keys(brief))
            plan = pipeline.create_plan(brief)
            plan_id = plan["plan_id"]
            logger.info("已建档 plan_id=%s，开始五看洞察", plan_id)

            self._set_running(key, "五看洞察")
            pipeline.generate_insights(plan)
            logger.info("五看洞察完成 plan_id=%s，开始机会生成", plan_id)

            self._set_running(key, "机会分析")
            opportunities = pipeline.generate_opportunities(plan)
            logger.info("机会生成完成 plan_id=%s 方向数=%d，发送机会选择卡", plan_id, len(opportunities or []))

            card = cards_v2.opportunity_choice_card(plan, opportunities, self._frontend_base())
            self._send_card(chat_id, card)
            # 进入“等人点选方向”阶段，释放在途锁（允许点选回调再启动）
            self._clear_running(key)
            logger.info("机会选择卡已发群，等待用户点选 plan_id=%s", plan_id)
        except StateTransitionError as e:
            logger.exception("状态机异常 plan_id=%s", plan_id, exc_info=e)
            self._fail(chat_id, key, plan_id, f"流程状态异常（{e.action or '状态机'}），请重新发起")
        except LLMGenerationError as e:
            logger.exception("LLM 生成失败 plan_id=%s detail=%s", plan_id, getattr(e, "args", None), exc_info=e)
            self._fail(chat_id, key, plan_id, "AI 内容生成暂时不可用（LLM 服务异常），请稍后重试")
        except Exception:  # noqa: BLE001
            logger.exception("群闭环洞察阶段异常 plan_id=%s", plan_id)
            self._fail(chat_id, key, plan_id, "洞察/机会生成失败，请检查 LLM/数据源后重试")

    def _run_card_and_archive(self, chat_id, key, plan_id, opp_id) -> None:
        try:
            plan = pipeline.get_plan(plan_id)
            if plan is None:
                self._fail(chat_id, key, plan_id, "任务不存在，无法生成企划卡")
                return
            self._send_text(chat_id, "🎨 正在生成企划卡与即梦概念图（约 30-60 秒），请稍候…")
            self._set_running(key, "企划卡出图")
            logger.info("开始生成企划卡(含即梦图) plan_id=%s opp_id=%s", plan_id, opp_id)
            card = pipeline.generate_plan_card(plan, opp_id)
            if card is None:
                self._fail(chat_id, key, plan_id, "未找到所选方向，企划卡生成失败")
                return
            logger.info("企划卡完成，执行归档 plan_id=%s", plan_id)

            # 出企划卡即归档（用户拍板：出企划卡 = 归档）
            pipeline.archive_plan(plan)
            self._set_running(key, "归档同步")
            self._archive_hooks(plan)

            # 归档后生成飞书在线完整报告（五看驾驶舱+企划案+即梦概念图），群内直接看、不跳前端；
            # 云文档需逐块写入（约 2-4 分钟），先发一条进度，避免群里长时间静默以为卡住
            self._send_text(
                chat_id,
                "📝 企划已归档，正在生成飞书在线完整报告（五看驾驶舱 + 企划案 + 概念图，约 2-3 分钟），"
                "完成后直接发到本群，无需跳转。",
            )
            from feishu.doc_report import build_plan_report, build_report_card
            report = build_plan_report(plan)
            if report and report.get("url"):
                self._send_card(chat_id, build_report_card(plan, report))
                logger.info("在线完整报告已发回群 plan_id=%s doc=%s", plan_id, report.get("document_id"))
            else:
                from feishu.notify import build_archive_card
                self._send_card(chat_id, build_archive_card(plan, self._frontend_base()))
                logger.warning("在线报告未生成，降级旧归档卡 plan_id=%s", plan_id)
            self._clear_running(key)
            logger.info("归档闭环完成 plan_id=%s", plan_id)
        except StateTransitionError as e:
            self._fail(chat_id, key, plan_id, f"流程状态异常（{e.action or '状态机'}），请回到方向选择重试")
        except LLMGenerationError:
            self._fail(chat_id, key, plan_id, "企划卡 AI 生成暂时不可用，请稍后重试")
        except Exception:  # noqa: BLE001
            logger.exception("群闭环企划卡/归档阶段异常 plan_id=%s", plan_id)
            self._fail(chat_id, key, plan_id, "企划卡生成或归档失败，请稍后重试")

    def _archive_hooks(self, plan: dict[str, Any]) -> None:
        """归档后同步多维表格（fail-soft；未配置 bitable 时静默跳过）"""
        try:
            from feishu.bitable_sync import sync_plan_to_bitable
            sync_plan_to_bitable(plan)
        except Exception:  # noqa: BLE001 — 多维表同步不影响归档与群通知
            logger.exception("归档同步多维表失败（不影响归档）plan_id=%s", plan.get("plan_id"))

    def _fail(self, chat_id: str, key: tuple[str, str], plan_id: str, message: str) -> None:
        self._clear_running(key)
        tail = f"\n可前往工作室查看：{self._frontend_base().rstrip('/')}/tasks/{plan_id}" if plan_id else ""
        self._send_card(chat_id, cards_v2.notice_card("⚠️ 任务未完成", message + tail, template="red"))


# ── 单例 ────────────────────────────────────────────────────

_BOT: GroupBot | None = None
_BOT_LOCK = threading.Lock()


def get_group_bot() -> GroupBot:
    global _BOT
    if _BOT is None:
        with _BOT_LOCK:
            if _BOT is None:
                _BOT = GroupBot()
    return _BOT

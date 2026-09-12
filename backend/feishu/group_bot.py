"""飞书群机器人闭环编排器（长连接入站后的业务大脑）

闭环（与用户确认的五项决策一致）：
  群里 @机器人 一句话提需求
    → NL 解析品类/IP/价格/人群（feishu.nl_brief）
    → 缺“品类/IP 策略”或外部 IP 不在资源库：发【表单卡片 2.0】补全
      （IP 三档下拉：无外部联名 / 自有 IP（已标注）/ 外部联名 IP，外部仅限资源库内）
    → 信息齐全：同进程直调 pipeline 跑 五看洞察 → 机会
    → 机会卡点：发三张方向卡，人点选（不全自动）
    → 点选后：生成企划卡（即梦出图）→ 生成飞书在线完整报告并发【待确认卡】（此阶段不归档）
    → 人审阅在线报告后点『确认归档』：才推进归档状态 + 同步多维表「企划资产库」，并回发归档回执
    （先文档、后归档：未经人工确认不归档，避免问题方案直接入库）

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
from app.planning.service import StateTransitionError
from app.schemas.planning import PlanBrief
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
        except Exception:
            logger.exception("群消息发送失败 chat=%s", chat_id)

    def _send_card(self, chat_id: str, card: dict[str, Any]) -> None:
        try:
            resp = self.bot.send_card(chat_id, card) or {}
            code = resp.get("code")
            if code not in (0, None):  # HTTP 200 但卡片被飞书拒收（如非法标签）必须暴露，不能静默当成功
                logger.error("群卡片被飞书拒收 chat=%s code=%s msg=%s",
                             chat_id, code, str(resp.get("msg", ""))[:300])
        except Exception:
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
                "你好，我是趋势官。告诉我想做的品类和 IP 策略即可，例如：\n"
                "· “做一款保温杯，和三丽鸥联名”（外部联名）\n"
                "· “做一款保温杯，用自有 IP YOYO”（自有 IP）\n"
                "· “做一款保温杯，不做联名”（无外部联名 · 原创设计）",
            )
            return

        try:
            parsed = nl_brief.parse_brief_text(text)
        except Exception:
            logger.exception("NL 需求解析异常，按缺字段处理")
            parsed = {"category": "", "ip_raw": "", "ip_match": None, "audience": "", "price_range": None}
        logger.info("需求解析完成 text=%r parsed=%s", text, parsed)

        missing = []
        note_lines = ["请补全以下信息后点「开始生成企划」（**品类 + IP 策略为必填**）："]
        if not parsed.get("category"):
            missing.append("category")
        ip_match = parsed.get("ip_match")
        ip_raw = parsed.get("ip_raw", "")
        if not ip_match:
            missing.append("ip")
            if ip_raw:
                note_lines.insert(
                    0,
                    f"⚠️ 外部 IP 资源库中无『{ip_raw}』。请从下方 IP 策略下拉重选："
                    "可选「无外部联名」、标注「（自有IP）」的名创自有 IP，或资源库内的外部联名 IP。",
                )

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
                ip_options=nl_brief.list_ip_select_options(),
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
    ) -> dict[str, Any]:
        """处理 card.action.trigger。返回 {type,content,card?}：type/content 组成 toast（必填），
        card 为点击后用于「同步替换原卡」的新卡片（schema2.0 dict，可选）；最终由 longconn 组装回飞书。
        校验拦截类分支只回 toast、不换卡（保留原卡让用户可继续操作）。"""
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
                return {"type": "error", "content": "请选择 IP 策略（无外部联名 / 自有 IP / 外部联名 IP）"}
            # 双保险：值必须合法（『无外部联名』+ 自有/外部资源库内），拒绝任何库外外部 IP
            if ip_name not in nl_brief.list_ip_options():
                matched = nl_brief.match_ip(ip_name)
                if not matched:
                    return {"type": "error", "content": "该外部 IP 不在资源库，请用下拉选择（或选无外部联名/自有 IP）"}
                ip_name = matched
            if self._is_running(key):
                return {"type": "info", "content": "上一个任务仍在进行中，请稍候"}

            self._kickoff(chat_id, user_id, category, ip_name, audience, price_range)
            accepted = cards_v2.notice_card(
                "✅ 需求已提交",
                f"已收到需求：**{category}**｜IP 策略：**{ip_name}**\n"
                "正在生成五看洞察与机会方向（约 30-60 秒），完成后会在本群发「机会选择卡」供你点选，无需重复提交。",
                template="blue",
            )
            return {"type": "success", "content": "已收到，开始生成企划", "card": accepted}

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
            opps = plan.get("opportunities", [])
            picked = next((o for o in opps if o.get("id") == opp_id), {}) or {}
            opp_idx = next((i for i, o in enumerate(opps, 1) if o.get("id") == opp_id), "")
            opp_title = picked.get("title") or picked.get("direction") or f"方向 {opp_idx}"
            self._set_running(key, "plan_card")
            logger.info("用户点选方向 plan_id=%s opp_id=%s，后台生成企划卡与在线报告", plan_id, opp_id)
            self._submit(self._run_card_and_report, chat_id, key, plan_id, opp_id)
            accepted = cards_v2.notice_card(
                "✅ 已选定机会方向",
                f"已选择方向 {opp_idx}：**{picked.get('emoji', '')}{opp_title}**\n"
                "正在生成企划卡、即梦概念图与在线完整报告（约 2-3 分钟），完成后发「待确认卡」，请在本群稍候、无需重复点选。",
                template="green",
            )
            return {"type": "success",
                    "content": "已选定方向，正在生成企划卡与在线报告…", "card": accepted}

        if act == "confirm_archive":
            plan_id = str(value.get("plan_id", ""))
            if not plan_id:
                return {"type": "error", "content": "归档参数缺失"}
            plan = pipeline.get_plan(plan_id)
            if plan is None:
                return {"type": "error", "content": "任务不存在或已被清理"}
            status = plan.get("status")
            if status == "archived":
                return {"type": "info", "content": "该企划已归档，无需重复操作"}
            if status != "plan_card_ready":
                return {"type": "info", "content": f"当前状态为 {status}，企划卡定稿后才能归档"}
            if self._is_running(key):
                return {"type": "info", "content": "正在处理中，请稍候"}
            self._set_running(key, "归档中")
            logger.info("用户确认归档 plan_id=%s，后台执行归档+多维表同步", plan_id)
            self._submit(self._do_confirm_archive, chat_id, key, plan_id)
            accepted = cards_v2.notice_card(
                "⏳ 正在归档到企划资产库",
                "已收到你的确认，正在推进归档并写入多维表「企划资产库」（约几秒），"
                "完成后本群会发「✅ 已归档」回执，此卡无需再点。",
                template="orange",
            )
            return {"type": "success", "content": "已收到，正在归档…", "card": accepted}

        # ── 新品类调研：登记到调研需求池（只写品类名+待调研），本次任务暂停 ──
        if act == "request_research":
            plan_id = str(value.get("plan_id", ""))
            category = str(value.get("category", "")).strip()
            if not plan_id or not category:
                return {"type": "error", "content": "调研参数缺失，无法登记"}
            plan = pipeline.get_plan(plan_id)
            if plan is None:
                return {"type": "error", "content": "任务不存在或已被清理"}
            if plan.get("status") != "brief_locked":
                return {"type": "info", "content": "该任务已开始生成，无需再登记调研"}
            if self._is_running(key):
                return {"type": "info", "content": "正在处理中，请稍候"}
            from feishu.research_pool import submit_research_request
            try:
                created, _rid = submit_research_request(category)  # 同步写表（快），失败不换卡可重试
            except Exception as exc:
                logger.exception("登记调研需求失败 plan_id=%s", plan_id)
                return {"type": "error", "content": f"登记调研需求失败：{exc}，请稍后重试"}
            self._clear_running(key)
            verb = "已在「调研需求池」新建一条需求" if created else "该品类已在调研队列中（待调研/调研中），未重复登记"
            done = cards_v2.notice_card(
                "✅ 已提交调研需求，本次任务暂停",
                f"**{category}**：{verb}（状态：待调研）。\n"
                "等豆包工作伙伴把趋势 / 痛点 / 竞品 / 热词等数据补全进 Base 后，再在群里@我，"
                "即可基于真实数据生成企划。",
                template="green",
            )
            return {"type": "success", "content": "已登记调研需求，本次任务暂停", "card": done}

        if act == "cancel_research":
            self._clear_running(key)
            done = cards_v2.notice_card(
                "已取消本次调研",
                "未登记调研需求，任务到此结束。需要时重新@我发起即可。",
                template="blue",
            )
            return {"type": "info", "content": "已取消调研", "card": done}

        return {"type": "info", "content": "未识别的卡片操作"}

    # ── 后台编排 ────────────────────────────────────────────

    def _session_key(self, key: tuple[str, str]) -> str:
        return f"{key[0]}|{key[1]}"

    def _kickoff(self, chat_id, user_id, category, ip_name, audience, price_range) -> None:
        key = (chat_id, user_id)
        self._set_running(key, "五看洞察")
        self._send_text(
            chat_id,
            f"✅ 已受理：{nl_brief.brief_headline(category, ip_name)}\n"
            "正在做五看洞察与机会分析（约 1 分钟），完成后我会把可选方向发到群里。",
        )
        self._submit(
            self._run_insights, chat_id, key,
            {"category": category, "ip_name": ip_name, "audience": audience, "price_range": price_range},
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

            # 新品类拦截：飞书 Base 与本地采集都无真实数据 → 发「是否调研」卡并暂停，不跑 LLM 空推
            from app.planning.insight_resolver import category_has_real_evidence
            if not category_has_real_evidence(draft["category"]):
                self._clear_running(key)
                self._send_card(chat_id, cards_v2.research_confirm_card(plan, draft["category"]))
                logger.info("新品类「%s」无真实数据 plan_id=%s，已发调研确认卡并暂停",
                            draft["category"], plan_id)
                return

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
        except LLMGenerationError:
            logger.exception("LLM 生成失败 plan_id=%s", plan_id)
            self._fail(chat_id, key, plan_id, "AI 内容生成暂时不可用（LLM 服务异常），请稍后重试")
        except Exception:
            logger.exception("群闭环洞察阶段异常 plan_id=%s", plan_id)
            self._fail(chat_id, key, plan_id, "洞察/机会生成失败，请检查 LLM/数据源后重试")

    def _run_card_and_report(self, chat_id, key, plan_id, opp_id) -> None:
        """阶段一：企划卡（即梦图）→ 飞书在线完整报告 → 发【待确认卡】。此阶段不归档。"""
        try:
            plan = pipeline.get_plan(plan_id)
            if plan is None:
                self._fail(chat_id, key, plan_id, "任务不存在，无法生成企划卡")
                return
            self._send_text(chat_id, "🎨 正在生成企划卡与即梦概念图（约 30-60 秒），请稍候…")
            self._set_running(key, "企划卡出图")
            logger.info("开始生成企划卡(含即梦图) plan_id=%s opp_id=%s", plan_id, opp_id)
            card = pipeline.generate_plan_card(plan, opp_id)  # 成功后状态 → plan_card_ready
            if card is None:
                self._fail(chat_id, key, plan_id, "未找到所选方向，企划卡生成失败")
                return
            logger.info("企划卡完成（暂不归档），开始生成在线报告 plan_id=%s", plan_id)

            # 先文档：生成飞书在线完整报告（五看驾驶舱+企划案+即梦概念图），群内直接看、不跳前端；
            # 云文档逐块写入约 2-3 分钟，先发进度避免群里静默。归档要等用户点『确认归档』。
            self._send_text(
                chat_id,
                "📝 企划卡已生成，正在汇总飞书在线完整报告（五看驾驶舱 + 企划案 + 概念图，约 2-3 分钟），"
                "完成后发到本群供你审阅，确认无误再点归档。",
            )
            self._set_running(key, "在线报告")
            from feishu.doc_report import build_plan_report
            report = build_plan_report(plan)  # plan_card_ready 即可生成，不依赖 archived
            # 文档成功/失败都发待确认卡（失败降级时仍可基于企划卡确认归档或进工作室改稿）
            self._send_card(chat_id, cards_v2.review_report_card(plan, report, self._frontend_base()))
            self._clear_running(key)  # 释放在途锁，等待用户点『确认归档』
            if report and report.get("url"):
                logger.info("在线报告+待确认卡已发群，等人工确认归档 plan_id=%s doc=%s",
                            plan_id, report.get("document_id"))
            else:
                logger.warning("在线报告未生成，已发降级待确认卡 plan_id=%s", plan_id)
        except StateTransitionError as e:
            self._fail(chat_id, key, plan_id, f"流程状态异常（{e.action or '状态机'}），请回到方向选择重试")
        except LLMGenerationError:
            self._fail(chat_id, key, plan_id, "企划卡 AI 生成暂时不可用，请稍后重试")
        except Exception:
            logger.exception("群闭环企划卡/在线报告阶段异常 plan_id=%s", plan_id)
            self._fail(chat_id, key, plan_id, "企划卡或在线报告生成失败，请稍后重试")

    def _do_confirm_archive(self, chat_id, key, plan_id) -> None:
        """阶段二：用户在待确认卡点『确认归档』后，才推进归档 + 多维表同步，并回发归档回执。"""
        try:
            plan = pipeline.get_plan(plan_id)
            if plan is None:
                self._fail(chat_id, key, plan_id, "任务不存在，无法归档")
                return
            if plan.get("status") == "archived":  # 幂等：重复点击 / 并发兜底
                self._send_card(chat_id, cards_v2.notice_card(
                    "ℹ️ 已归档", "该企划此前已归档，企划资产库中已有记录，无需重复操作。", template="blue"))
                self._clear_running(key)
                return
            logger.info("用户确认，执行归档 plan_id=%s", plan_id)
            pipeline.archive_plan(plan)  # plan_card_ready → archived，写 archived_at
            self._set_running(key, "归档同步")
            self._archive_hooks(plan)  # 多维表同步依赖 archived_at，fail-soft 不拖垮归档
            brief = plan.get("brief") or {}
            card = plan.get("plan_card") or {}
            name = card.get("name") or brief.get("theme", "新品企划")
            self._send_card(chat_id, cards_v2.notice_card(
                "✅ 已归档到企划资产库",
                f"**{name}**\n状态：已归档，已在多维表「企划资产库」新增一行；"
                "完整在线报告见上方卡片，可随时复盘。",
                template="green"))
            self._clear_running(key)
            logger.info("确认归档闭环完成 plan_id=%s", plan_id)
        except StateTransitionError as e:
            self._fail(chat_id, key, plan_id, f"流程状态异常（{e.action or '状态机'}），请刷新后重试")
        except Exception:
            logger.exception("群闭环确认归档阶段异常 plan_id=%s", plan_id)
            self._fail(chat_id, key, plan_id, "归档失败，请稍后重试")

    def _archive_hooks(self, plan: dict[str, Any]) -> None:
        """归档后同步多维表格（fail-soft；未配置 bitable 时静默跳过）"""
        try:
            from feishu.bitable_sync import sync_plan_to_bitable
            sync_plan_to_bitable(plan)
        except Exception:
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

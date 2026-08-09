"""API 路由 — 对应 docs/api/endpoints.md 约定（D1 冻结 + D2 增补）

编排层已接入：POST /reviews 后台驱动 run_review 事件流，
人工决策经 asyncio.Future 桥接进图的 interrupt。

动作映射（冻结契约词汇 → 图门词汇，D2 增补）：
- approve  → confirm（理由必填，留痕）
- reject   → reject（否决立项 = bad case，归档为学习官负样本）
- revise   → modify（suggestion = reason）
- reweight → modify + scope=business + custom_weights（仅商业官重算，秒级）
- chat     → 首次复盘入口对话（会后不打回重做，仅对话/总结教训）
- done     → 结束本轮复盘，轮数追加入档

D3 增补（2026-08-09）：归档前置——Gate 2 结论即建档（archive），
归档不是封存：POST /reviews/{id}/retro 是历史复盘入口，归档后随时可追问，
问答追加进 retro_logs 并累加 archive.retro_turns。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..config import WEIGHT_TEMPLATES
from ..engine.graph import retro_answer, run_review
from ..schemas.brief import Brief, Weights

router = APIRouter(prefix="/api/v1", tags=["committee"])

# 演示期内存存储：session_id → 会议全景（事件流 + 门桥 + 建议书 + 档案）
_SESSIONS: dict[str, dict[str, Any]] = {}

# role → current_act 映射（契约 current_act 枚举）
_ROLE_ACT = {
    "trend": "act1_insights", "user": "act1_insights", "ip": "act1_insights",
    "act1_gate": "act1_gate",
    "creative": "act2_ideation",
    "business": "act3_dual_review", "global": "act3_dual_review",
    "decision": "act4_decision",
    "human_gate": "human_gate",
    "retro": "act5_retro", "learning": "act5_retro",
    "qa": "act1_gate",
}

# 这些角色的发言内容构成历史复盘的素材摘要（与图内 _state_digest 对齐）
_DIGEST_ROLES = {"trend": "趋势官", "user": "用户官", "ip": "IP官",
                 "decision": "立项建议"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _drive(session_id: str, brief: dict[str, Any]):
    """后台驱动一轮评审：事件入 live_feed，门挂起等 Future，建议书/档案落库"""
    session = _SESSIONS[session_id]

    async def ask_human(gate_info: dict[str, Any]) -> dict[str, Any]:
        session["pending_gate"] = gate_info
        session["status"] = "awaiting_human"
        session["gate_future"] = asyncio.get_running_loop().create_future()
        decision = await session["gate_future"]  # Web 场景不设超时，人要想多久想多久
        session["pending_gate"] = None
        session["status"] = "running"
        return decision

    try:
        async for event in run_review(brief, ask_human=ask_human,
                                      session_id=session_id):
            session["live_feed"].append({**event, "timestamp": _now()})
            session["current_act"] = _ROLE_ACT.get(
                event["role"], session["current_act"]
            )
            if speaker := _DIGEST_ROLES.get(event["role"]):
                session["digest_parts"].append(f"{speaker}：{event['content']}")
            if report := event.get("report"):
                session["report"] = report
            if snapshot := event.get("snapshot"):
                if session["archive"] is None:
                    # Gate 2 结论即归档：通过案与 bad case 同等入档
                    session["archive"] = snapshot
                    session["status"] = (
                        "rejected" if snapshot.get("status") == "rejected"
                        else "approved"
                    )
                else:
                    # 复盘窗结束：轮数追加入档（归档 ≠ 封存）
                    session["archive"]["retro_turns"] = snapshot.get(
                        "retro_turns", 0
                    )
        if session["status"] not in ("approved", "rejected"):
            session["status"] = {"approve": "approved", "reject": "rejected"}.get(
                session.get("final_action"), "completed"
            )
        session["current_act"] = "act5_retro"
    except Exception as e:  # noqa: BLE001 — 会议失败要可见，不能静默
        session["status"] = "failed"
        session["error"] = str(e)[:500]


@router.post("/reviews", status_code=201)
async def create_review(payload: dict):
    """发起评审（BRIEF_LOCKED）"""
    try:
        brief = Brief(**payload.get("brief", {}))
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "BRIEF_INVALID", "message": str(e)}},
        )

    session_id = f"sess_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:4]}"
    _SESSIONS[session_id] = {
        "brief": brief.model_dump(),
        "created_at": _now(),
        "current_act": "brief_locked",
        "status": "running",
        "live_feed": [],
        "pending_gate": None,
        "gate_future": None,
        "report": None,
        "archive": None,
        "retro_logs": [],
        "digest_parts": [],
        "final_action": None,
        "error": None,
    }
    asyncio.create_task(_drive(session_id, brief.model_dump()))
    return {"session_id": session_id, "status": "created"}


@router.get("/reviews")
async def list_reviews():
    """会议列表（D4 新增）：任务中心与知识库看板的数据源

    只增不改：摘要素材，详情仍走 GET /reviews/{id}。
    """
    return {
        "reviews": [
            {
                "session_id": sid,
                "category": s["brief"].get("category", ""),
                "market": s["brief"].get("market", ""),
                "status": s["status"],
                "created_at": s["created_at"],
                "archive": s["archive"],
                "retro_turns": (s["archive"] or {}).get("retro_turns", 0),
            }
            for sid, s in sorted(
                _SESSIONS.items(),
                key=lambda kv: kv[1]["created_at"], reverse=True,
            )
        ]
    }


def _get_session(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "SESSION_NOT_FOUND", "message": session_id}},
        )
    return session


@router.get("/reviews/{session_id}")
async def get_review(session_id: str):
    """查询会议状态（前端轮询）"""
    session = _get_session(session_id)
    return {
        "session_id": session_id,
        "current_act": session["current_act"],
        "status": session["status"],
        "live_feed": session["live_feed"],
        "pending_gate": session["pending_gate"],
        "conflicts": (session["report"] or {}).get("dissent_records", []),
        "archive": session["archive"],
        "retro_logs": session["retro_logs"],
        "error": session["error"],
    }


@router.get("/reviews/{session_id}/report")
async def get_report(session_id: str):
    """获取立项建议书（decision 事件后可用）"""
    session = _get_session(session_id)
    if not session["report"]:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "REPORT_NOT_READY",
                              "message": "会议尚未到达决策"}},
        )
    return {"session_id": session_id, **session["report"]}


@router.post("/reviews/{session_id}/decision")
async def submit_decision(session_id: str, payload: dict):
    """人工决策：映射冻结契约动作 → 图门词汇，塞进 Future 唤醒挂起的门"""
    session = _get_session(session_id)
    future = session.get("gate_future")
    if not session["pending_gate"] or future is None or future.done():
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "SESSION_NOT_AT_GATE",
                              "message": "当前不在人工决策点"}},
        )

    action = payload.get("action")
    reason = payload.get("reason", "")
    if action in ("approve", "reject") and not reason:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DECISION_REASON_REQUIRED",
                    "message": "approve/reject 必须填写理由（学习官的负样本来源）",
                }
            },
        )

    if action == "approve":
        decision: dict[str, Any] = {"action": "confirm", "reason": reason}
    elif action == "reject":
        decision = {"action": "reject", "reason": reason}
    elif action == "revise":
        decision = {"action": "modify", "suggestion": reason,
                    "scope": payload.get("scope", "business")}
    elif action == "reweight":
        try:
            Weights.model_validate(payload.get("custom_weights") or {})
            assert payload.get("custom_weights")
        except (ValidationError, AssertionError):
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "WEIGHT_SUM_INVALID",
                                  "message": "五维权重之和必须为 1.0"}},
            )
        decision = {"action": "modify", "suggestion": reason or "重定权重",
                    "scope": "business",
                    "custom_weights": payload["custom_weights"]}
    elif action == "question":
        question = payload.get("question", "").strip()
        if not question:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "QUESTION_REQUIRED",
                                  "message": "question 必填"}},
            )
        decision = {"action": "question", "question": question}
    elif action == "chat":
        decision = {"action": "chat", "content": payload.get("content", "")}
    elif action == "done":
        decision = {"action": "done"}
    else:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "ACTION_UNKNOWN",
                              "message": f"未知动作: {action}"}},
        )

    session["final_action"] = action if action in ("approve", "reject") \
        else session["final_action"]
    future.set_result(decision)
    return {"session_id": session_id, "status": "decision_accepted",
            "mapped": decision}


@router.post("/reviews/{session_id}/retro")
async def retro_chat(session_id: str, payload: dict):
    """历史复盘入口（D3 新增）：归档后随时追问，问答追加进 retro_logs

    与图内首次复盘入口共用 retro_answer：LLM 基于本场证据链摘要作答，
    无 Key 时降级为产物索引。每轮对话累加 archive.retro_turns——
    人后来的理解与修正，同样是学习官的训练信号。
    """
    session = _get_session(session_id)
    if session["archive"] is None:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "RETRO_NOT_READY",
                              "message": "会议尚未归档，暂无复盘材料"}},
        )
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "RETRO_QUESTION_REQUIRED",
                              "message": "question 必填"}},
        )
    digest = "\n".join(session["digest_parts"])
    answer = retro_answer(digest, question)
    turn = {"question": question, "answer": answer, "timestamp": _now()}
    session["retro_logs"].append(turn)
    session["archive"]["retro_turns"] = session["archive"].get("retro_turns", 0) + 1
    return {"session_id": session_id, **turn}


@router.get("/weights/templates")
async def list_weight_templates():
    """权重模板列表"""
    labels = {"default": "默认均衡", "volume": "走量款", "image": "形象款", "profit": "利润款"}
    return {
        "templates": [
            {"key": k, "label": labels[k], "weights": w.model_dump()}
            for k, w in WEIGHT_TEMPLATES.items()
        ]
    }

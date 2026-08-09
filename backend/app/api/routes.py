"""API 路由 — 对应 docs/api/endpoints.md 约定（D1 冻结版）

当前为桩实现：端点形状已固定，业务逻辑待 LangGraph 编排层接入。
前端（组员B）可依此契约先行开发。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..config import WEIGHT_TEMPLATES
from ..schemas.brief import Brief

router = APIRouter(prefix="/api/v1", tags=["committee"])

# 演示期内存存储；接入编排层后替换为 LangGraph checkpoint 存储
_SESSIONS: dict[str, dict] = {}


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
        "current_act": "brief_locked",
        "status": "created",
        "acts_completed": [],
        "live_feed": [],
        "conflicts": [],
    }
    return {"session_id": session_id, "status": "created"}


@router.get("/reviews/{session_id}")
async def get_review(session_id: str):
    """查询会议状态（前端轮询）"""
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "SESSION_NOT_FOUND", "message": session_id}},
        )
    return {"session_id": session_id, **session}


@router.get("/reviews/{session_id}/report")
async def get_report(session_id: str):
    """获取立项建议书（到达 act4_decision 后可用）"""
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "SESSION_NOT_FOUND", "message": session_id}},
        )
    # TODO: 编排层接入后返回真实建议书
    return {
        "session_id": session_id,
        "proposals": [],
        "divergence_records": session.get("conflicts", []),
        "open_questions": [],
        "note": "编排层未接入，待 LangGraph 集成后返回真实数据",
    }


@router.post("/reviews/{session_id}/decision")
async def submit_decision(session_id: str, payload: dict):
    """人工决策（HUMAN_GATE）"""
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "SESSION_NOT_FOUND", "message": session_id}},
        )

    action = payload.get("action")
    if action in ("approve", "reject") and not payload.get("reason"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DECISION_REASON_REQUIRED",
                    "message": "approve/reject 必须填写理由（学习官的负样本来源）",
                }
            },
        )
    # TODO: 编排层接入后驱动 LangGraph resume
    session["human_decision"] = payload
    session["status"] = {"approve": "approved", "reject": "rejected"}.get(action, "revised")
    return {"session_id": session_id, **session}


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

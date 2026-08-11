"""企划工作室 API — AI 新品企划工作室的六步链路端点

    POST /api/v1/plans                      ① 创建企划任务（约束输入）
    GET  /api/v1/plans                      任务列表
    GET  /api/v1/plans/{id}                 任务详情（约束 + 状态）
    GET  /api/v1/plans/{id}/insights        ② 五看洞察（三Agent + 两块策展数据）
    GET  /api/v1/plans/{id}/opportunities   ③ 机会生成（3 张方向卡）
    POST /api/v1/plans/{id}/plan-card       ④⑤⑥ 选定方向 → 生成企划卡
    POST /api/v1/plans/{id}/revise          改稿沟通

    GET  /api/v1/insight-base               名创内部（策展数据独立页）
    GET  /api/v1/trend-gallery              流行元素板（策展数据独立页）
    GET  /api/v1/data-board                 数据看板（大盘）

数据策略「真管线、冻数据」：默认 fixture 模式返回冻结分析结果；
brief 传 mode="live" 走真实 LLM + 即梦出图（失败自动降级）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.planning import fixtures, pipeline
from app.schemas.planning import PlanBrief

router = APIRouter(prefix="/api/v1", tags=["planning"])


def _get_plan_or_404(plan_id: str) -> dict[str, Any]:
    plan = pipeline.get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, detail={"error": {"code": "PLAN_NOT_FOUND", "message": plan_id}})
    return plan


@router.post("/plans", status_code=201)
async def create_plan(payload: dict):
    brief = payload.get("brief") or payload  # 兼容直接传 brief
    # PlanBrief schema 校验（pydantic 保证必填字段 + 类型检查）
    try:
        PlanBrief.model_validate(brief)
    except Exception as e:
        raise HTTPException(422, detail={"error": {"code": "BRIEF_INVALID", "message": str(e)}})
    plan = pipeline.create_plan(brief)
    return {"plan_id": plan["plan_id"], "status": plan["status"]}


@router.get("/plans")
async def list_plans():
    return {"plans": pipeline.list_plans()}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    plan = _get_plan_or_404(plan_id)
    return {
        "plan_id": plan["plan_id"],
        "brief": plan["brief"],
        "mode": plan["mode"],
        "status": plan["status"],
        "selected_opportunity": plan["selected_opportunity"],
        "plan_card": plan.get("plan_card"),  # 已有企划卡（归档后回看用）
        "created_at": plan["created_at"],
    }


@router.get("/plans/{plan_id}/insights")
async def get_insights(plan_id: str):
    plan = _get_plan_or_404(plan_id)
    return {"plan_id": plan_id, **pipeline.get_insights(plan)}


@router.get("/plans/{plan_id}/opportunities")
async def get_opportunities(plan_id: str):
    plan = _get_plan_or_404(plan_id)
    return {"plan_id": plan_id, "opportunities": pipeline.get_opportunities(plan)}


@router.post("/plans/{plan_id}/plan-card")
async def generate_plan_card(plan_id: str, payload: dict):
    plan = _get_plan_or_404(plan_id)
    opportunity_id = payload.get("opportunity_id")
    if not opportunity_id:
        raise HTTPException(422, detail={"error": {"code": "OPPORTUNITY_REQUIRED", "message": "opportunity_id 必填"}})
    card = pipeline.generate_plan_card(plan, opportunity_id)
    if card is None:
        raise HTTPException(404, detail={"error": {"code": "OPPORTUNITY_NOT_FOUND", "message": opportunity_id}})
    return {"plan_id": plan_id, "plan_card": card}


@router.post("/plans/{plan_id}/revise")
async def revise_plan(plan_id: str, payload: dict):
    plan = _get_plan_or_404(plan_id)
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(422, detail={"error": {"code": "MESSAGE_REQUIRED", "message": "message 必填"}})
    if plan.get("plan_card") is None:
        raise HTTPException(409, detail={"error": {"code": "PLAN_CARD_NOT_READY", "message": "请先生成企划卡"}})
    return {"plan_id": plan_id, **pipeline.revise_plan(plan, message)}


@router.post("/plans/{plan_id}/archive")
async def archive_plan(plan_id: str):
    plan = _get_plan_or_404(plan_id)
    try:
        pipeline.archive_plan(plan)
    except ValueError as e:
        raise HTTPException(409, detail={"error": {"code": "PLAN_CARD_NOT_READY", "message": str(e)}})
    return {"plan_id": plan_id, "status": plan["status"], "archived_at": plan["archived_at"]}


# ── 策展数据独立页（非 Agent 现搜，提前策展）────────────────────

@router.get("/insight-base")
async def insight_base():
    return fixtures.INSIGHT_BASE


@router.get("/trend-gallery")
async def trend_gallery():
    return fixtures.TREND_GALLERY


@router.get("/data-board")
async def data_board():
    return fixtures.DATA_BOARD

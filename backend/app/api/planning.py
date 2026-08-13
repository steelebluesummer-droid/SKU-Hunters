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

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import ValidationError

from app.planning import fixtures, pipeline
from app.schemas.planning import PlanBrief

logger = logging.getLogger(__name__)

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
    except ValidationError as e:
        raise HTTPException(422, detail={"error": {"code": "BRIEF_INVALID", "message": str(e)}}) from e
    plan = pipeline.create_plan(brief)
    return {"plan_id": plan["plan_id"], "status": plan["status"]}


def _run_aily_flow(plan: dict[str, Any]) -> None:
    """Aily 发起后的后台流程：五看洞察 → 机会卡 → 推飞书卡片

    Aily 插件调用有超时限制（10-30s），不能同步等 pipeline，
    跑完由后端主动推消息（fail-soft，推送失败不影响任务状态）。
    """
    try:
        pipeline.get_insights(plan)
        opportunities = pipeline.get_opportunities(plan)
        from feishu.notify import notify_opportunities_ready
        notify_opportunities_ready(plan, opportunities)
    except Exception:
        logger.exception("Aily 后台流程异常，plan_id=%s", plan.get("plan_id"))


@router.post("/plans/aily-create", status_code=202)
async def aily_create_plan(payload: dict, background_tasks: BackgroundTasks):
    """Aily 轻入口：对话收集 PlanBrief → 立即返回，后台跑 pipeline

    入参与 POST /plans 一致（PlanBrief 字段），出参立即返回 plan_id；
    机会卡生成后推送飞书消息卡片（摘要 + 跳转前端选定方向）。
    """
    brief = payload.get("brief") or payload  # 兼容直接传 brief
    try:
        PlanBrief.model_validate(brief)
    except ValidationError as e:
        raise HTTPException(422, detail={"error": {"code": "BRIEF_INVALID", "message": str(e)}}) from e
    plan = pipeline.create_plan(brief)
    background_tasks.add_task(_run_aily_flow, plan)
    return {"plan_id": plan["plan_id"], "status": "running"}

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
    return {
        "plan_id": plan_id,
        "opportunities": pipeline.get_opportunities(plan),
        "processLog": fixtures.OPPORTUNITY_LOG,  # 机会生成思考过程（导师专项：呈现推理过程）
    }


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


def _run_archive_hooks(plan: dict[str, Any]) -> None:
    """归档后的飞书同步：①写入多维表格（企划资产库）②推归档卡片到通知群

    挂后台执行，归档响应不等飞书（演示现场不转圈）；
    fail-soft：任一失败只记日志，归档本身已落盘。
    """
    try:
        from feishu.bitable_sync import sync_plan_to_bitable
        from feishu.notify import notify_plan_archived
        sync_plan_to_bitable(plan)
        notify_plan_archived(plan)
    except Exception:
        logger.exception("归档后飞书同步异常（归档本身不受影响），plan_id=%s",
                         plan.get("plan_id"))


@router.post("/plans/{plan_id}/archive")
async def archive_plan(plan_id: str, background_tasks: BackgroundTasks):
    plan = _get_plan_or_404(plan_id)
    try:
        pipeline.archive_plan(plan)
    except ValueError as e:
        raise HTTPException(409, detail={"error": {"code": "PLAN_CARD_NOT_READY", "message": str(e)}})
    # 事件驱动同步挪后台：归档立即返回，多维表格写入 + 卡片推送随后执行
    background_tasks.add_task(_run_archive_hooks, plan)
    return {"plan_id": plan_id, "status": plan["status"], "archived_at": plan["archived_at"]}


# ── 策展数据独立页（非 Agent 现搜，提前策展）────────────────────

def _load_curated_module(topic: str, key: str, fallback: dict):
    """策展数据：有社媒证据取真实数据，否则回退 fixtures"""
    try:
        from app.insights.loaders.social_evidence import SocialEvidenceLoader
        return SocialEvidenceLoader().get_insight_bundle(topic)[key]
    except FileNotFoundError:
        return fallback


@router.get("/insight-base")
async def insight_base(topic: str = "小风扇"):
    return _load_curated_module(topic, "insightBase", fixtures.INSIGHT_BASE)


@router.get("/trend-gallery")
async def trend_gallery(topic: str = "小风扇"):
    return _load_curated_module(topic, "trendGallery", fixtures.TREND_GALLERY)


@router.get("/data-board")
async def data_board():
    return fixtures.DATA_BOARD

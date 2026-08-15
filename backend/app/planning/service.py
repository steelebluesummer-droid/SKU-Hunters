"""企划生成管线 · 业务编排层（service）

职责边界：编排业务流程（洞察 → 机会 → 企划卡 → 改稿 → 归档），
协调 repository（读写）/ insight_resolver（洞察解析）/ opportunity_engine（机会生成）/
plan_card_builder（企划卡组装）等下层模块；不直接操作存储、不做纯算法。

API 层（api/planning.py）只负责 HTTP：解析入参、调用 service、拼装出参。
"""

from __future__ import annotations

from typing import Any

from app.engine import llm
from app.planning import fixtures
from app.planning.insight_resolver import _resolve_insight_bundle
from app.planning.opportunity_engine import (
    _fallback_opportunities,
    _opportunities_from_bundle,
)
from app.planning.plan_card_builder import (
    _build_dynamic_plan_card,
    _find_opportunity,
)
from app.planning.repository import (
    _PLANS,
    _load_state,
    _now,
    _save_state,
    _snake_keys,
    create_plan,
    get_plan,
    list_plans,
    plan_write_lock,
)
from app.schemas.planning import InsightBundle, Opportunity, PlanBrief


class StateTransitionError(Exception):
    """状态机非法转移：当前状态不允许此操作（原子动作的前置状态校验失败）"""

    def __init__(self, expected: str, actual: str, action: str = ""):
        self.expected = expected
        self.actual = actual
        self.action = action
        super().__init__(f"状态不匹配：{action} 需要 {expected}，当前 {actual}")


__all__ = [
    "StateTransitionError",
    "archive_plan",
    "create_plan",
    "generate_insights",
    "generate_opportunities",
    "generate_plan_card",
    "get_insights",
    "get_opportunities",
    "get_plan",
    "list_plans",
    "review_plan",
    "revise_plan",
    "seed_demo",
]


# ── ② 五看洞察 ─────────────────────────────────────────

def get_insights(plan: dict[str, Any], advance: bool = False) -> dict[str, Any]:
    """五看洞察（只读）：真实社媒证据优先，无采集数据走 LLM 生成

    只读接口，不推进业务状态（advance 参数仅为旧兼容入口保留，新流程勿用）。
    """
    if advance and plan.get("status") != "archived":
        plan["status"] = "insights_ready"
    bundle = plan.get("insights")  # 先读缓存：已生成过的任务只读重开不重复烧 LLM
    if bundle is None:
        bundle = _resolve_insight_bundle(plan["brief"].get("category", ""), plan["brief"])
        _ = InsightBundle.model_validate(_snake_keys(bundle))
        plan["insights"] = bundle  # 缓存洞察：机会/企划卡复用，非采集品类不重复烧 LLM
        _save_state()  # 落盘：服务重启后缓存仍在，不重复触发 LLM
    return bundle


def generate_insights(plan: dict[str, Any]) -> dict[str, Any]:
    """原子业务动作：生成洞察，成功才推进状态并持久化（失败状态与产物不变）

    前置状态 brief_locked；成功后 status → insights_ready。
    取代「advance + GET」两请求组合，消除半完成态。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") != "brief_locked":
            raise StateTransitionError("brief_locked", plan.get("status"), "generate-insights")
        bundle = _resolve_insight_bundle(plan["brief"].get("category", ""), plan["brief"])
        _ = InsightBundle.model_validate(_snake_keys(bundle))
        plan["insights"] = bundle  # 缓存洞察：机会/企划卡复用，非采集品类不重复烧 LLM
        plan["status"] = "insights_ready"
        _save_state()
    return bundle


# ── ③ 机会生成 ─────────────────────────────────────────

def get_opportunities(plan: dict[str, Any], advance: bool = False) -> list[dict[str, Any]]:
    """机会生成（只读）：洞察 → 3 张方向卡，经 Opportunity schema 校验

    只读接口，不推进业务状态（advance 参数仅为旧兼容入口保留，新流程勿用）。
    """
    if advance and plan.get("status") != "archived":
        plan["status"] = "opportunities_ready"
    category = plan["brief"].get("category", "")
    brief = plan["brief"]
    bundle = plan.get("insights")
    if bundle is None:
        bundle = _resolve_insight_bundle(category, brief)
        plan["insights"] = bundle  # 重建时回写缓存：企划卡可复用洞察摘要
        _save_state()  # 落盘：服务重启后缓存仍在，不重复触发 LLM
    opps = _opportunities_from_bundle(category, bundle, brief)
    if not opps:
        opps = _fallback_opportunities(category, brief)
    for o in opps:
        _ = Opportunity.model_validate(_snake_keys(o))
    plan["opportunities"] = opps
    return opps


def generate_opportunities(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """原子业务动作：生成机会卡，成功才推进状态并持久化

    前置状态 insights_ready；成功后 status → opportunities_ready。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") != "insights_ready":
            raise StateTransitionError("insights_ready", plan.get("status"), "generate-opportunities")
        category = plan["brief"].get("category", "")
        brief = plan["brief"]
        bundle = plan.get("insights")
        if bundle is None:
            bundle = _resolve_insight_bundle(category, brief)
            plan["insights"] = bundle  # 重建时回写缓存：企划卡可复用洞察摘要
        opps = _opportunities_from_bundle(category, bundle, brief)
        if not opps:
            opps = _fallback_opportunities(category, brief)
        for o in opps:
            _ = Opportunity.model_validate(_snake_keys(o))
        plan["opportunities"] = opps
        plan["status"] = "opportunities_ready"
        _save_state()
    return opps


# ── ④⑤⑥ 企划卡生成 ────────────────────────────────────

def generate_plan_card(plan: dict[str, Any], opportunity_id: str) -> dict[str, Any] | None:
    """选定方向 → 生成完整新品企划卡（原子动作）

    一律走 _build_dynamic_plan_card（LLM 生成），无 fixture 模板路径。
    前置状态 opportunities_ready；成功后 status → plan_card_ready。
    返回值保持 camelCase 键名（前端契约）。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") != "opportunities_ready":
            raise StateTransitionError("opportunities_ready", plan.get("status"), "generate-plan-card")
        opportunity = _find_opportunity(plan, opportunity_id)
        if opportunity is None:
            return None

        card = _build_dynamic_plan_card(plan, opportunity)

        plan["selected_opportunity"] = opportunity_id
        plan["plan_card"] = card
        plan["status"] = "plan_card_ready"
        _save_state()
    return card


# ── 改稿沟通 ───────────────────────────────────────────

def revise_plan(plan: dict[str, Any], message: str) -> dict[str, Any]:
    """改稿：LLM 基于当前企划卡 + 修改意见作答；未配置则降级为固定回执

    仅 plan_card_ready 状态可改稿；archived 只读，禁止改稿（复盘追问用 review_plan）。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") == "archived":
            raise StateTransitionError("plan_card_ready", "archived", "revise")
        card = plan.get("plan_card") or {}
        answer = llm.complete(
            system_prompt=(
                "你是 SKU Hunters 新品企划工作室的企划助手。商品经理会对已生成的企划卡"
                "提出修改意见，你要说明会如何调整（涉及创意设计与商品策略两个环节，"
                "若影响成本需说明成本校验结果）。只依据给定企划卡内容作答，150 字以内。"
            ),
            user_prompt=(
                f"【当前企划卡】\n名称：{card.get('name', '')}\n概念：{card.get('concept', '')}\n"
                f"设计语言：{card.get('designLanguage', '')}\n功能点：{card.get('features', [])}\n"
                f"定价：{card.get('pricing', {})}\n成本校验：{card.get('costCheck', {})}\n\n"
                f"【修改意见】{message}"
            ),
            max_tokens=400,
        )
        if answer is None:
            answer = (
                "已收到修改意见。正式版将由创意设计模块调整方案，商品策略模块复核成本与价格带，"
                "概念图同步重新生成。（当前为冻结数据演示环境）"
            )
        turn = {"message": message, "reply": answer, "timestamp": _now()}
        plan["revise_logs"].append(turn)
    return turn


# ── 归档 ───────────────────────────────────────────────

def archive_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """复盘归档：企划卡定稿后归档入历史库（归档不是封存，后续可复盘追问）

    飞书同步（多维表格 + 通知卡片）由 API 层挂 BackgroundTasks 执行，
    归档响应不等飞书（见 api/planning.py _run_archive_hooks）。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") != "plan_card_ready":
            raise StateTransitionError("plan_card_ready", plan.get("status"), "archive")
        if plan.get("plan_card") is None:
            raise ValueError("企划卡尚未生成，不能归档")
        plan["status"] = "archived"
        plan["archived_at"] = _now()
        _save_state()
    return plan


# ── 演示任务预置 ───────────────────────────────────────

# ── 复盘追问（只读）───────────────────────────────────

def review_plan(plan: dict[str, Any], question: str) -> dict[str, Any]:
    """复盘追问（只读）：基于已归档企划卡回答追问，不修改 plan、不写 revise_logs

    与 revise_plan（改稿）分离：归档后只能复盘追问，不能改稿。
    """
    card = plan.get("plan_card") or {}
    answer = llm.complete(
        system_prompt=(
            "你是 SKU Hunters 新品企划工作室的复盘助手。商品经理会对已归档的企划案"
            "提出复盘追问，你要基于给定企划卡内容回答，说明该决策的依据与后续可复盘点。"
            "只依据给定企划卡内容作答，150 字以内。"
        ),
        user_prompt=(
            f"【已归档企划卡】\n名称：{card.get('name', '')}\n概念：{card.get('concept', '')}\n"
            f"定价：{card.get('pricing', {})}\n成本校验：{card.get('costCheck', {})}\n"
            f"商业化验证：{card.get('validation', [])}\n\n【复盘追问】{question}"
        ),
        max_tokens=400,
    )
    if answer is None:
        answer = "已收到复盘追问。该企划案已归档，可基于归档记录回顾决策依据。（当前为冻结数据演示环境）"
    return {"question": question, "answer": answer}


def seed_demo() -> None:
    """启动时预置演示任务（plan_id=demo），优先恢复上次持久化状态"""
    if "demo" in _PLANS:
        return

    saved = _load_state()
    if saved:
        # 恢复全部持久化任务（不只是 demo）——否则重启后 Aily 创建的任务 404
        # 旧状态文件 brief 可能是 camelCase，恢复时统一归一化为 snake_case
        for p in saved.values():
            p["brief"] = PlanBrief.model_validate(_snake_keys(p.get("brief") or {})).model_dump()
        _PLANS.update(saved)
        if "demo" in _PLANS:
            return

    _PLANS["demo"] = {
        "plan_id": "demo",
        # 与 create_plan 同路径归一化：camelCase fixtures → snake_case brief
        "brief": PlanBrief.model_validate(_snake_keys(fixtures.DEMO_BRIEF)).model_dump(),
        "mode": "fixture",
        "created_at": _now(),
        "status": "brief_locked",
        "selected_opportunity": None,
        "plan_card": None,
        "revise_logs": [],
    }


# 与旧 pipeline.py 保持一致：模块加载即预置演示任务
seed_demo()

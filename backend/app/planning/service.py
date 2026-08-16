"""企划生成管线 · 业务编排层（service）

职责边界：编排业务流程（洞察 → 机会 → 企划卡 → 改稿 → 归档），
协调 repository（读写）/ insight_resolver（洞察解析）/ opportunity_engine（机会生成）/
plan_card_builder（企划卡组装）等下层模块；不直接操作存储、不做纯算法。

API 层（api/planning.py）只负责 HTTP：解析入参、调用 service、拼装出参。
"""

from __future__ import annotations

from typing import Any

from app.engine import llm
from app.engine.strict_mode import is_demo_hidden
from app.planning import fixtures
from app.planning.cost_rules import cost_check
from app.planning.insight_resolver import _parse_llm_json, _resolve_insight_bundle
from app.planning.opportunity_discovery import build_opportunity_pool
from app.planning.opportunity_engine import (
    _fallback_opportunities,
    _opportunities_from_bundle,
)
from app.planning.plan_card_builder import (
    _build_dynamic_plan_card,
    _build_product_proposal,
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
from app.schemas.planning import InsightBundle, Opportunity, PlanBrief, PlanCard


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
    "rechoose_opportunity",
    "review_plan",
    "revise_apply",
    "revise_cancel",
    "revise_plan",
    "revise_preview",
    "seed_demo",
]


# ── ② 五看洞察 ─────────────────────────────────────────

def _ensure_opportunity_pool(plan: dict[str, Any], bundle: dict[str, Any]) -> None:
    """洞察 → 市场机会池：bundle 无 pool 时生成并回写（单一事实源）

    机会池是「五看洞察 → 产品决策」的中间产物，挂在 bundle 顶层；
    洞察驾驶舱 Block5 与机会生成消费同一份，禁止二次生成。
    pool 生成日志追加到 trendRadar.processLog，前端渐进日志可见。
    """
    if bundle.get("opportunityPool"):
        return
    category = plan["brief"].get("category", "")
    pool, pool_log = build_opportunity_pool(category, bundle, plan["brief"])
    if pool:
        bundle["opportunityPool"] = pool
    bundle.setdefault("trendRadar", {}).setdefault("processLog", []).extend(pool_log)


def _ensure_enrichment(plan: dict[str, Any], bundle: dict[str, Any]) -> None:
    """洞察增强（五段式驾驶舱）：旧缓存 bundle 无 enrichment 时懒补生成

    新 bundle 由 _resolve_insight_bundle 统一挂 enrichment；此处只补历史缓存。
    失败（无 Key/不合契约）不挂键，前端回退基础视图。
    """
    if bundle.get("enrichment"):
        return
    from app.planning.insight_enrichment import build_enrichment

    category = plan["brief"].get("category", "")
    enrichment = build_enrichment(category, bundle, plan["brief"])
    if enrichment is not None:
        bundle["enrichment"] = enrichment


def _ensure_consumer_voice_chains(plan: dict[str, Any], bundle: dict[str, Any]) -> None:
    """Consumer Voice Agent：用户决策画像 + 痛点归因链（引用机会池 id）

    依赖 opportunityPool 已生成（先 _ensure_opportunity_pool 再调本函数），
    归因链 supportsOpportunityIds 引用真实 pool id。失败不挂键，前端不渲染该块。
    """
    cv = bundle.setdefault("consumerVoice", {})
    if cv.get("painPointChains"):
        return
    from app.planning.consumer_voice_agent import build_consumer_voice_chains

    category = plan["brief"].get("category", "")
    result = build_consumer_voice_chains(category, bundle, plan["brief"])
    if result:
        cv["userProfile"] = result.get("userProfile")
        cv["painPointChains"] = result.get("painPointChains")


def _ensure_competitive_map_analysis(plan: dict[str, Any], bundle: dict[str, Any]) -> None:
    """Competitive Map Agent：需求满足矩阵 + 机会空位（验证机会池，不重新发现机会）

    依赖 decisionFactors（consumer voice 后）+ opportunityPool（机会池后），
    需求维度代码从 decisionFactors 提取，机会空位 supportsOpportunityIds 强绑机会池 id。
    """
    cm = bundle.setdefault("competitiveMap", {})
    if cm.get("needDimensions"):
        return
    from app.planning.competitive_map_agent import build_competitive_map_analysis

    category = plan["brief"].get("category", "")
    result = build_competitive_map_analysis(category, bundle, plan["brief"])
    if result:
        cm["needDimensions"] = result.get("needDimensions")
        cm["needSatisfaction"] = result.get("needSatisfaction")
        cm["opportunityGaps"] = result.get("opportunityGaps")


def _ensure_asset_fit(plan: dict[str, Any], bundle: dict[str, Any]) -> None:
    """Asset Fit Agent：机会方向 → 商品化适配（IP/设计语言/颜色/材质/包装）

    依赖 opportunityPool + insightBase.ipPool + consumerVoice 决策画像，
    不重新发现机会；ip 引用真实名创资产，无则空。失败不挂键。
    """
    if bundle.get("assetFit"):
        return
    from app.planning.asset_fit_agent import build_asset_fit

    category = plan["brief"].get("category", "")
    result = build_asset_fit(category, bundle, plan["brief"])
    if result:
        bundle["assetFit"] = result


def get_insights(plan: dict[str, Any], advance: bool = False) -> dict[str, Any]:
    """五看洞察（只读）：真实社媒证据优先，无采集数据走 LLM 生成

    只读接口，不推进业务状态（advance 参数仅为旧兼容入口保留，新流程勿用）。
    """
    if advance and plan.get("status") != "archived":
        plan["status"] = "insights_ready"
    bundle = plan.get("insights")  # 先读缓存：已生成过的任务只读重开不重复烧 LLM
    if not bundle:  # None 或历史坏缓存（空 dict）都重新生成
        bundle = _resolve_insight_bundle(plan["brief"].get("category", ""), plan["brief"])
        _ensure_opportunity_pool(plan, bundle)
        _ensure_consumer_voice_chains(plan, bundle)
        _ensure_competitive_map_analysis(plan, bundle)
        _ensure_asset_fit(plan, bundle)
        _ = InsightBundle.model_validate(_snake_keys(bundle))
        plan["insights"] = bundle  # 缓存洞察：机会/企划卡复用，非采集品类不重复烧 LLM
        _save_state()  # 落盘：服务重启后缓存仍在，不重复触发 LLM
    else:
        _ensure_opportunity_pool(plan, bundle)  # 旧缓存补 pool（不落盘，生成机会时统一落）
        _ensure_enrichment(plan, bundle)        # 旧缓存补 enrichment（五段式驾驶舱）
        _ensure_consumer_voice_chains(plan, bundle)  # 旧缓存补决策画像 + 归因链
        _ensure_competitive_map_analysis(plan, bundle)  # 旧缓存补需求满足矩阵 + 机会空位
        _ensure_asset_fit(plan, bundle)  # 旧缓存补资产适配
    return bundle


def _build_plan_data_context(plan: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """按任务 mode 构造并写入 data_context（live→feishu，fixture→fixture）"""
    from datetime import datetime, timezone

    from app.engine.task_data_context import build_fixture_context, build_live_context

    plan_id = plan["plan_id"]
    brief_mode = plan["brief"].get("mode", plan.get("mode", "fixture"))
    now = datetime.now(timezone.utc).isoformat()
    if brief_mode == "live":
        dc = bundle.get("dataContext") or {}
        ctx = build_live_context(
            plan_id=plan_id,
            record_count=dc.get("record_count", 0),
            evidence_count=dc.get("evidence_count", 0),
            snapshot_ids=[dc.get("snapshot_id", "")],
            generated_at=dc.get("generated_at") or now,
        )
    else:
        ctx = build_fixture_context(plan_id, now)
    plan["data_context"] = ctx.to_dict()
    return plan["data_context"]


def generate_insights(plan: dict[str, Any]) -> dict[str, Any]:
    """原子业务动作：生成洞察，成功才推进状态并持久化（失败状态与产物不变）

    前置状态 brief_locked；成功后 status → insights_ready。
    取代「advance + GET」两请求组合，消除半完成态。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") != "brief_locked":
            raise StateTransitionError("brief_locked", plan.get("status"), "generate-insights")
        bundle = _resolve_insight_bundle(plan["brief"].get("category", ""), plan["brief"])
        _ensure_opportunity_pool(plan, bundle)
        _ensure_consumer_voice_chains(plan, bundle)
        _ensure_competitive_map_analysis(plan, bundle)
        _ensure_asset_fit(plan, bundle)
        _ = InsightBundle.model_validate(_snake_keys(bundle))
        plan["insights"] = bundle  # 缓存洞察：机会/企划卡复用，非采集品类不重复烧 LLM
        _build_plan_data_context(plan, bundle)
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
    if not bundle:  # None 或历史坏缓存（空 dict）都重新生成
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
        if not bundle:  # None 或历史坏缓存（空 dict）都重新生成
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
        proposal = _build_product_proposal(plan, opportunity)
        # 概念图统一：以企划案图（product_proposal.design.imageUrl）为准回填企划卡
        proposal_img = (proposal.get("design") or {}).get("imageUrl", "")
        if proposal_img:
            card["conceptImage"] = proposal_img

        plan["selected_opportunity"] = opportunity_id
        plan["plan_card"] = card
        plan["product_proposal"] = proposal  # 新品企划案（六模块，与旧 plan_card 并存）
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


# ── 改稿两步式：预览草案 / 确认应用 / 取消 ─────────────────

# 可被改稿覆盖的企划卡字段 → 中文标签
_REVISE_FIELD_LABELS = {
    "name": "产品名称",
    "concept": "产品概念",
    "designLanguage": "设计语言",
    "keywords": "关键词",
    "features": "功能点",
    "fusion": "跨品类融合",
    "pricing.price": "零售价",
    "pricing.reason": "定价理由",
    "schedule": "上新节奏",
    "validation": "验证指标",
}


def _norm_str(v: Any) -> str:
    return "" if v is None else str(v)


def _revise_draft_changes(draft_card: dict, plan_card: dict) -> list[dict]:
    """对比草案 card 与当前 plan_card，生成「修改前后对比」changes 列表"""
    changes: list[dict] = []
    for key, after in draft_card.items():
        if key == "pricing" and isinstance(after, dict):
            for sub, sub_val in after.items():
                changes.append({
                    "field": f"pricing.{sub}",
                    "label": _REVISE_FIELD_LABELS.get(f"pricing.{sub}", f"pricing.{sub}"),
                    "before": (plan_card.get("pricing") or {}).get(sub, ""),
                    "after": sub_val,
                })
        else:
            changes.append({
                "field": key,
                "label": _REVISE_FIELD_LABELS.get(key, key),
                "before": plan_card.get(key, ""),
                "after": after,
            })
    return changes


def _apply_draft_to_card(plan_card: dict, draft_card: dict) -> dict:
    """把草案字段覆盖到企划卡副本（类型规整，仅覆盖草案中出现的字段）"""
    import copy as _copy
    new_card = _copy.deepcopy(plan_card)
    for key, val in draft_card.items():
        if key == "pricing" and isinstance(val, dict):
            pricing = dict(new_card.get("pricing") or {})
            for sub, sub_val in val.items():
                pricing[sub] = _norm_str(sub_val)
            new_card["pricing"] = pricing
        elif key in ("keywords", "features", "validation"):
            new_card[key] = [_norm_str(x) for x in (val or []) if _norm_str(x).strip()]
        elif key == "schedule":
            new_card[key] = [
                {"time": _norm_str(x.get("time", "")), "action": _norm_str(x.get("action", ""))}
                for x in (val or []) if isinstance(x, dict)
            ]
        else:
            new_card[key] = _norm_str(val)
    return new_card


def revise_preview(plan: dict[str, Any], message: str) -> dict[str, Any]:
    """改稿草案：LLM 分析意见生成「拟修改内容」，不落盘正式数据

    仅非 archived 可改稿；草案暂存 plan.revise_draft（持久化），
    不改 plan_card、不改 status；由 revise_apply 确认后正式应用。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") == "archived":
            raise StateTransitionError("plan_card_ready", "archived", "revise-preview")
        card = plan.get("plan_card") or {}
        raw = llm.complete(
            system_prompt=(
                "你是 SKU Hunters 新品企划工作室的改稿助手。商品经理会对已生成的企划卡提出修改意见。"
                "你要：1) 分析意见，说明将如何调整；2) 生成「拟修改内容」草稿。"
                "只修改与意见相关的字段，无关字段不输出。"
                "输出 JSON（不要输出其他文字）：\n"
                '{"reply": "对修改意见的分析说明（150 字以内）", "card": {'
                '拟修改字段的新值，键为企划卡 camelCase 字段：'
                '"name","concept","designLanguage","keywords","features","fusion",'
                '"pricing":{"price":"55 元","reason":"..."},"schedule","validation"}}'
            ),
            user_prompt=(
                f"【当前企划卡】\n名称：{card.get('name', '')}\n概念：{card.get('concept', '')}\n"
                f"设计语言：{card.get('designLanguage', '')}\n功能点：{card.get('features', [])}\n"
                f"定价：{card.get('pricing', {})}\n成本校验：{card.get('costCheck', {})}\n\n"
                f"【修改意见】{message}"
            ),
            max_tokens=1200,
        )
        draft_card: dict[str, Any] = {}
        reply = "已生成修改草案，请确认后再应用。"
        if raw:
            data = _parse_llm_json(raw)
            if isinstance(data, dict):
                reply = _norm_str(data.get("reply", "") or reply)
                dc = data.get("card")
                if isinstance(dc, dict):
                    draft_card = {
                        k: v for k, v in dc.items()
                        if k in _REVISE_FIELD_LABELS or (k == "pricing" and isinstance(v, dict))
                    }
        changes = _revise_draft_changes(draft_card, card)
        plan["revise_draft"] = {"message": message, "reply": reply, "card": draft_card}
        _save_state()
    return {"reply": reply, "changes": changes, "card": draft_card}


def revise_apply(plan: dict[str, Any]) -> dict[str, Any]:
    """确认应用修改：二次校验成本/价格/schema，通过后更新企划卡并保存旧版本

    前置：已有 revise_draft（preview 生成）；非 archived。
    成功：旧 plan_card 快照追加到 plan_card_history，更新 plan_card，
    写 revise_logs，清除草案。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") == "archived":
            raise StateTransitionError("plan_card_ready", "archived", "revise-apply")
        draft = plan.get("revise_draft")
        if not draft:
            raise ValueError("没有待应用的修改草案，请先提交修改意见生成草案")
        old_card = plan.get("plan_card") or {}
        draft_card = draft.get("card") or {}
        if not draft_card:
            raise ValueError("草案为空，无可应用修改")
        new_card = _apply_draft_to_card(old_card, draft_card)
        # 二次校验：成本 + schema
        brief = plan.get("brief") or {}
        cost_limit = float(brief.get("cost_limit", brief.get("costLimit", 25)))
        check = cost_check(
            {"pricing": {"price": (new_card.get("pricing") or {}).get("price", "")}},
            cost_limit,
        )
        new_card["costCheck"] = check.model_dump()
        if not check.passed:
            raise ValueError(f"修改后未通过成本校验：{check.reason}")
        try:
            PlanCard.model_validate(_snake_keys(new_card))
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"修改后企划卡未通过 schema 校验：{e}")
        # 保存旧版本
        history = plan.setdefault("plan_card_history", [])
        history.append({
            "version": len(history) + 1,
            "applied_at": _now(),
            "message": draft.get("message", ""),
            "card": old_card,
        })
        # 更新企划卡
        plan["plan_card"] = new_card
        # 写改稿日志（标记已应用）
        plan["revise_logs"].append({
            "message": draft.get("message", ""),
            "reply": draft.get("reply", ""),
            "applied": True,
            "version": len(history),
            "timestamp": _now(),
        })
        # 清除草案
        plan["revise_draft"] = None
        _save_state()
    return {"plan_card": new_card, "version": len(history), "history_count": len(history)}


def revise_cancel(plan: dict[str, Any]) -> dict[str, Any]:
    """取消本次改稿：清除草案，不修改任何内容"""
    with plan_write_lock(plan["plan_id"]):
        plan["revise_draft"] = None
        _save_state()
    return {"plan_card": plan.get("plan_card") or {}}


# ── 重新选择机会方向 ───────────────────────────────────

def rechoose_opportunity(plan: dict[str, Any]) -> dict[str, Any]:
    """重新选择机会方向：plan_card_ready → opportunities_ready（原子动作）

    返回换方向（前端「返回换方向」按钮）需要回到机会选择步骤。
    清除已选方向及相关产物，使后续能再次 generate-plan-card，避免触发状态机保护。
    清除：selected_opportunity、plan_card、product_proposal、revise_logs。
    前置状态 plan_card_ready；成功后 status → opportunities_ready。
    """
    with plan_write_lock(plan["plan_id"]):
        if plan.get("status") != "plan_card_ready":
            raise StateTransitionError("plan_card_ready", plan.get("status"), "rechoose-opportunity")
        plan["selected_opportunity"] = None
        plan["plan_card"] = None
        plan["product_proposal"] = None
        plan["revise_logs"] = []
        plan["status"] = "opportunities_ready"
        _save_state()
    return plan

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

    if is_demo_hidden():
        return  # 严格模式不预置演示任务（已有持久化 demo 已在上方恢复，且 API 层隐藏）
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

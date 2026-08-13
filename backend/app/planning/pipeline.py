"""AI 新品企划工作室 — 企划生成管线（真管线、冻数据）

业务链路（对应全景设计文档 v2.0）：

    ① 企划约束（人工下达） → ② 五看洞察（趋势/用户/竞品 三Agent并行
       + 名创内部 Insight Base + 流行元素板 Trend Gallery 两块策展数据）
    → ③ 机会生成（3 张方向卡，挂依据链，人选 1）
    → ④ 创意设计（概念/视觉/功能 + 即梦文生图）
    → ⑤ 商品策略（定价/成本校验/上新节奏，成本超标打回创意重做）
    → ⑥ 新品企划卡（模板组装，非 LLM 自由发挥）

数据策略：fixture 模式为默认（样本提前采集 + LLM 离线分析固化）；
LLM 是增强层——mode="live" 时走真实调用，失败自动降级回 fixture。

所有输入输出均通过 pydantic Schema 校验（schemas/planning.py），
前后端契约收敛为 JSON Schema，素材替换只改 fixtures.py。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.engine import llm
from app.planning import fixtures
from app.schemas.planning import (
    CostCheck,
    InsightBundle,
    Opportunity,
    PlanBrief,
    PlanCard,
    PlanSummary,
)
from app.services import jimeng

# ── 内部工具 ───────────────────────────────────────────────

def _camel_to_snake(name: str) -> str:
    """camelCase → snake_case 键名转换"""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _snake_keys(obj: Any) -> Any:
    """递归转换 dict 的全部键 camelCase → snake_case，列表和标量直通"""
    if isinstance(obj, dict):
        return {_camel_to_snake(k): _snake_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_snake_keys(v) for v in obj]
    return obj

# ── 任务存储（内存 + JSON 文件持久化）────────────────────────
_PLANS: dict[str, dict[str, Any]] = {}
_STATE_DIR = Path(__file__).resolve().parents[2] / "data"  # backend/data/
_STATE_FILE = _STATE_DIR / "plans_state.json"


def _save_state() -> None:
    """将全部任务状态落盘到 JSON 文件（重启恢复用）"""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {}
    for pid, p in _PLANS.items():
        payload[pid] = {
            "plan_id": p["plan_id"],
            "brief": p["brief"],
            "mode": p["mode"],
            "created_at": p["created_at"],
            "status": p["status"],
            "selected_opportunity": p.get("selected_opportunity"),
            "plan_card": p.get("plan_card"),
            "revise_logs": p.get("revise_logs", []),
            "archived_at": p.get("archived_at"),
        }
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_state() -> dict[str, dict[str, Any]]:
    """从 JSON 文件恢复任务状态（不存在或损坏则返回空）"""
    if not _STATE_FILE.is_file():
        return {}
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_plan(brief: dict[str, Any]) -> dict[str, Any]:
    """① 企划约束：冻结人工输入，经 PlanBrief schema 校验后建档"""
    # 先归一化键名（前端/DEMO_BRIEF 是 camelCase，PlanBrief 无别名会静默丢字段）
    validated = PlanBrief.model_validate(_snake_keys(brief))
    plan_id = f"plan_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:4]}"
    plan = {
        "plan_id": plan_id,
        "brief": validated.model_dump(),
        "mode": brief.get("mode", "fixture"),  # fixture（默认）| live（真实 LLM，预留）
        "created_at": _now(),
        "status": "brief_locked",
        "selected_opportunity": None,
        "plan_card": None,
        "revise_logs": [],
    }
    _PLANS[plan_id] = plan
    return plan


def get_plan(plan_id: str) -> dict[str, Any] | None:
    return _PLANS.get(plan_id)


def list_plans() -> list[dict[str, Any]]:
    summaries = [
        PlanSummary(
            plan_id=p["plan_id"],
            theme=p["brief"].get("theme", ""),
            category=p["brief"].get("category", ""),
            audience=p["brief"].get("audience", ""),
            status=p["status"],
            created_at=p["created_at"],
        )
        for p in sorted(_PLANS.values(), key=lambda p: p["created_at"], reverse=True)
    ]
    return [s.model_dump() for s in summaries]


# ── ② 五看洞察 ─────────────────────────────────────────────

def get_insights(plan: dict[str, Any]) -> dict[str, Any]:
    """五看洞察：有社媒证据则返回真实数据（SocialEvidenceLoader），否则回退 fixtures

    真实数据键名与 fixtures 同构（camelCase），前端零改动即可消费。
    """
    # 归档过的任务不降级状态（只读接口不得覆盖归档状态）
    if plan.get("status") != "archived":
        plan["status"] = "insights_ready"
    bundle = _resolve_insight_bundle(plan["brief"].get("category", ""))
    # 契约校验：确保数据符合 InsightBundle schema（不改变输出格式）
    _ = InsightBundle.model_validate(_snake_keys(bundle))
    return bundle


def _resolve_insight_bundle(category: str) -> dict[str, Any]:
    """按品类取社媒真实证据；无对应数据回退冻结 fixtures（process_log 兼容）"""
    try:
        from app.insights.loaders.social_evidence import SocialEvidenceLoader
        bundle = SocialEvidenceLoader().get_insight_bundle(category)
        bundle["trendRadar"]["heatCurve"] = _load_heat_curve()
        return bundle
    except FileNotFoundError:
        return {
            "trendRadar": fixtures.TREND_RADAR,
            "consumerVoice": fixtures.CONSUMER_VOICE,
            "competitiveMap": fixtures.COMPETITIVE_MAP,
            "insightBase": fixtures.INSIGHT_BASE,
            "trendGallery": fixtures.TREND_GALLERY,
        }


def _load_heat_curve() -> dict[str, Any] | None:
    """从 Google Trends 冻结快照注入热度曲线（存在才注入，否则前端留空）"""
    try:
        path = Path(__file__).resolve().parents[2] / "data" / "google_trends_snapshot.json"
        if not path.is_file():
            return None
        snap = json.loads(path.read_text(encoding="utf-8"))
        return {"weeks": snap["weeks"], "series": snap["series"]}
    except Exception:
        return None

def get_opportunities(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """机会生成：洞察 → 3 张方向卡（每张挂四方依据链），经 Opportunity schema 校验

    有该品类的社媒证据则按其真实洞察生成方向卡，否则回退冻结 fixtures。
    """
    # 归档过的任务不降级状态（只读接口不得覆盖归档状态）
    if plan.get("status") != "archived":
        plan["status"] = "opportunities_ready"
    category = plan["brief"].get("category", "")
    try:
        bundle = _resolve_insight_bundle(category)
        opps = _opportunities_from_bundle(category, bundle)
        if not opps:
            return fixtures.OPPORTUNITIES
    except FileNotFoundError:
        return fixtures.OPPORTUNITIES
    for o in opps:
        _ = Opportunity.model_validate(_snake_keys(o))
    return opps


def _opportunities_from_bundle(category: str, bundle: dict) -> list[dict]:
    """从真实五看洞察派生 3 张机会卡（IP/痛点/场景三方向）"""
    tr = bundle["trendRadar"]; cv = bundle["consumerVoice"]
    cm = bundle["competitiveMap"]; ib = bundle["insightBase"]; tg = bundle["trendGallery"]
    signals = tr.get("signals", []); pains = cv.get("painPoints", [])
    scenes = cv.get("scenes", []); ip_pool = ib.get("ipPool", [])
    gap = cm.get("gapZone") or {}
    gap_label = gap.get("label", "") if isinstance(gap, dict) else str(gap)
    colors = tg.get("colors", []); exprs = tg.get("expressions", [])

    color0 = colors[0].get("name") if colors and isinstance(colors[0], dict) else (colors[0] if colors else "")
    expr0 = exprs[0].get("name") if exprs and isinstance(exprs[0], dict) else (exprs[0] if exprs else "")
    sig0 = signals[0] if signals else None
    sig1 = signals[1] if len(signals) > 1 else None
    pain0 = pains[0] if pains else None
    scene0 = scenes[0].get("name") if scenes else "日常"
    price_band = "49-99 元"
    for pb in cm.get("priceBands", []):
        if pb.get("band"):
            price_band = pb.get("price") or price_band
            break

    def ev(frm: str, text: str) -> dict:
        return {"from": frm, "text": text}

    opps: list[dict] = []

    # ① IP 联名款
    if ip_pool:
        # 压缩 IP 名避免挤爆窄卡片（取品牌主体，如"三丽鸥"）
        ip_name = str(ip_pool[0].get("name", ""))
        ip_short = (re.split(r"[（(]", ip_name)[0] or ip_name).strip()[:8]
        opps.append({
            "id": "ip-licensing", "emoji": "🎀",
            "title": f"{category} × {ip_short} 联名款",
            "direction": "IP联名风",
            "pitch": f"借势「{ip_short}」情绪势能，做{category}里的社交货币款",
            "priceBand": price_band,
            "keywords": [ip_short, color0, "联名限定"],
            "evidence": [
                ev("名创内部", f"IP 池：{ip_short}（{ip_pool[0].get('why','')[:50]}）"),
                ev("趋势洞察", f"{sig0['name']}（{sig0['metric']}）" if sig0 else ""),
                ev("流行元素", f"当季配色 {color0}"),
                ev("竞品分析", gap_label[:50] if gap_label else "差异化机会空白"),
            ],
        })

    # ② 痛点解决/功能升级款
    if pain0 or sig0:
        opps.append({
            "id": "pain-solution", "emoji": "💡",
            "title": f"{category}痛点解决升级款",
            "direction": "功能实用风",
            "pitch": f"直击「{pain0['text'][:22] if pain0 else '体验'}」痛点，做差异化功能",
            "priceBand": price_band,
            "keywords": [(pain0["text"][:12] if pain0 else ""), "品质升级"],
            "evidence": [
                ev("用户洞察", f"高频痛点：{pain0['text']}（{pain0['count']}条）" if pain0 else ""),
                ev("趋势洞察", f"{sig1['name']}（{sig1['metric']}）" if sig1 else ""),
                ev("竞品分析", gap_label[:50] if gap_label else "差异化机会空白"),
                ev("流行元素", f"当季配色 {color0 or '—'}"),
            ],
        })

    # ③ 场景情绪款
    opps.append({
        "id": "scene-emotion", "emoji": "✨",
        "title": f"{category}场景情绪款",
        "direction": "场景情绪风",
        "pitch": f"围绕「{scene0}」场景，用{expr0 or '情绪'}叙事做差异化",
        "priceBand": price_band,
        "keywords": [scene0, expr0, color0],
        "evidence": [
            ev("用户洞察", f"高频场景：{scene0}"),
            ev("流行元素", f"风格关键词：{expr0 or '—'}"),
            ev("竞品分析", gap_label[:50] if gap_label else "差异化机会空白"),
            ev("趋势洞察", f"{sig0['name']}（{sig0['metric']}）" if sig0 else ""),
        ],
    })

    return [o for o in opps if o]


# ── ⑤ 商品策略：成本校验 ────────────────────────────────────

# 名创小家电品类毛利率红线（校验规则写死，LLM 不得自由发挥）
MIN_GROSS_MARGIN = 0.30


def _parse_price(price_str: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", price_str)
    return float(m.group(1)) if m else None


def cost_check(plan_card: dict[str, Any], cost_limit: float) -> CostCheck:
    """商品策略校验回环：定价毛利率低于红线 → 打回创意设计调整

    fixture 模式下三个方向均已离线校验通过；live 模式校验不通过时
    由管线打回创意环节重出方案（最多 2 轮，仍不过则标记人工介入）。
    """
    price = _parse_price(plan_card.get("pricing", {}).get("price", ""))
    if price is None:
        return CostCheck(passed=False, reason="定价缺失，无法校验")
    margin = (price - cost_limit) / price
    return CostCheck(
        passed=margin >= MIN_GROSS_MARGIN,
        price=price,
        cost_limit=cost_limit,
        margin=round(margin, 3),
        reason=(
            f"毛利率 {margin:.0%} ≥ 红线 {MIN_GROSS_MARGIN:.0%}，校验通过"
            if margin >= MIN_GROSS_MARGIN
            else f"毛利率 {margin:.0%} 低于红线 {MIN_GROSS_MARGIN:.0%}，打回创意环节调整（降本或调价）"
        ),
    )


# ── ④⑤⑥ 企划卡生成 ────────────────────────────────────────

def generate_plan_card(plan: dict[str, Any], opportunity_id: str) -> dict[str, Any] | None:
    """选定方向 → 生成完整新品企划卡

    组装顺序：方向卡（机会生成）→ 创意方案 + 概念图（创意设计）
    → 定价/节奏/验证（商品策略 + 成本校验）→ PlanCard schema 校验。
    返回值保持 camelCase 键名（前端契约）。
    """
    template = fixtures.PLAN_TEMPLATES.get(opportunity_id)
    opportunity = next((o for o in fixtures.OPPORTUNITIES if o["id"] == opportunity_id), None)
    if template is None or opportunity is None:
        return None

    brief = plan["brief"]
    cost_limit = float(brief.get("cost_limit", brief.get("costLimit", 25)))

    # 概念图：fixture 模式用模板里冻结的即梦出图；live 模式实时重生成（失败回退冻结图）
    concept_image = template.get("conceptImage")
    if plan["mode"] == "live":
        concept_image = jimeng.generate_concept_image(
            prompt=_concept_prompt(template, opportunity),
            fallback=concept_image,
        )

    # 成本校验（CostCheck schema → pydantic 保证算术一致性）
    check = cost_check(template, cost_limit)

    # 思考过程呈现（导师专项意见）：模板冻结的创意/策略推理 +
    # 末行成本校验为管线实时计算结果（真管线：数字随约束输入变化）
    process_log = list(template.get("strategyLog", []))
    if check.price is not None:
        process_log.append(
            f"成本校验：定价 {check.price:g} 元 / 成本上限 {check.cost_limit:g} 元 → {check.reason}"
        )
    else:
        process_log.append(f"成本校验：{check.reason}")

    # ── 组装企划卡（camelCase，与前端契约一致）──
    card = {
        "name": template["name"],
        "conceptImage": concept_image,
        "concept": template["concept"],
        "designLanguage": template["designLanguage"],
        "keywords": template["keywords"],
        "features": template["features"],
        "fusion": template["fusion"],
        "pricing": template["pricing"],
        "schedule": template["schedule"],
        "validation": template["validation"],
        "processLog": process_log,
        "costCheck": check.model_dump(),
        "opportunityId": opportunity_id,
        "source": "fixture" if plan["mode"] == "fixture" else "live",
    }

    # pydantic 契约校验（camelCase → snake_case → PlanCard 校验，确保形状正确）
    _ = PlanCard.model_validate(_snake_keys(card))

    plan["selected_opportunity"] = opportunity_id
    plan["plan_card"] = card
    # 归档过的任务不降级状态（前端 PlanCard 回流时保护已归档状态）
    if plan.get("status") != "archived":
        plan["status"] = "plan_card_ready"
    _save_state()
    return card


def _concept_prompt(template: dict[str, Any], opportunity: dict[str, Any]) -> str:
    """即梦文生图 prompt：设计语言 + 关键词 → 视觉描述（商品渲染图风格）"""
    return (
        f"产品概念渲染图，{template['name']}，{template['designLanguage']}，"
        f"关键词：{'、'.join(template['keywords'])}，"
        f"风格方向：{opportunity['direction']}，名创优品风格，干净背景，柔光，高质感"
    )


# ── 改稿沟通 ───────────────────────────────────────────────

def revise_plan(plan: dict[str, Any], message: str) -> dict[str, Any]:
    """改稿：LLM 基于当前企划卡 + 修改意见作答；未配置则降级为固定回执"""
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


# ── 归档 ───────────────────────────────────────────────────

def archive_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """复盘归档：企划卡定稿后归档入历史库（归档不是封存，后续可复盘追问）

    飞书同步（多维表格 + 通知卡片）由 API 层挂 BackgroundTasks 执行，
    归档响应不等飞书（见 api/planning.py _run_archive_hooks）。
    """
    if plan.get("plan_card") is None:
        raise ValueError("企划卡尚未生成，不能归档")
    plan["status"] = "archived"
    plan["archived_at"] = _now()
    _save_state()
    return plan


# ── 演示任务预置 ───────────────────────────────────────────

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


seed_demo()

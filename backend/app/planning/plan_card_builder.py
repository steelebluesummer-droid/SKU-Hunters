"""新品企划卡组装器（plan card builder）：机会卡 → 完整企划卡

职责边界：纯函数，输入 plan + opportunity，输出企划卡 dict；
不修改 plan（selected_opportunity/plan_card/status 的落盘由 service 编排）。

fixture 模板命中走冻结模板路径；未命中（动态 opportunity_id）走动态拼装，
解决动态机会卡无法生成企划卡的问题。
"""

from __future__ import annotations

import re
from typing import Any

from app.planning import fixtures
from app.planning.cost_rules import cost_check
from app.planning.repository import _snake_keys
from app.schemas.planning import PlanCard
from app.services import jimeng


def _find_opportunity(plan: dict, opportunity_id: str) -> dict | None:
    """优先从 plan 里已保存的机会卡找（动态生成），其次 fixtures"""
    for o in plan.get("opportunities", []):
        if o.get("id") == opportunity_id:
            return o
    return next((o for o in fixtures.OPPORTUNITIES if o["id"] == opportunity_id), None)


def _derive_price_from_band(price_band: str) -> float:
    """价格带字符串 → 建议定价（取区间中值，保证成本校验有真实数字）"""
    nums = re.findall(r"\d+(?:\.\d+)?", price_band or "")
    if len(nums) >= 2:
        return round((float(nums[0]) + float(nums[1])) / 2, 1)
    if len(nums) == 1:
        return float(nums[0])
    return 59.0


def _concept_prompt_dynamic(opportunity: dict, brief: dict) -> str:
    """动态企划卡即梦 prompt：机会卡标题 + 方向 + 关键词 → 视觉描述"""
    return (
        f"产品概念渲染图，{opportunity.get('title', '')}，{opportunity.get('direction', '')}风格，"
        f"关键词：{'、'.join(opportunity.get('keywords', []) or [])}，"
        f"名创优品风格，干净背景，柔光，高质感"
    )


def _concept_prompt(template: dict[str, Any], opportunity: dict[str, Any]) -> str:
    """即梦文生图 prompt：设计语言 + 关键词 → 视觉描述（商品渲染图风格）"""
    return (
        f"产品概念渲染图，{template['name']}，{template['designLanguage']}，"
        f"关键词：{'、'.join(template['keywords'])}，"
        f"风格方向：{opportunity['direction']}，名创优品风格，干净背景，柔光，高质感"
    )


def _assemble_fixture_plan_card(plan: dict, template: dict, opportunity: dict, opportunity_id: str) -> dict:
    """fixture 模板命中路径：按冻结模板组装企划卡（原逻辑保留）"""
    brief = plan["brief"]
    cost_limit = float(brief.get("cost_limit", brief.get("costLimit", 25)))

    concept_image = template.get("conceptImage")
    if plan["mode"] == "live":
        concept_image = jimeng.generate_concept_image(
            prompt=_concept_prompt(template, opportunity),
            fallback=concept_image,
        )

    check = cost_check(template, cost_limit)

    process_log = list(template.get("strategyLog", []))
    if check.price is not None:
        process_log.append(
            f"成本校验：定价 {check.price:g} 元 / 成本上限 {check.cost_limit:g} 元 → {check.reason}"
        )
    else:
        process_log.append(f"成本校验：{check.reason}")

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
    _ = PlanCard.model_validate(_snake_keys(card))
    return card


def _build_dynamic_plan_card(plan: dict, opportunity: dict) -> dict:
    """动态企划卡：机会卡 + brief 模板化拼装（下限版本，字段齐全、过 PlanCard 契约）

    未命中 fixture 模板时走此路径，解决动态 opportunity_id 无法生成企划卡的问题。
    无论 mode 都尝试即梦出图，未配置/失败自动降级占位（fail-soft）。
    """
    brief = plan["brief"]
    category = brief.get("category", "")
    cost_limit = float(brief.get("cost_limit", brief.get("costLimit", 25)))
    opp_id = opportunity.get("id", "")
    direction = opportunity.get("direction", "")
    keywords = list(opportunity.get("keywords", []))
    price_band = opportunity.get("priceBand", "49-99 元")
    price = _derive_price_from_band(price_band)

    concept_image = jimeng.generate_concept_image(
        prompt=_concept_prompt_dynamic(opportunity, brief),
        fallback=None,
    )

    check = cost_check({"pricing": {"price": f"{price:g} 元"}}, cost_limit)

    process_log = [
        f"承接方向「{direction}」：锁定核心创意",
        "即梦文生图：设计语言 + 关键词组装 prompt，生成产品概念图",
        f"定价推导：{price_band} 机会带 → 建议 {price:g} 元",
    ]
    if check.price is not None:
        process_log.append(
            f"成本校验：定价 {check.price:g} 元 / 成本上限 {check.cost_limit:g} 元 → {check.reason}"
        )
    else:
        process_log.append(f"成本校验：{check.reason}")

    card = {
        "name": opportunity.get("title", f"{category}企划案"),
        "conceptImage": concept_image or "",
        "concept": opportunity.get("pitch", ""),
        "designLanguage": f"{direction}风格，名创优品设计语言",
        "keywords": keywords,
        "features": [f"{category}核心功能", "名创优品品质", "差异化设计"],
        "fusion": "跨品类流行元素融合",
        "pricing": {"price": f"{price:g} 元", "reason": f"落在 {price_band} 机会带"},
        "schedule": [
            {"time": "T-3月", "action": "设计打样 + 选样会评审"},
            {"time": "T-2月", "action": "成本谈判 + 下单备产"},
            {"time": "T-1月", "action": "社媒预热"},
            {"time": "T0", "action": "全国门店上市"},
        ],
        "validation": ["上市首 2 周动销率 ≥ 50%", "社媒自发 UGC 达标", "复购/评价正向率达标"],
        "processLog": process_log,
        "costCheck": check.model_dump(),
        "opportunityId": opp_id,
        "source": "fixture" if plan["mode"] == "fixture" else "live",
    }
    _ = PlanCard.model_validate(_snake_keys(card))
    return card

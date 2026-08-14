"""机会生成引擎（opportunity engine）：洞察 → 3 张方向卡（每张挂四方依据链）

职责边界：纯函数，输入 brief + 洞察 bundle，输出机会卡列表；不修改 plan、不做状态推进。

机会卡三方向：
  ① IP 联名款（IP 从 brief.ip_strategy 解析，不再无条件取 ip_pool[0]）
  ② 痛点解决 / 功能升级款
  ③ 场景情绪款
无社媒证据品类走 _fallback_opportunities 动态生成（不再回退小风扇 fixture）。
"""

from __future__ import annotations

import re


def _derive_price_band(brief: dict) -> str:
    """机会卡价格带：优先读 brief 的零售价格带，其次成本/预算，兜底固定带"""
    pr = brief.get("price_range") or brief.get("priceRange")
    if pr and len(pr) >= 2:
        try:
            lo, hi = int(pr[0]), int(pr[1])
            return f"{lo}-{hi} 元"
        except (TypeError, ValueError):
            pass
    rpb = brief.get("retail_price_band") or brief.get("retailPriceBand")
    if rpb:
        return str(rpb)
    return "49-99 元"


def _resolve_ip_for_opportunity(brief: dict, ip_pool: list) -> tuple[str, str]:
    """按 brief 的 ip_strategy 选 IP（不再无条件取 ip_pool[0]）。

    返回 (ip_short, ip_why)：优先匹配 brief 指定的 IP，匹配不到用 brief 名字兜底；
    brief 未指定时才回退 ip_pool 第一项。
    """
    strategy = brief.get("ip_strategy") or brief.get("ipStrategy") or []
    selected = strategy[0] if strategy else None
    if selected:
        for ip in ip_pool:
            name = str(ip.get("name", ""))
            if selected in name or name in selected:
                return _short_ip(name), str(ip.get("why", "") or ip.get("fit", ""))
        return _short_ip(str(selected)), ""
    if ip_pool:
        name = str(ip_pool[0].get("name", ""))
        return _short_ip(name), str(ip_pool[0].get("why", "") or ip_pool[0].get("fit", ""))
    return "", ""


def _short_ip(name: str) -> str:
    """压缩 IP 名避免挤爆窄卡片（取品牌主体，如"三丽鸥"）"""
    return (re.split(r"[（(]", name)[0] or name).strip()[:8]


def _opportunities_from_bundle(category: str, bundle: dict, brief: dict) -> list[dict]:
    """从真实五看洞察派生 3 张机会卡（IP/痛点/场景三方向）"""
    tr = bundle["trendRadar"]
    cv = bundle["consumerVoice"]
    cm = bundle["competitiveMap"]
    ib = bundle["insightBase"]
    tg = bundle["trendGallery"]
    signals = tr.get("signals", [])
    pains = cv.get("painPoints", [])
    scenes = cv.get("scenes", [])
    ip_pool = ib.get("ipPool", [])
    gap = cm.get("gapZone") or {}
    gap_label = gap.get("label", "") if isinstance(gap, dict) else str(gap)
    colors = tg.get("colors", [])
    exprs = tg.get("expressions", [])

    color0 = colors[0].get("name") if colors and isinstance(colors[0], dict) else (colors[0] if colors else "")
    expr0 = exprs[0].get("name") if exprs and isinstance(exprs[0], dict) else (exprs[0] if exprs else "")
    sig0 = signals[0] if signals else None
    sig1 = signals[1] if len(signals) > 1 else None
    pain0 = pains[0] if pains else None
    scene0 = scenes[0].get("name") if scenes else "日常"
    price_band = _derive_price_band(brief)

    def ev(frm: str, text: str) -> dict:
        return {"from": frm, "text": text}

    opps: list[dict] = []

    # ① IP 联名款（IP 从 brief.ip_strategy 解析，不再无条件取 ip_pool[0]）
    ip_short, ip_why = _resolve_ip_for_opportunity(brief, ip_pool)
    if ip_short:
        opps.append({
            "id": "ip-licensing", "emoji": "🎀",
            "title": f"{category} × {ip_short} 联名款",
            "direction": "IP联名风",
            "pitch": f"借势「{ip_short}」情绪势能，做{category}里的社交货币款",
            "priceBand": price_band,
            "keywords": [ip_short, color0, "联名限定"],
            "evidence": [
                ev("名创内部", f"IP 池：{ip_short}（{ip_why[:50]}）" if ip_why else f"IP 策略：{ip_short}"),
                ev("趋势洞察", f"{sig0.get('name', '')}（{sig0.get('metric', '')}）" if sig0 else ""),
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
            "pitch": f"直击「{pain0.get('text', '')[:22] if pain0 else '体验'}」痛点，做差异化功能",
            "priceBand": price_band,
            "keywords": [(pain0.get("text", "")[:12] if pain0 else ""), "品质升级"],
            "evidence": [
                ev("用户洞察", f"高频痛点：{pain0.get('text', '')}（{pain0.get('count', 0)}条）" if pain0 else ""),
                ev("趋势洞察", f"{sig1.get('name', '')}（{sig1.get('metric', '')}）" if sig1 else ""),
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
            ev("趋势洞察", f"{sig0.get('name', '')}（{sig0.get('metric', '')}）" if sig0 else ""),
        ],
    })

    return [o for o in opps if o]


def _fallback_opportunities(category: str, brief: dict) -> list[dict]:
    """无社媒证据品类：按品类名 + brief 动态生成 3 张方向卡（不再回退小风扇 fixture）"""
    price_band = _derive_price_band(brief)
    ip_short, _ip_why = _resolve_ip_for_opportunity(brief, [])

    def ev(frm: str, text: str) -> dict:
        return {"from": frm, "text": text}

    opps: list[dict] = []
    if ip_short:
        opps.append({
            "id": "ip-licensing", "emoji": "🎀",
            "title": f"{category} × {ip_short} 联名款",
            "direction": "IP联名风",
            "pitch": f"借势「{ip_short}」情绪势能，做{category}里的社交货币款",
            "priceBand": price_band,
            "keywords": [ip_short, "联名限定"],
            "evidence": [
                ev("名创内部", f"IP 策略：{ip_short}"),
                ev("趋势洞察", f"围绕 {category} 品类做 IP 化探索"),
                ev("竞品分析", "差异化机会空白"),
                ev("用户洞察", "以情绪价值驱动购买"),
            ],
        })
    opps.append({
        "id": "pain-solution", "emoji": "💡",
        "title": f"{category}痛点解决升级款",
        "direction": "功能实用风",
        "pitch": f"直击 {category} 使用痛点，做差异化功能升级",
        "priceBand": price_band,
        "keywords": ["品质升级", "差异化功能"],
        "evidence": [
            ev("用户洞察", f"{category} 高频痛点待采集"),
            ev("趋势洞察", "功能升级趋势"),
            ev("竞品分析", "差异化机会空白"),
            ev("名创内部", "供应链成本优势"),
        ],
    })
    opps.append({
        "id": "scene-emotion", "emoji": "✨",
        "title": f"{category}场景情绪款",
        "direction": "场景情绪风",
        "pitch": "围绕日常使用场景，用情绪叙事做差异化",
        "priceBand": price_band,
        "keywords": ["场景化", "情绪价值"],
        "evidence": [
            ev("用户洞察", "高频使用场景"),
            ev("流行元素", "当季风格关键词"),
            ev("竞品分析", "差异化机会空白"),
            ev("趋势洞察", "情绪消费趋势"),
        ],
    })
    return [o for o in opps if o]

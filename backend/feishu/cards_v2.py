"""飞书卡片 JSON 2.0 构造器 —— 群机器人闭环专用

只产出 schema 2.0 卡片（长连接的 card.action.trigger 仅支持新版回调）：
- brief_form_card：需求补全表单（品类 input + 联名 IP 单选下拉[限资源库] + 选填项），
  提交按钮 behaviors=callback，点击一次性把 form_value 回传。
- opportunity_choice_card：机会卡点，三张方向卡各带一个 callback 按钮（不全自动，人来点选）。
- notice_card：轻量状态/进度/错误提示卡。

协议要点（已核对官方文档，勿凭记忆改）：
- 顶层 {"schema":"2.0","header":{...},"body":{"elements":[...]}}；
- form 只能放在卡片根节点；form 内每个交互组件必须有非空且唯一的 name（否则 200530）；
- 提交按钮 form_action_type="submit" + behaviors=[{"type":"callback","value":{...}}]；
- 普通回传按钮同样用 behaviors callback；跳转按钮用 behaviors open_url。
"""

from __future__ import annotations

from typing import Any

# 下拉选项过多时的保护上限（飞书单组件 options 不宜无限膨胀）
_MAX_IP_OPTIONS = 100


def _pt(content: str) -> dict[str, str]:
    return {"tag": "plain_text", "content": str(content)}


def _md(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": str(content)}


def _label(text: str) -> dict[str, Any]:
    return _md(f"**{text}**")


def brief_form_card(
    session_key: str,
    ip_names: list[str],
    prefill: dict[str, str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """需求补全表单卡。

    Args:
        session_key: 会话键（chat_id|open_id），随提交回传以定位会话。
        ip_names: IP 资源库规范名列表（下拉唯一来源，不允许自由 IP）。
        prefill: 已从自然语言解析出的字段，用于回填（category/price_range/audience）。
        note: 顶部提示（如缺哪些必填、或“资源库中无该 IP”）。
    """
    prefill = prefill or {}
    elements: list[dict[str, Any]] = []

    if note:
        elements.append(_md(note))
        elements.append({"tag": "hr"})

    options = [
        {"text": _pt(name), "value": name}
        for name in ip_names[:_MAX_IP_OPTIONS]
    ]

    category_input: dict[str, Any] = {
        "tag": "input",
        "name": "category",
        "required": True,
        "placeholder": _pt("如：保温杯、香薰蜡烛、双肩包"),
        "width": "fill",
    }
    if prefill.get("category"):
        category_input["default_value"] = prefill["category"]

    price_input: dict[str, Any] = {
        "tag": "input",
        "name": "price_range",
        "required": False,
        "placeholder": _pt("如 39-99，留空默认 39-99 元"),
        "width": "fill",
    }
    if prefill.get("price_range"):
        price_input["default_value"] = prefill["price_range"]

    audience_input: dict[str, Any] = {
        "tag": "input",
        "name": "audience",
        "required": False,
        "placeholder": _pt("如 18-25 岁年轻女性，留空由 AI 判断"),
        "width": "fill",
    }
    if prefill.get("audience"):
        audience_input["default_value"] = prefill["audience"]

    form = {
        "tag": "form",
        "name": "brief_form",
        "direction": "vertical",
        "vertical_spacing": "8px",
        "elements": [
            _label("品类（必填）"),
            category_input,
            _label("联名 IP（必选，仅限资源库）"),
            {
                "tag": "select_static",
                "name": "ip",
                "required": True,
                "placeholder": _pt("请从资源库选择联名 IP"),
                "width": "fill",
                "options": options,
            },
            _label("目标价格带（选填）"),
            price_input,
            _label("目标人群（选填）"),
            audience_input,
            {
                "tag": "button",
                "name": "submit_brief_btn",
                "type": "primary",
                "form_action_type": "submit",
                "text": _pt("开始生成企划"),
                "behaviors": [
                    {
                        "type": "callback",
                        "value": {
                            "act": "submit_brief",
                            "session": session_key,
                        },
                    }
                ],
            },
        ],
    }
    elements.append(form)

    return {
        "schema": "2.0",
        "header": {
            "title": _pt("📝 补全新品企划信息"),
            "template": "wathet",
        },
        "body": {"elements": elements},
    }


def opportunity_choice_card(
    plan: dict[str, Any],
    opportunities: list[dict[str, Any]],
    frontend_base: str,
) -> dict[str, Any]:
    """机会卡点卡：逐方向展示，每个方向一个 callback 按钮让人点选（不全自动）。"""
    brief = plan.get("brief") or {}
    theme = brief.get("theme", "")
    category = brief.get("category", "")
    locked_ip = ""
    ip_strategy = brief.get("ip_strategy") or brief.get("ipStrategy") or []
    if isinstance(ip_strategy, list) and ip_strategy:
        locked_ip = str(ip_strategy[0])

    elements: list[dict[str, Any]] = [
        _md(
            f"**企划主题**：{theme}\n**品类**：{category}"
            + (f"\n**锁定联名 IP**：{locked_ip}" if locked_ip else "")
        ),
        _md("五看洞察已完成，AI 给出以下机会方向，**请点选一个方向**继续生成企划卡："),
        {"tag": "hr"},
    ]

    plan_id = plan.get("plan_id", "")
    for i, o in enumerate(opportunities[:3], 1):
        emoji = o.get("emoji", "")
        title = o.get("title") or o.get("direction") or f"方向 {i}"
        pitch = o.get("pitch", "")
        price_band = o.get("priceBand") or o.get("price_band", "")
        asset = o.get("assetFit") or o.get("asset_fit") or {}
        fit_ip = asset.get("ip", "")
        band = f"（{price_band}）" if price_band else ""
        ip_line = f"\n适配 IP：{fit_ip}" if fit_ip else ""
        elements.append(_md(f"**方向 {i}｜{emoji}{title}**{band}{ip_line}\n{pitch}"))
        elements.append(
            {
                "tag": "button",
                "name": f"pick_opp_btn_{i}",
                "type": "primary",
                "text": _pt(f"选择方向 {i}"),
                "behaviors": [
                    {
                        "type": "callback",
                        "value": {
                            "act": "pick_opp",
                            "plan_id": plan_id,
                            "opp_id": o.get("id", ""),
                        },
                    }
                ],
            }
        )
        elements.append({"tag": "hr"})

    task_url = f"{frontend_base.rstrip('/')}/tasks/{plan_id}"
    elements.append(
        {
            "tag": "button",
            "name": "open_studio_btn",
            "type": "default",
            "text": _pt("进入企划工作室查看"),
            "behaviors": [{"type": "open_url", "default_url": task_url}],
        }
    )

    return {
        "schema": "2.0",
        "header": {
            "title": _pt("🎯 请选择机会方向"),
            "template": "green",
        },
        "body": {"elements": elements},
    }


def notice_card(title: str, content: str, template: str = "blue") -> dict[str, Any]:
    """轻量状态/进度/错误提示卡。"""
    return {
        "schema": "2.0",
        "header": {"title": _pt(title), "template": template},
        "body": {"elements": [_md(content)]},
    }

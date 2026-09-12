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


def _loose(raw: Any) -> Any:
    """state 里少量 plan_card 字段可能被存成 JSON / Python repr 字符串，尽力还原为 dict/list；失败原样返回。"""
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if not s or s[0] not in "[{":
        return raw
    import ast
    import json
    for loader in (ast.literal_eval, json.loads):
        try:
            return loader(s)
        except (ValueError, SyntaxError):
            continue
    return raw


def brief_form_card(
    session_key: str,
    ip_options: list[Any],
    prefill: dict[str, str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """需求补全表单卡。

    Args:
        session_key: 会话键（chat_id|open_id），随提交回传以定位会话。
        ip_options: IP 策略下拉项，接受 [{value,label}]（三档：无外部联名/自有IP/外部联名，
                    由 nl_brief.list_ip_select_options 提供），兼容旧的 list[str]；
                    下拉为唯一来源，不允许自由输入外部 IP。
        prefill: 已从自然语言解析出的字段，用于回填（category/price_range/audience）。
        note: 顶部提示（如缺哪些必填、或“资源库中无该 IP”）。
    """
    prefill = prefill or {}
    elements: list[dict[str, Any]] = []

    if note:
        elements.append(_md(note))
        elements.append({"tag": "hr"})

    def _opt(item: Any) -> dict[str, str]:
        if isinstance(item, dict):
            value = str(item.get("value") or "")
            label = str(item.get("label") or value)
            return {"text": _pt(label), "value": value}
        return {"text": _pt(str(item)), "value": str(item)}

    options = [_opt(item) for item in (ip_options or [])[:_MAX_IP_OPTIONS]]

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
            _label("IP 策略（必选：无外部联名 / 自有 IP / 外部联名 IP）"),
            {
                "tag": "select_static",
                "name": "ip",
                "required": True,
                "placeholder": _pt("选择 IP 策略（自有 IP 已标注，外部 IP 仅限资源库内）"),
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
            + (f"\n**锁定 IP**：{locked_ip}" if locked_ip else "")
        ),
        _md("五看洞察已完成，AI 给出以下机会方向，**请点选一个方向**继续生成企划卡："),
        {"tag": "hr"},
    ]

    plan_id = plan.get("plan_id", "")

    def _clip(value: Any, limit: int) -> str:
        text = str(value or "").strip().replace("\n", " ")
        return text if len(text) <= limit else text[: limit - 1] + "…"

    for i, o in enumerate(opportunities[:3], 1):
        emoji = o.get("emoji", "")
        title = _clip(o.get("title") or o.get("direction") or f"方向 {i}", 42)
        pitch = o.get("pitch", "")
        price_band = o.get("priceBand") or o.get("price_band", "")
        direction = o.get("direction", "")
        confidence = o.get("confidence", 0)
        target_user = o.get("targetUser") or o.get("target_user", "")
        scenario = o.get("scenario", "")
        strategy = o.get("productStrategy") or o.get("product_strategy", "")
        pain = o.get("painPoint") or o.get("pain_point", "")
        gap = o.get("competitorGap") or o.get("competitor_gap", "")
        evidence = o.get("evidence") or []
        asset = o.get("assetFit") or o.get("asset_fit") or {}
        fit_ip = asset.get("ip", "")
        fit_reason = asset.get("ipReason") or asset.get("ip_reason", "")

        # 标题行：方向名 + 类型 / 置信度小标签
        tags = [f"`{direction}`"] if direction else []
        if confidence:
            tags.append(f"`置信度 {confidence}%`")
        block = [f"**方向 {i}｜{emoji}{title}**" + ("  " + "　".join(tags) if tags else "")]
        if pitch:
            block.append(_clip(pitch, 96))

        # 第一层：给谁 / 在哪用 / 价格带
        meta: list[str] = []
        if target_user:
            meta.append(f"👤 {_clip(target_user, 26)}")
        if scenario:
            meta.append(f"📍 {_clip(scenario, 18)}")
        if price_band:
            meta.append(f"💰 **{price_band}**")
        if meta:
            block.append("　".join(meta))

        # 第三层：怎么做（产品策略 + IP 适配）
        if strategy:
            block.append(f"🎯 **产品策略**：{_clip(strategy, 80)}")
        if fit_ip:
            block.append(
                f"🤝 **IP 适配 · {fit_ip}**：{_clip(fit_reason, 60)}"
                if fit_reason else f"🤝 **IP 适配**：{fit_ip}"
            )

        # 第二层：为什么值得做（痛点 / 竞品空白 / 依据链前两条）
        why: list[str] = []
        if pain:
            why.append(f"🔎 **对应痛点**：{_clip(pain, 56)}")
        if gap:
            why.append(f"📊 **竞品空白**：{_clip(gap, 56)}")
        for ev in evidence[:2]:
            src = ev.get("from", "依据")
            why.append(f"· [{src}] {_clip(ev.get('text', ''), 46)}")
        block.extend(why)

        elements.append(_md("\n".join(block)))
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


def research_confirm_card(plan: dict[str, Any], category: str) -> dict[str, Any]:
    """新品类（无任何真实数据）拦截卡：问是否登记到调研需求池。选是只登记、本次任务暂停。"""
    plan_id = plan.get("plan_id", "")
    elements: list[dict[str, Any]] = [
        _md(
            f"**新品类**：{category}\n"
            "该品类在五看数据库（飞书策展 + 本地采集）里还没有趋势、痛点、竞品价格带、热词等**真实数据**。"
        ),
        _md(
            "现在继续只会得到 **AI 推理版**（内容为模型估计、非真实采集）。建议先发起调研：\n"
            "点「✅ 发起调研」会把该品类登记到**调研需求池**（状态：待调研），由豆包工作伙伴订阅并补全数据；"
            "**本次任务到此暂停**，等数据填回 Base 后，你再在群里@我，就能基于真实数据生成企划。"
        ),
        {"tag": "hr"},
        {
            "tag": "button", "name": "request_research_btn", "type": "primary",
            "text": _pt("✅ 发起调研（登记到需求池）"),
            "behaviors": [{
                "type": "callback",
                "value": {"act": "request_research", "plan_id": plan_id, "category": category},
            }],
        },
        {
            "tag": "button", "name": "cancel_research_btn", "type": "default",
            "text": _pt("暂不调研"),
            "behaviors": [{
                "type": "callback",
                "value": {"act": "cancel_research", "plan_id": plan_id},
            }],
        },
    ]
    return {
        "schema": "2.0",
        "header": {"title": _pt("🔍 该品类暂无调研数据，是否发起调研？"), "template": "orange"},
        "body": {"elements": elements},
    }


def notice_card(title: str, content: str, template: str = "blue") -> dict[str, Any]:
    """轻量状态/进度/错误提示卡。"""
    return {
        "schema": "2.0",
        "header": {"title": _pt(title), "template": template},
        "body": {"elements": [_md(content)]},
    }


def review_report_card(
    plan: dict[str, Any],
    report: dict[str, str] | None,
    frontend_base: str = "",
) -> dict[str, Any]:
    """「先文档、后归档」的待确认卡：云文档已生成 → 人审阅 → 点『确认归档』才真正归档。

    report 为 build_plan_report 的返回 {url,title,document_id}；为 None 时是在线文档生成失败的降级
    （仍允许基于企划卡点确认归档，或进工作室查看）。确认按钮走 callback，act=confirm_archive。
    """
    brief = plan.get("brief") or {}
    card = plan.get("plan_card") or {}
    ins = plan.get("insights") or {}
    pricing = _loose(card.get("pricing"))
    price = pricing.get("price", "") if isinstance(pricing, dict) else ""
    name = card.get("name") or (report or {}).get("title") or brief.get("theme", "新品企划")
    plan_id = plan.get("plan_id", "")
    has_doc = bool(report and report.get("url"))

    elements: list[dict[str, Any]] = [_md(f"**{name}**")]
    if card.get("concept"):
        elements.append(_md(str(card["concept"])))
    elements.append(_md(
        "—— 完整企划已汇总为飞书在线文档，请先审阅 ——" if has_doc
        else "—— 企划卡已生成（在线文档暂未生成成功，可进工作室查看）——"
    ))
    elements.append(_md(
        f"**品类**：{brief.get('category', '') or '—'}　"
        f"**建议定价**：{price or '—'}　**数据来源**：{ins.get('dataSource', '') or '—'}"
    ))
    if has_doc:
        elements.append(_md("文档内含：五看洞察驾驶舱、机会方向、企划案全文、即梦概念图。"))
    elements.append({"tag": "hr"})
    elements.append(_md(
        "**请审阅，确认无误后点「✅ 确认归档」写入企划资产库；需要调整请先不点，"
        "进工作室改稿后重新生成。**"
    ))

    if has_doc:
        elements.append({
            "tag": "button", "name": "open_report_btn", "type": "primary",
            "text": _pt("📖 打开完整在线报告"),
            "behaviors": [{"type": "open_url", "default_url": report["url"]}],
        })
    elements.append({
        "tag": "button", "name": "confirm_archive_btn",
        "type": "default" if has_doc else "primary",
        "text": _pt("✅ 确认归档到企划资产库"),
        "behaviors": [{"type": "callback", "value": {"act": "confirm_archive", "plan_id": plan_id}}],
    })
    if frontend_base:
        elements.append({
            "tag": "button", "name": "open_studio_btn", "type": "default",
            "text": _pt("进入企划工作室改稿"),
            "behaviors": [{"type": "open_url",
                           "default_url": f"{frontend_base.rstrip('/')}/tasks/{plan_id}"}],
        })
    elements.append({"tag": "hr"})
    # 注意：卡片 schema 2.0 已移除 note 标签（错误 200861），备注一律用 markdown
    elements.append(_md("在你点「确认归档」前不会写入多维表；归档后将在「企划资产库」新增一行。"))

    return {
        "schema": "2.0",
        "header": {"title": _pt("📝 请审阅在线报告，确认后归档"), "template": "violet"},
        "body": {"elements": elements},
    }

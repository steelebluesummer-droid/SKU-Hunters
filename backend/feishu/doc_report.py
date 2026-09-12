"""把企划卡已定稿（plan_card_ready，尚未归档）的 plan 生成飞书在线文档（docx）：五看洞察驾驶舱 + 机会方向 + 企划案 + 即梦概念图。

运行时用应用身份（tenant_access_token）自动创建，供群闭环「先出在线报告、人工确认后再归档」时调用，
把文档链接发回群，用户在飞书内即可看全，不必跳转本地前端；点『确认归档』后才真正写入资产库。

- 块结构遵循飞书 docx OpenAPI；children 单批最多 50 块，内部自动分批。
- fail-soft：任一非关键小节/图片/分享设置失败都不拖垮整体，文档仍产出。
- 不打印 token / secret。
"""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any

import requests

from .auth import FeishuAuth
from .config import FeishuConfig

logger = logging.getLogger(__name__)

_OPEN = "https://open.feishu.cn/open-apis"
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_CONCEPT_DIR = _BACKEND_ROOT / "data" / "evidence" / "images" / "concepts"

# docx block_type 枚举（仅用到的）
T_TEXT, T_H1, T_H2 = 2, 3, 4
T_BULLET, T_ORDERED, T_QUOTE = 12, 13, 15
T_CALLOUT, T_DIVIDER, T_IMAGE, T_TABLE = 19, 22, 27, 31
_CHUNK = 45  # 单批追加块数上限（飞书上限 50，留余量）

# 字体色 FontColor：1粉 2橙 3黄 4绿 5蓝 6紫 7灰
PINK, ORANGE, YELLOW, GREEN, BLUE, PURPLE, GREY = 1, 2, 3, 4, 5, 6, 7
# 文字背景色（浅）：1浅粉 2浅橙 3浅黄 4浅绿 5浅蓝 6浅紫 7浅灰
BG_PINK, BG_ORANGE, BG_YELLOW, BG_GREEN, BG_BLUE, BG_PURPLE, BG_GREY = 1, 2, 3, 4, 5, 6, 7
# 高亮块底色（浅色系）：1浅红 2浅橙 3浅黄 4浅绿 5浅蓝 6浅紫 7浅灰
CB_RED, CB_ORANGE, CB_YELLOW, CB_GREEN, CB_BLUE, CB_PURPLE, CB_GREY = 1, 2, 3, 4, 5, 6, 7


def _coerce(raw: Any) -> Any:
    """state 里部分 plan_card 字段被存成 Python repr / JSON 字符串，尽力还原为 list/dict；失败原样返回。"""
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if not s or s[0] not in "[{":
        return raw
    for loader in (ast.literal_eval, json.loads):
        try:
            return loader(s)
        except (ValueError, SyntaxError):
            continue
    return raw


def _run(content: Any, bold: bool = False, color: int | None = None,
         bg: int | None = False) -> dict[str, Any]:  # type: ignore[assignment]
    st: dict[str, Any] = {"bold": bool(bold)}
    if color:
        st["text_color"] = color
    if bg:
        st["background_color"] = bg
    return {"text_run": {"content": str(content or ""), "text_element_style": st}}


def _blk(btype: int, key: str, runs: list[dict[str, Any]] | str) -> dict[str, Any]:
    if isinstance(runs, str):
        runs = [_run(runs)]
    return {"block_type": btype, key: {"elements": runs, "style": {}}}


def h1(t: str) -> dict[str, Any]:
    return _blk(T_H1, "heading1", [_run(t, True)])


def h2(t: str) -> dict[str, Any]:
    return _blk(T_H2, "heading2", [_run(t, True)])


def P(runs: list | str) -> dict[str, Any]:
    return _blk(T_TEXT, "text", runs)


def B(runs: list | str) -> dict[str, Any]:
    return _blk(T_BULLET, "bullet", runs)


def ordered(runs: list | str) -> dict[str, Any]:
    return _blk(T_ORDERED, "ordered", runs)


def Q(runs: list | str) -> dict[str, Any]:
    return _blk(T_QUOTE, "quote", runs)


def kv(label: str, value: Any, value_color: int | None = None) -> list[dict[str, Any]]:
    """加粗蓝色标签 + 普通（可带色）值，返回 runs（需再包进 P/B/O）。"""
    if value is None or value == "":
        return []
    return [_run(f"{label}：", True, BLUE), _run(value, False, value_color)]


def tags(label: str, words: list[str], bg: int = BG_PURPLE) -> list[dict[str, Any]]:
    """把若干短词做成带浅色底的『标签』样式 run。"""
    runs = [_run(f"{label}：", True, BLUE)] if label else []
    for w in words:
        runs.append(_run(f" {w} ", False, None, bg))
        runs.append(_run("  "))
    return runs


def divider() -> dict[str, Any]:
    return {"block_type": T_DIVIDER, "divider": {}}


def callout(children: list[dict[str, Any]], bg: int = CB_BLUE, border: int | None = None,
            color: int | None = None) -> dict[str, Any]:
    """高亮块容器 IR：children 在写入时追加进该 callout。"""
    style: dict[str, Any] = {"background_color": bg, "border_color": border or bg}
    if color:
        style["text_color"] = color
    return {"_callout": True, "style": style, "children": children}


def table(rows: list[list[Any]], header: bool = True) -> dict[str, Any]:
    """表格容器 IR：rows 为二维，单元格可为 str 或 runs 列表；首行统一加粗+浅灰底当表头。"""
    norm = []
    for ri, r in enumerate(rows):
        row = []
        for c in r:
            cell = c if isinstance(c, list) else ([_run("—", False, GREY)] if c is None else [_run(c)])
            cell_txt = "".join(x.get("text_run", {}).get("content", "") for x in cell).strip()
            if not cell_txt:  # 空单元格统一补淡灰占位，避免表格留白、错行
                cell = [_run("—", False, GREY)]
            if header and ri == 0:
                for rr in cell:
                    st = rr.setdefault("text_run", {}).setdefault("text_element_style", {})
                    st["bold"] = True
                    st["background_color"] = BG_GREY
            row.append(cell)
        norm.append(row)
    return {"_table": True, "rows": norm, "header": header}


def image_placeholder(path: str) -> dict[str, Any]:
    """内部占位：顺序追加时遇到它走『建空图片块→上传→replace_image』三步法插入真实图片。"""
    return {"_image_placeholder": True, "_path": path}


class DocReportBuilder:
    """根据 plan 构建并创建飞书在线报告文档。"""

    def __init__(self, auth: FeishuAuth, timeout: int = 20):
        self.auth = auth
        self.timeout = timeout

    # ── 低层 API ──────────────────────────────
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _create_document(self, title: str) -> str:
        resp = requests.post(
            f"{_OPEN}/docx/v1/documents", headers=self._headers(),
            json={"title": title[:100]}, timeout=self.timeout,
        )
        j = resp.json()
        if j.get("code") != 0:
            raise RuntimeError(f"创建文档失败 code={j.get('code')} msg={j.get('msg')}")
        return j["data"]["document"]["document_id"]

    def _post_children(self, doc_id: str, parent_id: str, index: int,
                       children: list[dict[str, Any]]) -> dict[str, Any]:
        resp = requests.post(
            f"{_OPEN}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children",
            headers=self._headers(), json={"index": index, "children": children},
            timeout=self.timeout,
        )
        j = resp.json()
        if j.get("code") != 0:
            raise RuntimeError(f"追加文档块失败 code={j.get('code')} msg={j.get('msg')}")
        return j

    def _append_plain(self, doc_id: str, parent_id: str, start: int, blocks: list[dict[str, Any]]) -> int:
        """向指定父块从 start 游标分批写普通块，返回写入块数。"""
        written = 0
        for i in range(0, len(blocks), _CHUNK):
            batch = blocks[i:i + _CHUNK]
            self._post_children(doc_id, parent_id, start + written, batch)
            written += len(batch)
        return written

    def _append_mixed(self, doc_id: str, blocks: list[dict[str, Any]]) -> None:
        """按顺序追加：普通块攒批；图片走三步法；callout/table 走容器两级写入。"""
        cursor = 0
        buf: list[dict[str, Any]] = []

        def flush() -> None:
            nonlocal cursor
            if buf:
                cursor += self._append_plain(doc_id, doc_id, cursor, buf)
                buf.clear()

        for blk in blocks:
            if blk.get("_image_placeholder"):
                flush()
                self._insert_image(doc_id, cursor, Path(blk["_path"]))
                cursor += 1  # 图片块在父块下占一个位置
            elif blk.get("_callout"):
                flush()
                self._insert_callout(doc_id, cursor, blk)
                cursor += 1
            elif blk.get("_table"):
                flush()
                self._insert_table(doc_id, cursor, blk)
                cursor += 1
            else:
                buf.append(blk)
                if len(buf) >= _CHUNK:
                    flush()
        flush()

    def _delete_range(self, doc_id: str, parent_id: str, start: int, end: int) -> None:
        """删除父块下 [start,end) 的子块（用于清掉新建 callout/cell 自带的空段落）；失败只记日志。"""
        if end <= start:
            return
        try:
            r = requests.delete(
                f"{_OPEN}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children/batch_delete",
                headers=self._headers(), json={"start_index": start, "end_index": end},
                timeout=self.timeout)
            j = r.json()
            if j.get("code") != 0:
                logger.warning("清理空块失败 code=%s msg=%s", j.get("code"), j.get("msg"))
        except requests.RequestException as e:  # noqa: BLE001
            logger.warning("清理空块异常：%s", e)

    def _insert_callout(self, doc_id: str, index: int, ir: dict[str, Any]) -> None:
        """高亮块：先建空壳拿 block_id，再把内部子块写进去，并删掉自带空段落；失败只降级。"""
        try:
            j = self._post_children(doc_id, doc_id, index,
                                    [{"block_type": T_CALLOUT, "callout": ir["style"]}])
            cid = (j.get("data") or {}).get("children", [{}])[0].get("block_id")
            kids = ir.get("children") or []
            if cid and kids:
                self._append_plain(doc_id, cid, 0, kids)  # 插到 index0，自带空段落被挤到末尾
                self._delete_range(doc_id, cid, len(kids), len(kids) + 1)
        except (requests.RequestException, KeyError, IndexError) as e:  # noqa: BLE001
            logger.warning("高亮块写入失败，已跳过：%s", e)

    @staticmethod
    def _column_widths(ncol: int) -> list[int]:
        """飞书表格列宽（px 数组，创建时按列指定；总宽撑满正文约 720px，避免右侧大片留白）。

        - 两栏键值表（维度/内容）：标签列偏窄、内容列加宽，减少内容折行；
        - 多列数据表：等宽，余数补到末列凑满总宽。
        飞书 column_width 为逐列整数数组（实测默认 [100,100]，过窄）。
        """
        total = 720
        if ncol <= 1:
            return [total]
        if ncol == 2:
            label_w = 190
            return [label_w, total - label_w]
        base = total // ncol
        widths = [base] * ncol
        widths[-1] += total - base * ncol
        return widths

    def _insert_table(self, doc_id: str, index: int, ir: dict[str, Any]) -> None:
        """表格：建空表拿行优先 cells，再逐格写文本；失败只降级。"""
        try:
            rows = ir.get("rows") or []
            if not rows:
                return
            ncol, nrow = len(rows[0]), len(rows)
            if ncol > 9 or nrow > 9:  # 飞书创建表格行/列均须 ≤9（实测 10 即 1770001），超规只跳过该表
                logger.error("表格超飞书 9×9 上限，已跳过：%d 行 × %d 列", nrow, ncol)
                return
            j = self._post_children(doc_id, doc_id, index, [{
                "block_type": T_TABLE,
                "table": {"property": {
                    "row_size": nrow,
                    "column_size": ncol,
                    "column_width": self._column_widths(ncol),
                }},
            }])
            tb = (j.get("data") or {}).get("children", [{}])[0]
            cells = (tb.get("table") or {}).get("cells") or []
            flat = [cell for r in rows for cell in r]  # 行优先
            for cid, runs in zip(cells, flat):
                if cid and runs:
                    self._post_children(doc_id, cid, 0, [_blk(T_TEXT, "text", runs)])
                    self._delete_range(doc_id, cid, 1, 2)  # 删掉单元格自带空段落
        except (requests.RequestException, KeyError, IndexError) as e:  # noqa: BLE001
            logger.warning("表格写入失败，已跳过：%s", e)

    def _insert_image(self, doc_id: str, index: int, image_path: Path) -> bool:
        """飞书 docx 插图三步法；失败只记日志，不拖垮整篇文档。"""
        try:
            j = self._post_children(doc_id, doc_id, index, [{"block_type": T_IMAGE, "image": {}}])
            block_id = (j.get("data") or {}).get("children", [{}])[0].get("block_id")
            if not block_id:
                logger.warning("图片空块创建失败，跳过插图")
                return False
            raw = image_path.read_bytes()
            up = requests.post(
                f"{_OPEN}/drive/v1/medias/upload_all",
                headers={"Authorization": f"Bearer {self.auth.get_token()}"},
                data={
                    "file_name": image_path.name,
                    "parent_type": "docx_image",
                    "parent_node": block_id,
                    "size": str(len(raw)),
                    "extra": "[]",
                },
                files={"file": (image_path.name, raw, "image/png")},
                timeout=60,
            ).json()
            file_token = (up.get("data") or {}).get("file_token")
            if up.get("code") != 0 or not file_token:
                logger.warning("上传概念图失败 code=%s msg=%s", up.get("code"), up.get("msg"))
                return False
            patch = requests.patch(
                f"{_OPEN}/docx/v1/documents/{doc_id}/blocks/{block_id}",
                headers=self._headers(),
                json={"replace_image": {"token": file_token}},
                timeout=self.timeout,
            ).json()
            if patch.get("code") != 0:
                logger.warning("绑定概念图失败 code=%s msg=%s", patch.get("code"), patch.get("msg"))
                return False
            logger.info("概念图已内嵌 doc=%s block=%s", doc_id, block_id)
            return True
        except (requests.RequestException, OSError) as e:  # noqa: BLE001
            logger.warning("概念图内嵌异常：%s", e)
            return False

    def _make_readable(self, doc_id: str) -> None:
        """开放组织内获得链接的人可阅读；失败只记日志（可手动分享）。"""
        try:
            resp = requests.patch(
                f"{_OPEN}/drive/v2/permissions/{doc_id}/public?type=docx",
                headers=self._headers(),
                json={"link_share_entity": "tenant_readable"}, timeout=self.timeout,
            )
            j = resp.json()
            if j.get("code") != 0:
                logger.warning("设置文档链接可读失败 code=%s msg=%s", j.get("code"), j.get("msg"))
        except requests.RequestException as e:  # noqa: BLE001
            logger.warning("设置文档分享异常：%s", e)

    # ── 内容组装 ──────────────────────────────
    def _resolve_concept_path(self, plan: dict[str, Any]) -> Path | None:
        card = plan.get("plan_card") or {}
        url = card.get("conceptImage") or ""
        if not url:
            return None
        name = url.rsplit("/", 1)[-1]
        cand = _CONCEPT_DIR / name
        return cand if cand.is_file() else None

    @staticmethod
    def _type_label(t: Any) -> str:
        return {
            "design_value": "设计价值", "scenario_growth": "场景增长",
            "pain_point_solution": "痛点解决", "emotional_consumption": "情绪消费",
            "technology_upgrade": "技术升级",
        }.get(t, str(t or ""))

    def build_blocks(self, plan: dict[str, Any], image_path: Path | None) -> list[dict[str, Any]]:
        """富排版：高亮结论卡 + 表格 + 有序步骤 + 引用原声 + 配色重点 + 图文一体 Hero，对齐前端信息架构。"""
        brief = plan.get("brief") or {}
        ins = plan.get("insights") or {}
        card = plan.get("plan_card") or {}
        proposal = _coerce(plan.get("product_proposal"))
        if not isinstance(proposal, dict):
            proposal = {}
        pos = proposal.get("positioning") or {}
        pd = proposal.get("design") or {}
        biz = proposal.get("business") or {}
        opps = plan.get("opportunities") or []
        sel = plan.get("selected_opportunity")
        selected_id = sel.get("opportunityId") if isinstance(sel, dict) else sel
        pool = ins.get("opportunityPool") or []
        pool_title = {p.get("id"): p.get("title", "") for p in pool}
        out: list[dict[str, Any]] = []

        def score_color(v: Any) -> int | None:
            try:
                n = float(v)
            except (TypeError, ValueError):
                return None
            return GREEN if n >= 4 else (ORANGE if n <= 2 else GREY)

        # ══════════ 封面 / Hero 决策区 ══════════
        head_name = proposal.get("name") or card.get("name") or brief.get("theme", "新品企划")
        out.append(h1(f"✨ {head_name}"))
        hero_lead = []
        if pos.get("slogan"):
            hero_lead.append(P([_run("Slogan　", True, BLUE), _run(pos["slogan"], True, BLUE)]))
        elif (proposal.get("background") or {}).get("marketOpportunity"):
            hero_lead.append(P([_run("一句话机会　", True, BLUE), _run(proposal["background"]["marketOpportunity"])]))
        # 关键词标签（对齐前端：IP联名 + 设计语言/材质/颜色切短词）
        seg: list[str] = []
        for src in (pd.get("designLanguage"), pd.get("material"), pd.get("color")):
            if src:
                seg += [x.strip() for x in str(src).replace("，", ",").replace("、", ",").replace("；", ",").split(",") if x.strip()]
        kws = list(dict.fromkeys(["IP联名"] + [x for x in seg if len(x) <= 8]))[:6]
        if hero_lead:
            out.append(callout(hero_lead, bg=CB_BLUE))
        # 决策信息表（封面一眼看到关键约束）
        price_strategy = str(pos.get("priceRange", "") or "")
        if biz.get("retailPrice"):
            price_strategy += f"，主推 {biz['retailPrice']}"
        cover_rows = [
            ["品类 / 主题", f"{brief.get('category', '')} · {brief.get('theme', '')}"],
            ["目标人群", pos.get("targetUser") or brief.get("audience") or "大众消费者"],
            ["核心场景", pos.get("scenario") or "—"],
            ["价格策略", price_strategy or str(brief.get("price_range", ""))],
            ["商业验证 / 成本", biz.get("costTarget") or f"成本上限 {brief.get('cost_limit', '')}"],
            ["生成方式", "AI 洞察引擎综合生成（社媒声量 · 竞品格局 · 名创内部资产）"],
        ]
        out.append(table([["决策项", "内容"]] + cover_rows))
        if kws:
            out.append(P(tags("关键词", kws, BG_PURPLE)))
        # 导读：一句话结论 + 全篇导航
        concl = sel.get("summary", "") if isinstance(sel, dict) else ""
        if not concl and pool:
            concl = pool[0].get("summary", "")
        guide = []
        if concl:
            guide.append(P([_run("📌 本篇结论　", True, GREEN), _run(str(concl))]))
        guide.append(P([_run("🧭 内容导航　", True, GREEN),
                        _run("一、五看洞察驾驶舱（趋势 → 用户 → 竞品 → 自身资产 → 流行元素 → IP 适配）；"
                             "二、已人工选定的机会方向；三、新品企划案（概念图 + 六大模块 + 落地排期）")]))
        out.append(callout(guide, bg=CB_GREEN))
        out += [divider(), h1("第一部分 · 五看洞察驾驶舱")]

        # ── 1 趋势机会雷达 ──────────
        trend = ins.get("trendRadar") or {}
        enrich = ins.get("enrichment") or {}
        out.append(h2("1 ｜ 趋势机会雷达（看趋势）"))
        # 数据口径：有真实采集标样本量；无采集则如实标注为 AI 估计，不把估计值伪装成实测
        dctx = plan.get("data_context") or {}
        rec_n = dctx.get("record_count") or 0
        plog = trend.get("processLog") or []
        if rec_n:
            out.append(callout([P([_run("📊 数据底座　", True, GREEN),
                                   _run(f"基于 {rec_n} 条真实采集记录（来源：{dctx.get('data_source', '—')}），结合 AI 综合研判生成。")])],
                               bg=CB_GREEN))
        elif plog:
            out.append(callout([P([_run("⚠️ 数据口径　", True, ORANGE),
                                   _run("本品类暂无本地社媒采集，以下趋势信号 / 热词 / 热度曲线为 AI 结合公开市场常识的推断，仅供企划方向参考。")])]
                               + [B(str(x)) for x in plog], bg=CB_YELLOW))
        lead = []
        if enrich.get("marketJudgment"):
            lead.append(P([_run("AI 市场判断　", True), _run(enrich["marketJudgment"])]))
        ts = enrich.get("trendSummary") or {}
        if ts.get("verdict"):
            lead.append(P([_run("AI 趋势判断　", True), _run(ts["verdict"])]))
        if lead:
            out.append(callout(lead, bg=CB_YELLOW))
        for m in ts.get("metrics", []):
            arrow = "↑ " if m.get("direction") == "up" else ""
            out.append(B([_run(f"{m.get('label', '')}：", True, BLUE),
                          _run(arrow + str(m.get("value", "")), True, ORANGE),
                          _run(f"（{m.get('note', '')}）", False, GREY)]))
        for s in trend.get("signals", []):
            out.append(B([_run(f"{s.get('name', '')}　", True),
                          _run(str(s.get("metric", "")), False, ORANGE),
                          _run(f"｜{s.get('period', '')}", False, GREY)]))
            if s.get("domains"):
                out.append(P([_run("关联领域：", False, GREY), _run("、".join(map(str, s["domains"])))]))
            if s.get("opportunity"):
                out.append(Q([_run("机会｜", True, GREEN), _run(s["opportunity"])]))
        hc = trend.get("heatCurve") or {}
        weeks = hc.get("weeks") or []
        hseries = (hc.get("series") or [])[:8]
        if weeks and hseries:
            # 飞书单表行列均 ≤9：周次做行、序列做列；周数过多时等间隔采样到最多 8 个时间点
            if len(weeks) <= 8:
                pick = list(range(len(weeks)))
            else:
                step = len(weeks) / 8
                pick = sorted({min(len(weeks) - 1, int(i * step)) for i in range(8)})
            out.append(P([_run(f"品类热度曲线（{weeks[0]}–{weeks[-1]}，共 {len(weeks)} 周；0-1 相对热度指数）",
                               True, BLUE)]))
            hrows = [["周次"] + [str(s.get("name", "")) for s in hseries]]
            for wi in pick:
                row = [str(weeks[wi])]
                for s in hseries:
                    data = s.get("data") or []
                    v = data[wi] if wi < len(data) else ""
                    row.append("" if v == "" else f"{float(v):.2f}")
                hrows.append(row)
            out.append(table(hrows))
            if len(weeks) > 8:
                out.append(P([_run(f"（共 {len(weeks)} 周，上表等间隔采样 {len(pick)} 个时间点以呈现趋势走向）",
                                   False, GREY)]))
        if trend.get("hotWords"):
            out.append(P(tags("热词", [str(x) for x in trend["hotWords"][:16]], BG_YELLOW)))
        for c in enrich.get("topicClusters", []):
            tps = c.get("topics", [])
            if tps:
                out.append(B([_run(f"用户讨论 · {c.get('type', '')}：", True, BLUE)] +
                             [_run("；".join(f"{t.get('name', '')}({t.get('count', '')})" for t in tps))]))
        for d in enrich.get("subCategoryTrends", []):
            out.append(B([_run(f"子品类 · {d.get('name', '')}　", True),
                          _run(f"样本 {d.get('records', '—')} 条，同比 {d.get('growthPct', '—')}", False, ORANGE),
                          _run(f"｜{d.get('note', '')}", False, GREY)]))
        sp = enrich.get("seasonPlan") or {}
        for p in sp.get("cycle", []):
            out.append(B(f"季节窗口 · {p.get('phase', '')}（{p.get('months', '')}）：{p.get('action', '')}"))
        if sp.get("launchSuggestion"):
            out.append(Q([_run("上市建议：", True, GREEN), _run(sp["launchSuggestion"])]))

        # ── 2 AI 机会池 ──────────
        if pool:
            out.append(h2("2 ｜ AI 机会池（方向排序与依据）"))
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}
            for it in pool:
                head = [_run(f"{medal.get(it.get('rank'), '#' + str(it.get('rank', '')))} {it.get('title', '')}  ", True),
                        _run(f" {self._type_label(it.get('opportunityType'))} ", False, None, BG_BLUE),
                        _run("　置信度 ", False, GREY), _run(f"{it.get('confidence', '—')}%", True, ORANGE)]
                kids = [P(head)]
                if it.get("summary"):
                    kids.append(P(it["summary"]))
                for e in it.get("evidenceSource", []):
                    kids.append(Q([_run(f"[{e.get('source', '')}] ", True, GREEN), _run(e.get("fact", ""))]))
                for r in it.get("reasoning", []):
                    kids.append(ordered([_run("信号 ", True, GREY), _run(str(r.get("signal", ""))),
                                   _run(" → 解读 ", True, GREY), _run(str(r.get("interpretation", ""))),
                                   _run(" → 机会 ", True, GREEN), _run(str(r.get("opportunity", "")))]))
                # 排名第一用高亮块突出，其余用普通标题块
                if it.get("rank") == 1:
                    out.append(callout(kids, bg=CB_ORANGE))
                else:
                    out.append(P(head))
                    out += kids[1:]

        # ── 3 用户需求 ──────────
        cv = ins.get("consumerVoice") or {}
        if cv:
            out.append(h2("3 ｜ 用户需求 · 实时摘要（看用户）"))
            up = cv.get("userProfile") or {}
            prof = []
            if up.get("userSegment"):
                prof.append(P([_run("用户分群　", True, PURPLE), _run(up["userSegment"])]))
            for label, k, bgc in (("核心场景", "usageScenario", BG_BLUE), ("使用任务", "userTask", BG_GREEN),
                                  ("购买动机", "purchaseMotivation", BG_PINK), ("决策因素", "decisionFactors", BG_YELLOW)):
                if up.get(k):
                    prof.append(P(tags(label, [str(x) for x in up[k]], bgc)))
            if prof:
                out.append(callout(prof, bg=CB_PURPLE))
            for c in cv.get("painPointChains", []):
                star = "⭐" * min(int(c.get("priority", 0) or 0), 5)
                out.append(B([_run(f"{star} {c.get('painPoint', '')}".strip(), True, PINK)]))
                if c.get("demandInterpretation"):
                    out.append(P([_run("需求归因：", True, BLUE), _run(c["demandInterpretation"])]))
                for q in c.get("consumerVoice", [])[:3]:
                    out.append(Q([_run("消费者原声　", False, GREY), _run(f"“{q}”")]))
                sup = c.get("supportsOpportunityIds") or []
                if sup:
                    out.append(P([_run("→ 支撑机会：", True, GREEN),
                                  _run("、".join(pool_title.get(i, i) for i in sup))]))
                es = c.get("evidenceSource") or {}
                if es:
                    out.append(P([_run("证据：", False, GREY),
                                  _run(f"{es.get('platform', '社媒')} · {'、'.join(map(str, es.get('keywords', [])))}"
                                       f"{(' · ' + str(es.get('count')) + ' 条原声') if es.get('count') is not None else ''}")]))
            for p in cv.get("painPoints", []):
                out.append(B([_run("TOP痛点 · ", True, PINK), _run(p.get("text", "")),
                              _run(f"（{p.get('count', '')} 条）", False, ORANGE)]))
            for sc in cv.get("scenes", []):
                out.append(B([_run(f"场景 · {sc.get('name', '')}：", True, BLUE),
                              _run(f"{sc.get('value', '')}%", False, ORANGE)]))
            for q in cv.get("quotes", []):
                out.append(Q([_run("消费者原声　", False, GREY),
                              _run(f"“{q.get('text', '')}” —— {q.get('source', '')}")]))
            if cv.get("summary"):
                out.append(callout([P([_run("洞察总结　", True, GREEN), _run(cv["summary"])])], bg=CB_GREEN))

        # ── 4 竞品分析 ──────────
        cm = ins.get("competitiveMap") or {}
        if cm:
            out.append(h2("4 ｜ 竞品分析（看对手）"))
            prods_all = cm.get("products", [])
            prods = prods_all[:8]  # 飞书单表 ≤9 行，只展开 TOP8
            if prods:
                rows = [["竞品", "价格", "设计评分", "核心卖点"]]
                for prod in prods:
                    sp = prod.get("sellingPoints")
                    sp_s = "、".join(map(str, sp)) if isinstance(sp, list) else prod.get("sellingPoint", "")
                    design = prod.get("designScore") or prod.get("design") or ""
                    nm = (str(prod.get("brand", "")) + " ") if prod.get("brand") else ""
                    price_v = prod.get("price")
                    rows.append([str(prod.get("name", nm) or ""),
                                 [_run(f"¥{price_v}" if price_v not in (None, "") else "—", False, ORANGE)],
                                 str(design or ""), str(sp_s or "")[:80]])
                out.append(table(rows))
                if len(prods_all) > 8:
                    out.append(P([_run(f"（竞品共 {len(prods_all)} 个，上表展示设计/相关度 TOP8）", False, GREY)]))
            dims = cm.get("needDimensions") or []
            mat: dict[str, dict[str, Any]] = {}
            for cell in cm.get("needSatisfaction", []):
                mat.setdefault(cell.get("competitor", ""), {})[cell.get("need", "")] = cell.get("score")
            if dims and mat:
                dims_use = dims[:8]  # 列数控制在 9 列内（含表头），避免超飞书表格列上限
                dim_tail = f"（需求维度共 {len(dims)} 项，仅展示前 8）" if len(dims) > 8 else ""
                mrows = [["竞品 \\ 需求"] + [str(x) for x in dims_use]]
                for comp, scores in list(mat.items())[:8]:  # 行也控制在 9 行内
                    row: list[Any] = [comp]
                    for dim in dims_use:
                        sv = scores.get(dim)
                        if sv is None:
                            row.append([_run("—", False, GREY)])  # 未评分项弱化，让有分数的格子更突出
                        else:
                            row.append([_run(str(sv), True, score_color(sv))])
                    mrows.append(row)
                comp_tail = f"，竞品仅列 TOP8 / 共 {len(mat)}" if len(mat) > 8 else ""
                out.append(P([_run(f"用户需求满足矩阵（0-5 分，绿=优势 / 橙=短板）{dim_tail}{comp_tail}", True, BLUE)]))
                out.append(table(mrows))
            for g in cm.get("opportunityGaps", []):
                kids = [P([_run("用户需求　", True, BLUE), _run(str(g.get("userNeed", "")))]),
                        P([_run("竞品不足　", True, PINK), _run(str(g.get("competitorGap", "")))]),
                        P([_run("→ 机会　", True, GREEN), _run(str(g.get("opportunity", "")))])]
                for w in g.get("why", [])[:3]:
                    kids.append(B(str(w)))
                out.append(callout(kids, bg=CB_ORANGE))
            pb = []
            for b in cm.get("priceBands", []):
                pb.append(f"{b.get('band', '')} {b.get('price', '')} {b.get('pct', '')}% {b.get('note', '')}".strip())
            if pb:
                out.append(B([_run("价格带分布：", True, BLUE), _run("；".join(pb))]))
            sw = [f"{s.get('word', '')}" + (f"×{s.get('count')}" if s.get("count") else "")
                  for s in cm.get("sellingPoints", [])]
            if sw:
                out.append(P(tags("卖点关键词", sw, BG_GREEN)))
            gap = cm.get("gapZone")
            gap_label = gap.get("label", "") if isinstance(gap, dict) else gap
            if gap_label or cm.get("gapZoneNote"):
                out.append(callout([P([_run("价格 × 设计感空白　", True, ORANGE),
                                       _run(str(gap_label or cm.get("gapZoneNote")))])], bg=CB_YELLOW))

        # ── 5 名创内部资产 ──────────
        base = ins.get("insightBase") or {}
        if base:
            out.append(h2("5 ｜ 名创内部资产（看自己）"))
            hits_all = base.get("hitProducts", [])
            hits = hits_all[:8]  # 飞书单表 ≤9 行
            if hits:
                hrows = [["爆品", "指数", "命中因素", "备注"]]
                for hp in hits:
                    hrows.append([str(hp.get("name", "")),
                                  [_run(str(hp.get("index", "")), True, ORANGE)],
                                  "、".join(map(str, hp.get("factors", []))), str(hp.get("note", ""))])
                out.append(table(hrows))
                if len(hits_all) > 8:
                    out.append(P([_run(f"（爆品库共 {len(hits_all)} 个，上表列指数 TOP8）", False, GREY)]))
            for ip in base.get("ipPool", []):
                fit = ip.get("fit", [])
                fit_s = "、".join(fit) if isinstance(fit, list) else str(fit)
                out.append(B([_run(f"IP · {ip.get('name', '')}", True, PURPLE),
                              _run(f"（{ip.get('status', '')}，热度 {ip.get('heat', '')}）：{fit_s}", False, GREY)]))
            if base.get("designLanguage"):
                out.append(P(tags("内部设计语言", [str(x) for x in base["designLanguage"]], BG_BLUE)))

        # ── 6 流行元素板 ──────────
        gallery = ins.get("trendGallery") or {}
        grows = []
        for label, key in (("流行色", "colors"), ("花纹", "patterns"), ("形态", "shapes"), ("表情/意象", "expressions")):
            items = gallery.get(key) or []
            if not items:
                continue
            names = []
            for it in items:
                if isinstance(it, dict):
                    nm = it.get("name", "")
                    if it.get("emoji"):
                        nm = f"{it['emoji']} {nm}"
                    if it.get("hex"):
                        nm += f" {it['hex']}"
                    names.append(nm)
                else:
                    names.append(str(it))
            grows.append([label, "、".join(names)])
        if grows:
            out.append(h2("6 ｜ 流行元素板"))
            out.append(table([["维度", "元素"]] + grows))

        # ── 7 联名 IP 资产适配 ──────────
        asset_fit = ins.get("assetFit") or []
        if isinstance(asset_fit, list) and asset_fit:
            out.append(h2("7 ｜ 联名 IP 资产适配"))
            for af in asset_fit:
                kids = [P([_run(f"{af.get('ip', '')}", True, PURPLE),
                           _run(f" → {pool_title.get(af.get('opportunityId', ''), af.get('opportunityId', ''))}")])]
                if af.get("targetConsumer"):
                    kids.append(P([_run("目标人群：", True, BLUE), _run(af["targetConsumer"])]))
                if af.get("designLanguage"):
                    kids.append(P([_run("设计语言：", True, BLUE), _run(af["designLanguage"])]))
                if af.get("ipReason"):
                    kids.append(P([_run("适配理由：", True, BLUE), _run(af["ipReason"])]))
                out.append(callout(kids, bg=CB_PURPLE))

        # ══════════ 第二部分：机会方向（人工点选）══════════
        out += [divider(), h1("第二部分 · 机会方向（已人工点选）")]
        for i, o in enumerate(opps, 1):
            af = o.get("assetFit") or {}
            chosen = bool(selected_id and o.get("id") == selected_id)
            head = [_run(("✅【已选定】" if chosen else f"方向{i} · ") + f"{o.get('emoji', '')} {o.get('title') or o.get('direction', '')}", chosen),
                    _run(f"（{o.get('priceBand') or o.get('price_band', '')}）", False, GREY),
                    _run("　置信度 ", False, GREY), _run(f"{o.get('confidence', '—')}%", True, ORANGE),
                    _run("　锁定IP ", False, GREY), _run(str(af.get("ip", "")), True, PURPLE)]
            kids = [P(head)]
            if o.get("pitch"):
                kids.append(P(o["pitch"]))
            for label, k, cc in (("目标人群", "targetUser", BLUE), ("核心场景", "scenario", BLUE),
                                 ("核心痛点", "painPoint", PINK), ("竞品缺口", "competitorGap", PINK),
                                 ("商品策略", "productStrategy", GREEN)):
                if o.get(k):
                    kids.append(P([_run(f"{label}：", True, cc), _run(str(o[k]))]))
            for ev in o.get("evidence", []):
                kids.append(Q([_run(f"[{ev.get('from', '')}] ", True, GREY), _run(ev.get("text", ""))]))
            out.append(callout(kids, bg=CB_GREEN) if chosen else P(head))
            if not chosen:
                out += kids[1:]

        # ══════════ 第三部分：新品企划案（图文一体 Hero + 五步链 + 六模块）══════════
        out += [divider(), h1("第三部分 · 新品企划案")]
        # —— 概念图 Hero：图 + 紧邻设计说明，图文一体 ——
        out.append(h2("🎨 产品概念图 · 即梦 AI 生成"))
        if image_path:
            out.append(image_placeholder(str(image_path)))
        else:
            out.append(P([_run("（概念图未能内嵌，可在企划工作室查看）", False, GREY)]))
        cap = []
        if pd.get("concept"):
            cap.append(P([_run("Concept 设计主题：", True, BLUE), _run(pd["concept"])]))
        if pd.get("designLanguage"):
            cap.append(P([_run("设计方向：", True, BLUE), _run(pd["designLanguage"])]))
        if cap:
            out.append(callout(cap, bg=CB_BLUE))  # 紧贴图下方，避免孤图

        # —— 五步决策链（有序）——
        if proposal:
            chain = [
                ("市场机会", (proposal.get("background") or {}).get("marketOpportunity")),
                ("用户洞察", (proposal.get("background") or {}).get("userNeed")),
                ("商品方向", proposal.get("name")),
                ("设计验证", pd.get("designLanguage")),
                ("商业评估", f"{biz.get('retailPrice', '')} · {biz.get('costTarget', '')}".strip(" ·")),
            ]
            chain = [c for c in chain if c[1]]
            if chain:
                out.append(P([_run("商品决策链", True, BLUE)]))
                for lab, txt in chain:
                    out.append(ordered([_run(f"{lab}　", True, BLUE), _run(str(txt))]))

            bg = proposal.get("background") or {}
            # 01 市场机会
            mk = []
            if bg.get("marketOpportunity"):
                mk.append(P([_run(bg["marketOpportunity"], True, BLUE)]))
            if bg.get("trendEvidence"):
                mk.append(B([_run("趋势依据：", True), _run(str(bg["trendEvidence"]))]))
            if bg.get("userNeed"):
                mk.append(B([_run("用户需求：", True), _run(str(bg["userNeed"]))]))
            if mk:
                out.append(h2("01 ｜ 市场机会（Why Now）"))
                out.append(callout(mk, bg=CB_BLUE))
            # 02 商品定位
            pos_rows = [[k2, v2] for k2, v2 in (
                ("目标消费者", pos.get("targetUser")), ("核心场景", pos.get("scenario")),
                ("Slogan", pos.get("slogan")), ("价格带", pos.get("priceRange"))) if v2]
            if pos_rows:
                out.append(h2("02 ｜ 商品定位（Who & What）"))
                out.append(table([["维度", "定位"]] + pos_rows))
            # 03 产品概念
            c_rows = [[k2, v2] for k2, v2 in (("设计主题", pd.get("concept")), ("视觉语言", pd.get("designLanguage")),
                                              ("核心元素", pd.get("pattern")), ("颜色", pd.get("color")),
                                              ("材质", pd.get("material"))) if v2]
            if c_rows:
                out.append(h2("03 ｜ 产品概念（Product Concept）"))
                out.append(table([["设计项", "方案"]] + c_rows))
            # 04 商品规格（表格）
            specs = proposal.get("specification") or []
            if specs:
                out.append(h2("04 ｜ 商品规格（Product Spec）"))
                out.append(table([["模块", "解决方案"]] +
                                 [[s.get("module", ""), s.get("solution", "")] for s in specs]))
            # 05 商业模型（三价格 + 策略）
            out.append(h2("05 ｜ 商业模型（Business Model）"))
            import re as _re
            nums = [float(x) for x in _re.findall(r"\d+(?:\.\d+)?", str(pos.get("priceRange", "")))]
            retail_nums = _re.findall(r"\d+(?:\.\d+)?", str(biz.get("retailPrice", "")))
            price_line = []
            if nums:
                price_line += [_run(f" 基础款 {nums[0]:g} 元 ", False, GREY, BG_GREY)]
            if retail_nums:
                price_line += [_run(f" ⭐ 主推款 {retail_nums[0]} 元 ", True, ORANGE, BG_ORANGE)]
            if len(nums) > 1:
                price_line += [_run(f" 限定礼盒 {nums[1]:g} 元 ", False, GREY, BG_GREY)]
            if price_line:
                out.append(P(price_line))
            biz_rows = [[k2, v2] for k2, v2 in (("成本约束", biz.get("costTarget")),
                                                ("SKU 策略", biz.get("skuStrategy")),
                                                ("首发策略", biz.get("launchPlan"))) if v2]
            for r in biz_rows:
                out.append(B([_run(f"{r[0]}：", True, BLUE), _run(str(r[1]))]))
            # 06 增长路线（有序）
            growth = proposal.get("growthPath") or []
            if growth:
                out.append(h2("06 ｜ 增长路线（Growth Roadmap）"))
                for g in growth:
                    out.append(ordered([_run(f"{g.get('stage', '')}　", True, BLUE), _run(str(g.get("action", "")))]))

        # 07 落地执行细节（plan_card 补充）
        out.append(h2("07 ｜ 落地执行细节"))
        if card.get("fusion"):
            out.append(B([_run("跨品类融合：", True, BLUE), _run(str(card["fusion"]))]))
        features = _coerce(card.get("features"))
        if isinstance(features, list) and features:
            for f in features:
                out.append(B(str(f)))
        pricing = _coerce(card.get("pricing"))
        if isinstance(pricing, dict):
            out.append(B([_run("建议定价：", True, BLUE), _run(str(pricing.get("price", "")), True, ORANGE),
                          _run(f"（{pricing.get('reason', '')}）", False, GREY)]))
        check = _coerce(card.get("costCheck"))
        if isinstance(check, dict):
            margin = check.get("margin")
            margin_s = f"，毛利率 {margin:.0%}" if isinstance(margin, (int, float)) else ""
            passed = bool(check.get("passed"))
            out.append(callout([P([_run(("✅ 成本校验通过" if passed else "❌ 成本校验未通过"), True, GREEN if passed else PINK),
                                   _run(f"{margin_s}：{check.get('reason', '')}")])],
                               bg=CB_GREEN if passed else CB_RED))
        schedule = _coerce(card.get("schedule"))
        if isinstance(schedule, list) and schedule:
            for s in schedule:
                    out.append(ordered([_run(f"{s.get('time', '')}　", True, BLUE), _run(str(s.get("action", "")))]))
        validation = _coerce(card.get("validation"))
        if isinstance(validation, list) and validation:
            for v in validation:
                out.append(B(str(v)))
        return out

    # ── 对外主流程 ──────────────────────────────
    def build_for_plan(self, plan: dict[str, Any]) -> dict[str, str]:
        """生成在线文档，返回 {document_id, url, title}。"""
        card = plan.get("plan_card") or {}
        title = f"{card.get('name', '新品企划')} · AI企划报告"
        doc_id = self._create_document(title)

        img_path = self._resolve_concept_path(plan)
        blocks = self.build_blocks(plan, img_path)
        self._append_mixed(doc_id, blocks)
        self._make_readable(doc_id)
        url = f"https://feishu.cn/docx/{doc_id}"
        logger.info("在线企划报告已生成 doc=%s blocks=%s img=%s",
                    doc_id, len(blocks), bool(img_path))
        return {"document_id": doc_id, "url": url, "title": title}


def build_plan_report(plan: dict[str, Any]) -> dict[str, str] | None:
    """便捷封装：用环境变量凭证为 plan 生成在线文档；失败返回 None（fail-soft，群闭环改发降级待确认卡）。"""
    try:
        config = FeishuConfig.from_env()
        if not (config.app_id and config.app_secret):
            logger.warning("飞书凭证未配置，跳过在线报告文档生成")
            return None
        return DocReportBuilder(FeishuAuth(config)).build_for_plan(plan)
    except Exception:  # noqa: BLE001
        logger.exception("生成在线企划报告失败（不影响归档），plan_id=%s", plan.get("plan_id"))
        return None

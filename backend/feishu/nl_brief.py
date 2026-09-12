"""群聊自然语言 → 企划约束（PlanBrief）解析，含 IP 资源库强校验

职责：
- parse_brief_text：把“做一款保温杯，和三丽鸥联名”这类口语解析成结构化字段（LLM，失败规则兜底）；
- list_ip_options：IP 下拉选项，唯一来源是资源库（策展 12 + 扩充 33 去重）；
- match_ip：把口语里的 IP（含角色名/英文/别名）匹配到资源库**规范展示名**，匹配不到返回 None
  （上层据此回“资源库中无该 IP”，并让用户改从下拉选，绝不允许 LLM 自造 IP）；
- build_brief：组装 PlanBrief dict（群场景强制 mode=live，theme 由 IP+品类拼）。

注意：本模块在“尚未跑洞察”阶段也要能用，因此候选池用 merged_candidate_pool(None)
（不依赖 insightBase.ipPool）。
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from app.engine import llm
from app.planning.insight_resolver import _parse_llm_json
from app.planning.ip_library import merged_candidate_pool, normalize_ip_name

logger = logging.getLogger(__name__)

# ── IP 候选池（进程内缓存一次；资源库为静态 seed / 启动期拉取）──────────────

_CANDIDATES: list[dict[str, str]] | None = None

# 合作状态优先级：持续合作 / 战略共创排前，方便下拉里常用 IP 靠前
_STATUS_RANK = {"持续合作": 0, "战略共创": 0, "合作中": 1, "快闪限定": 2, "一次性联名": 3}

# 角色名 / 别称 → 资源库规范名（normalize 后的 key）。
# 仅映射到资源库内真实存在的 IP，不引入任何库外 IP。
_CHARACTER_ALIAS: dict[str, str] = {
    # 三丽鸥家族
    "库洛米": "三丽鸥", "酷洛米": "三丽鸥", "kuromi": "三丽鸥",
    "玉桂狗": "大耳狗", "cinnamoroll": "大耳狗",
    "美乐蒂": "三丽鸥", "melody": "三丽鸥",
    "帕恰狗": "三丽鸥", "布丁狗": "三丽鸥",
    "hello kitty": "三丽鸥", "hellokitty": "三丽鸥", "凯蒂猫": "三丽鸥",
    # 迪士尼（含皮克斯）
    "米奇": "迪士尼", "米妮": "迪士尼", "史迪奇": "迪士尼", "史迪仔": "迪士尼",
    "皮克斯": "迪士尼", "玩具总动员": "迪士尼", "胡迪": "迪士尼", "巴斯光年": "迪士尼",
    "冰雪奇缘": "迪士尼", "艾莎": "迪士尼",
    # 宝可梦
    "皮卡丘": "宝可梦", "伊布": "宝可梦", "杰尼龟": "宝可梦",
    "可达鸭": "宝可梦", "胖丁": "宝可梦", "精灵宝可梦": "宝可梦",
    # 海贼王
    "路飞": "海贼王", "索隆": "海贼王", "航海王": "海贼王",
    # 蜡笔小新
    "小新": "蜡笔小新", "野原": "蜡笔小新", "野原新之助": "蜡笔小新",
    # Chiikawa
    "吉伊": "chiikawa", "小八": "chiikawa", "乌萨奇": "chiikawa",
    "ちいかわ": "chiikawa",
    # 其它常见别称
    "机器猫": "哆啦A梦", "叮当猫": "哆啦A梦",
    "神偷奶爸": "小黄人", "格鲁": "小黄人",
}

# 模糊匹配阈值：低于此值视为资源库无此 IP
_FUZZY_THRESHOLD = 0.6


def _load_candidates() -> list[dict[str, str]]:
    """返回 [{name(展示名), key(normalize)}]，按合作状态/热度排序，进程内缓存"""
    global _CANDIDATES
    if _CANDIDATES is not None:
        return _CANDIDATES

    def _heat(item: dict) -> float:
        for k in ("ipHeat", "heat"):
            try:
                return float(str(item.get(k) or "0").replace("↑", "").strip() or 0)
            except (TypeError, ValueError):
                continue
        return 0.0

    pool = merged_candidate_pool(None)
    rows = []
    for item in pool:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        rows.append({
            "name": name,
            "key": normalize_ip_name(name),
            "status_rank": _STATUS_RANK.get(str(item.get("cooperationStatus") or item.get("status") or ""), 2),
            "heat": _heat(item),
        })
    # 去重（同名保留排序靠前的一条）
    dedup: dict[str, dict[str, str]] = {}
    for r in rows:
        if r["key"] not in dedup:
            dedup[r["key"]] = r
    rows = list(dedup.values())
    rows.sort(key=lambda r: (r["status_rank"], -r["heat"], r["name"]))
    _CANDIDATES = rows
    return rows


def list_ip_options() -> list[str]:
    """IP 下拉选项（资源库规范展示名，按合作优先级排序）"""
    return [r["name"] for r in _load_candidates()]


def match_ip(raw: str) -> str | None:
    """把口语 IP 匹配到资源库规范展示名；匹配不到返回 None。

    顺序：normalize 精确 → 角色/别称映射 → 双向子串 → difflib 模糊（阈值兜底）。
    """
    if not raw:
        return None
    candidates = _load_candidates()
    key = normalize_ip_name(str(raw))
    if not key:
        return None

    # 1) 精确
    for c in candidates:
        if c["key"] == key:
            return c["name"]

    # 2) 角色 / 别称映射到规范 key，再精确
    mapped = _CHARACTER_ALIAS.get(key)
    if mapped:
        mapped_key = normalize_ip_name(mapped)
        for c in candidates:
            if c["key"] == mapped_key:
                return c["name"]

    # 3) 双向子串（如“三丽鸥家族”“和三丽鸥”“宝可梦联名”）
    if len(key) >= 2:
        for c in candidates:
            if key in c["key"] or c["key"] in key:
                return c["name"]
        for alias_key, target in _CHARACTER_ALIAS.items():
            if alias_key in key:
                target_key = normalize_ip_name(target)
                for c in candidates:
                    if c["key"] == target_key:
                        return c["name"]

    # 4) 模糊匹配兜底
    best: tuple[float, str] | None = None
    for c in candidates:
        ratio = SequenceMatcher(None, key, c["key"]).ratio()
        if best is None or ratio > best[0]:
            best = (ratio, c["name"])
    if best and best[0] >= _FUZZY_THRESHOLD:
        return best[1]
    return None


# ── 价格带解析 ─────────────────────────────────────────────

def parse_price_range(raw) -> list[float] | None:
    """把 '39-99'/'39~99元'/'39到99'/'50左右' 解析成 [lo, hi]；无法解析返回 None"""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        try:
            return [float(raw[0]), float(raw[1])]
        except (TypeError, ValueError):
            return None
    text = str(raw or "").replace("元", "").replace("块", "").replace(" ", "")
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    try:
        if len(nums) >= 2:
            lo, hi = float(nums[0]), float(nums[1])
            if lo > hi:
                lo, hi = hi, lo
            return [lo, hi]
        if len(nums) == 1:
            center = float(nums[0])
            return [max(1.0, round(center * 0.7)), round(center * 1.3)]
    except (TypeError, ValueError):
        return None
    return None


# ── 自然语言需求解析 ───────────────────────────────────────

_PARSE_SYS = (
    "你是名创优品新品企划工作室的需求解析器。用户会用一句口语描述想做的新品，"
    "你要从中抽取结构化字段。只输出 JSON（不要输出任何其它文字、不要 markdown 代码块）：\n"
    '{"category": "产品品类（如 保温杯/香薰/双肩包，去掉修饰只留品类名，没有则空串）",'
    '"ip": "用户提到的联名 IP 原名（照抄用户说法，没有则空串）",'
    '"audience": "目标人群（没有则空串）",'
    '"price_min": 数字或 null, "price_max": 数字或 null}'
)


def parse_brief_text(text: str) -> dict:
    """解析口语需求；返回 {category, ip_raw, ip_match, audience, price_range}。

    LLM 优先，任何失败都走规则兜底；ip 一律再过资源库 match_ip（不信任 LLM 自造 IP）。
    """
    result = {"category": "", "ip_raw": "", "ip_match": None,
              "audience": "", "price_range": None}
    data = None
    try:
        raw = llm.complete(_PARSE_SYS, f"用户需求：{text}", temperature=0.0,
                           max_tokens=300, node="group_nl_parse")
        if raw:
            parsed = _parse_llm_json(raw)
            if isinstance(parsed, dict):
                data = parsed
    except Exception:  # noqa: BLE001 — 解析失败必须降级到规则，不阻塞表单流程
        logger.exception("NL 需求解析 LLM 异常，走规则兜底")
        data = None

    if isinstance(data, dict):
        result["category"] = str(data.get("category") or "").strip()
        result["ip_raw"] = str(data.get("ip") or "").strip()
        result["audience"] = str(data.get("audience") or "").strip()
        lo = data.get("price_min")
        hi = data.get("price_max")
        if lo is not None and hi is not None:
            result["price_range"] = parse_price_range([lo, hi])

    # 规则兜底：IP 直接在原文里扫（角色名/别名也能命中）
    if not result["ip_raw"]:
        result["ip_raw"] = _scan_ip_in_text(text)
    if result["ip_raw"]:
        result["ip_match"] = match_ip(result["ip_raw"])

    # 品类兜底：LLM 没抽到时，去掉常见动词/IP/联名词后的短语不稳健，宁留空交表单补
    if not result["category"]:
        result["category"] = _rule_category(text)
    return result


def _scan_ip_in_text(text: str) -> str:
    """规则扫 IP：优先命中角色/别称表，其次命中资源库展示名（子串）"""
    low = (text or "").lower()
    for alias in sorted(_CHARACTER_ALIAS, key=len, reverse=True):
        if alias in low:
            return alias
    for c in _load_candidates():
        # 用剥括号后的短名在原文里找（如资源库名“三丽鸥（Sanrio）”→“三丽鸥”）
        short = c["key"]
        if len(short) >= 2 and short in low:
            return c["name"]
    return ""


def _rule_category(text: str) -> str:
    """极简品类兜底：剥掉常见引导语和 IP 片段后，若只剩一个短名词则采用，否则空（交表单）"""
    if not text:
        return ""
    t = re.sub(r"(我们|我|想|要|需要|打算|帮忙|帮我|设计|做|一款|一个|一款|联名|和.*?IP|与.*?联名)",
               "", text)
    t = t.strip(" ，。,.!！?？、的")
    # 剥掉命中的 IP 名，避免品类里混入 IP
    for c in _load_candidates():
        t = t.replace(c["key"], "")
    t = t.strip(" ，。,.!！?？、的")
    # 只在结果很短（像品类名）时采用
    if 0 < len(t) <= 8:
        return t
    return ""


# ── 组装 PlanBrief ─────────────────────────────────────────

def build_brief(category: str, ip_display: str, audience: str = "",
                price_range: list[float] | None = None) -> dict:
    """组装可直接传给 pipeline.create_plan 的 brief（snake_case，群场景强制 live）"""
    category = (category or "").strip()
    ip_display = (ip_display or "").strip()
    brief = {
        "theme": f"{ip_display} × {category} 联名企划" if ip_display else f"{category} 新品企划",
        "category": category,
        "market": "中国大陆",
        "audience": (audience or "").strip(),
        "price_range": price_range or [39, 99],
        "cost_limit": 25,
        "ip_strategy": [ip_display] if ip_display else [],
        "launch_window": "",
        "goals": [],
        "mode": "live",
    }
    return brief

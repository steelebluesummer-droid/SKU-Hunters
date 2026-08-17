"""Stage 12A · 洞察二次分析缓存（跨任务 / 跨重启）

缓存键 = 品类 + 明细快照 + 汇总快照 + 竞品快照 + LLM 模型 + prompt 版本。
安全规则：
- 任一快照缺失 → 返回 None（不命中，安全重算），避免跨快照误复用；
- 不同品类 / 不同快照 / 不同模型 / 不同 prompt 版本 → 不同键，不会误复用；
- 缓存命中后，调用方仍须做 schema 校验（不因命中跳过校验）；
- 缓存损坏时安全重算（load 失败返回空）。
"""
import hashlib
import json
import logging
import threading
from pathlib import Path

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
_CACHE_FILE = _CACHE_DIR / "insight_analysis_cache.json"
_lock = threading.Lock()
_LOG = logging.getLogger("insights.cache")

# prompt 版本：改动各 Agent prompt 时递增，强制旧缓存失效
PROMPT_VERSION = "1.0"

# 缓存 payload 结构版本：改动缓存结构（元数据/字段）时递增，旧结构视为 miss
CACHE_SCHEMA_VERSION = "2"


def _model() -> str:
    """当前 LLM 模型名（模型变化 → 缓存键变化，不误复用旧模型结果）"""
    try:
        from app.engine.llm import get_llm_config
        cfg = get_llm_config()
        return (cfg or {}).get("model", "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def cache_key(category, detail_snap, summary_snap, competitor_snap):
    """构造缓存键；任一快照缺失返回 None（不命中，安全重算）"""
    if not category or not detail_snap or not summary_snap or not competitor_snap:
        return None
    raw = "|".join([
        str(category),
        str(detail_snap),
        str(summary_snap),
        str(competitor_snap),
        _model(),
        PROMPT_VERSION,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — 缓存损坏视为空，安全重算
        return {}


def get(key):
    """命中返回缓存增强数据；未命中 / 损坏 / 版本过期 / complete=False → None（重算）"""
    if not key:
        return None
    entry = _load().get(key)
    if not entry:
        return None
    if entry.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
        return None  # 缓存结构版本过期 → miss
    if not entry.get("complete"):
        return None  # 未完整增强结果 → miss
    return entry.get("data")


def put(
    key,
    value,
    complete: bool = True,
    node_status: dict | None = None,
    caveats: list | None = None,
) -> None:
    """写缓存；键为 None 不写。

    仅当 complete=True 时才可被 get() 命中（未完整增强结果写 complete=False，视为 miss）。
    """
    if not key:
        return
    entry = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "created_at": _now_iso(),
        "complete": bool(complete),
        "node_status": dict(node_status or {}),
        "caveats": list(caveats or []),
        "data": value,
    }
    with _lock:
        data = _load()
        data[key] = entry
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_name(f".{_CACHE_FILE.name}.{threading.get_ident()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            tmp.replace(_CACHE_FILE)
        except Exception:  # noqa: BLE001 — 写缓存失败不影响主流程
            _LOG.warning("洞察缓存写入失败（忽略）")


def _test_reset_cache_dir(dirpath) -> None:
    """测试专用：重指缓存目录"""
    global _CACHE_DIR, _CACHE_FILE
    _CACHE_DIR = Path(dirpath)
    _CACHE_FILE = _CACHE_DIR / "insight_analysis_cache.json"

"""飞书真实数据本地快照缓存（Stage 12A·后续 二阶段）

目标：避免每次洞察都通过代理分页读取 base_records / base_summaries / base_competitors。
缓存的是「飞书真实数据快照」，source 恒为 feishu，绝不标记为 fixture/mock。

- 缓存键 = sha256(base_id | table_id | category | table_type)
  base_id 由 FEISHU_BASE_APP_TOKEN 的 sha256 前缀派生（不落原始 token）。
- 快照内容：normalized records + snapshot_id + fetched_at + source + record_count + caveats。
- 原子写入 + 线程锁，避免并发破坏缓存文件；损坏时安全忽略并重新读取飞书。
- 不跨品类 / 不跨表 / 不跨 snapshot 复用（get 可校验 snapshot_id）。
- TTL：FEISHU_SNAPSHOT_TTL_SECONDS（默认 3600）；过期默认视为 miss 重新访问飞书。
- 过期缓存仅在飞书不可用且明确允许 stale 时返回，且必须带 stale 标记（不伪装实时）。
- 提供可审计 CLI：python -m app.data.feishu_snapshot_cache --help
  支持 --refresh / --category / --dry-run；不打印 token / secret / 完整原始记录。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("feishu.snapshot")

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshot_cache"  # backend/data/snapshot_cache/
_CACHE_FILE = _CACHE_DIR / "feishu_snapshot_cache.json"
_lock = threading.Lock()

_DEFAULT_TTL = 3600

# 数据表类型常量
TYPE_RECORDS = "records"
TYPE_SUMMARY = "summary"
TYPE_COMPETITORS = "competitors"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return time.time()


def _parse_iso(value: str) -> float:
    """解析 ISO 时间戳为 epoch 秒；解析失败返回 0（视为过期）"""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


def ttl_seconds() -> int:
    """TTL（秒）；FEISHU_SNAPSHOT_TTL_SECONDS 非法时用安全默认并记录配置错误"""
    raw = os.getenv("FEISHU_SNAPSHOT_TTL_SECONDS", str(_DEFAULT_TTL))
    try:
        v = int(raw)
        if v < 0:
            raise ValueError("负 TTL")
        return v
    except (ValueError, TypeError):
        _LOG.warning("FEISHU_SNAPSHOT_TTL_SECONDS 非法（%r），使用默认 %s 秒", raw, _DEFAULT_TTL)
        return _DEFAULT_TTL


def base_id() -> str:
    """由 FEISHU_BASE_APP_TOKEN 派生的 Base 标识（不暴露原始 token）"""
    token = os.getenv("FEISHU_BASE_APP_TOKEN", "")
    if not token:
        return "unknown_base"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def cache_key(base: str, table_id: str, category: str, table_type: str) -> str:
    """构造缓存键；category 归一化小写去空白（跨品类/表/类型隔离）"""
    raw = "|".join([str(base), str(table_id), (category or "").strip().lower(), str(table_type)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_file() -> Path:
    return _CACHE_FILE


def _load() -> dict[str, Any]:
    """读取缓存文件；损坏 → 空 dict（安全：调用方重新读取飞书）"""
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — 缓存损坏视为空，安全重取
        return {}


def _entry_expired(entry: dict[str, Any]) -> bool:
    fetched = _parse_iso(entry.get("fetched_at", ""))
    if fetched <= 0:
        return True
    return (_now_ts() - fetched) > ttl_seconds()


def get(base: str, table_id: str, category: str, table_type: str, snapshot_id: str | None = None) -> dict[str, Any] | None:
    """返回有效缓存快照；未命中 / 快照不匹配 / 过期 → None（调用方重新访问飞书）"""
    key = cache_key(base, table_id, category, table_type)
    with _lock:
        data = _load()
        entry = data.get(key)
        if not entry:
            return None
        if snapshot_id is not None and entry.get("snapshot_id") != snapshot_id:
            return None  # 不同 snapshot 不命中
        if _entry_expired(entry):
            return None  # 过期 → miss（重新访问飞书）
        return dict(entry)


def get_any(base: str, table_id: str, category: str, table_type: str) -> dict[str, Any] | None:
    """返回任意缓存快照（含过期），供「飞书不可用时明确 stale 降级」；无缓存 → None"""
    key = cache_key(base, table_id, category, table_type)
    with _lock:
        data = _load()
        entry = data.get(key)
        return dict(entry) if entry else None


def put(
    base: str,
    table_id: str,
    category: str,
    table_type: str,
    snapshot_id: str,
    records: list[dict[str, Any]],
    record_count: int,
    caveats: list[str] | None = None,
    stale: bool = False,
) -> str:
    """写入缓存快照（原子写 + 线程锁）；返回写入的缓存键"""
    key = cache_key(base, table_id, category, table_type)
    entry = {
        "key": key,
        "base_id": base,
        "table_id": table_id,
        "category": category.strip().lower(),
        "table_type": table_type,
        "snapshot_id": snapshot_id or "",
        "records": records,
        "fetched_at": _now_iso(),
        "source": "feishu",
        "record_count": int(record_count or len(records)),
        "caveats": list(caveats or []),
        "stale": bool(stale),
    }
    with _lock:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = _load()
        data[key] = entry
        tmp = _CACHE_FILE.with_name(f".feishu_snapshot.{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            tmp.replace(_CACHE_FILE)
        except Exception as e:  # noqa: BLE001 — 写缓存失败不影响主流程
            _LOG.warning("飞书快照缓存写入失败（忽略）: %s", e)
    return key


def invalidate(base: str, table_id: str, category: str, table_type: str) -> bool:
    """删除指定缓存项；返回是否存在被删除"""
    key = cache_key(base, table_id, category, table_type)
    with _lock:
        data = _load()
        if key not in data:
            return False
        del data[key]
        tmp = _CACHE_FILE.with_name(f".feishu_snapshot.{uuid.uuid4().hex}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(_CACHE_FILE)
        return True


def _dump_stats() -> list[dict[str, Any]]:
    """审计统计（不含 token / 完整原始记录）"""
    with _lock:
        data = _load()
    out = []
    for key, entry in data.items():
        out.append({
            "key": key,
            "category": entry.get("category"),
            "table_type": entry.get("table_type"),
            "snapshot_id": entry.get("snapshot_id"),
            "source": entry.get("source"),
            "record_count": entry.get("record_count"),
            "fetched_at": entry.get("fetched_at"),
            "expired": _entry_expired(entry),
        })
    return out


# ── 可审计 CLI ──────────────────────────────────────────

def _run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.data.feishu_snapshot_cache",
        description="飞书真实数据本地快照缓存审计/刷新工具（不打印 token/secret/完整记录）",
    )
    parser.add_argument("--refresh", action="store_true", help="刷新（清空）快照缓存，下次读取重新访问飞书")
    parser.add_argument("--category", type=str, default=None, help="仅查看/刷新指定品类的缓存")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不实际写入/删除")
    args = parser.parse_args(argv)

    if args.refresh:
        _run_refresh(args)
    else:
        _run_stats(args)
    return 0


def _run_stats(args) -> None:
    stats = _dump_stats()
    if args.category:
        cat = args.category.strip().lower()
        stats = [s for s in stats if s.get("category") == cat]
    if not stats:
        print("无快照缓存项" + (f"（品类 {args.category}）" if args.category else ""))
        return
    print(f"共 {len(stats)} 项飞书快照缓存：")
    for s in stats:
        print(
            f"  [{s['table_type']}] 品类={s['category']} snapshot={s['snapshot_id']} "
            f"records={s['record_count']} fetched={s['fetched_at']} "
            f"expired={'是' if s['expired'] else '否'} source={s['source']}"
        )


def _run_refresh(args) -> None:
    stats = _dump_stats()
    if args.category:
        cat = args.category.strip().lower()
        targets = [s for s in stats if s.get("category") == cat]
    else:
        targets = stats
    if not targets:
        print("无可刷新项")
        return
    if args.dry_run:
        print(f"[dry-run] 将删除 {len(targets)} 项缓存（品类={args.category or '全部'}），不实际执行")
        for s in targets:
            print(f"  - [{s['table_type']}] 品类={s['category']} snapshot={s['snapshot_id']}")
        return
    for s in targets:
        _delete_by_key(s["key"])
    print(f"已刷新（删除）{len(targets)} 项缓存")


def _delete_by_key(key: str) -> bool:
    with _lock:
        data = _load()
        if key not in data:
            return False
        del data[key]
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_name(f".feishu_snapshot.{uuid.uuid4().hex}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(_CACHE_FILE)
        return True


if __name__ == "__main__":
    sys.exit(_run_cli())

"""任务存储层（repository）：内存 + JSON 文件持久化

职责边界：只负责「任务」的读写与落盘（原子写入、并发安全），
不含业务编排（洞察/机会/企划卡的业务流程在 service.py）。

键名工具（camelCase ↔ snake_case 契约转换）也收敛在此，
供 opportunity_engine / plan_card_builder / service 复用。
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.planning import PlanBrief, PlanSummary

# ── 键名工具（前后端契约转换）────────────────────────────

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 任务存储（内存 + 原子文件持久化，并发安全）────────────

_PLANS: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

_STATE_DIR = Path(__file__).resolve().parents[2] / "data" / "state"  # backend/data/state/
_STATE_FILE = _STATE_DIR / "plans_state.json"
# 迁移前旧位置（backend/data/plans_state.json），仅供向后兼容读取
_LEGACY_STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "plans_state.json"


def _save_state() -> None:
    """将全部任务状态原子落盘（先写临时文件再 rename，避免写一半损坏）"""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {}
    with _lock:
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
    tmp = _STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(_STATE_FILE)  # 原子替换（同目录 rename）


def _load_state() -> dict[str, dict[str, Any]]:
    """从 JSON 文件恢复任务状态（不存在或损坏则返回空）

    新路径（data/state/）优先，旧路径（data/plans_state.json）向后兼容读取。
    """
    path = _STATE_FILE
    if not path.is_file() and _LEGACY_STATE_FILE.is_file():
        path = _LEGACY_STATE_FILE
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ── 任务 CRUD ────────────────────────────────────────────

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
    with _lock:
        _PLANS[plan_id] = plan
    return plan


def get_plan(plan_id: str) -> dict[str, Any] | None:
    return _PLANS.get(plan_id)


def list_plans() -> list[dict[str, Any]]:
    with _lock:
        plans = sorted(_PLANS.values(), key=lambda p: p["created_at"], reverse=True)
    summaries = [
        PlanSummary(
            plan_id=p["plan_id"],
            theme=p["brief"].get("theme", ""),
            category=p["brief"].get("category", ""),
            audience=p["brief"].get("audience", ""),
            status=p["status"],
            created_at=p["created_at"],
        )
        for p in plans
    ]
    return [s.model_dump() for s in summaries]

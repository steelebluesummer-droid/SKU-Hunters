"""Connector 白名单网关 — AGENT_DATA_ACCESS 的运行时强制

Agent 只能通过本网关获取白名单内的 connector；白名单外或未实现的 connector fail-closed。
这是「信息隔离」的代码级约束（而非仅 prompt 声明），graph.py 的 Agent 创建路径经此注入。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.config import AGENT_DATA_ACCESS


class DataAccessViolation(Exception):
    """尝试访问白名单外或未实现的数据源"""


def _google_trends():
    from app.data.google_trends import GoogleTrendsConnector
    return GoogleTrendsConnector()


def _bilibili():
    from app.data.bilibili_hot import BilibiliConnector
    return BilibiliConnector()


def _taobao():
    from app.data.taobao_suggest import TaobaoSuggestConnector
    return TaobaoSuggestConnector()


def _weibo():
    from app.data.weibo_hot import WeiboHotConnector
    return WeiboHotConnector()


def _baidu():
    from app.data.baidu_hot import BaiduHotConnector
    return BaiduHotConnector()


# 只注册仓库中真实存在的 connector。AGENT_DATA_ACCESS 中声明但未实现的数据源
# （social_snapshot / ip_database / artifact_store 等）不在此注册表 → fail-closed。
CONNECTOR_REGISTRY: dict[str, Callable[[], Any]] = {
    "google_trends": _google_trends,
    "bilibili_ranking": _bilibili,
    "taobao_suggest": _taobao,
    "weibo_hot": _weibo,
    "baidu_hot": _baidu,
}


def resolve_connector(agent_key: str, connector_name: str) -> Any:
    """解析单个 connector：白名单外或未实现 → DataAccessViolation（fail-closed）"""
    allowed = set(AGENT_DATA_ACCESS.get(agent_key, []))
    if connector_name not in allowed:
        raise DataAccessViolation(
            f"数据源 '{connector_name}' 不在 '{agent_key}' 的信息访问白名单内"
        )
    factory = CONNECTOR_REGISTRY.get(connector_name)
    if factory is None:
        raise DataAccessViolation(
            f"数据源 '{connector_name}' 已声明但未实现（fail-closed，拒绝访问）"
        )
    return factory()


def resolve_connectors(agent_key: str) -> dict[str, Any]:
    """返回 agent 白名单内、且已实现的 connector 实例映射（跳过未实现项）"""
    resolved: dict[str, Any] = {}
    for name in AGENT_DATA_ACCESS.get(agent_key, []):
        factory = CONNECTOR_REGISTRY.get(name)
        if factory is not None:
            resolved[name] = factory()
    return resolved

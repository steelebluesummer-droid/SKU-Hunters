"""调研需求池写入（research pool）。

群闭环识别到「全新品类」（飞书 Base 与本地采集都无真实数据）后，由用户在群里点
「发起调研」，把该品类登记到调研需求表，状态=待调研，供飞书侧豆包工作伙伴订阅读取、
完成调研后把结果填回数据源 Base。本模块只负责「去重 + 登记一条」，不负责调研本身。

表结构（用户在飞书侧建好，应用被加为可编辑协作者）：
  品类名  文本(type=1)  状态  单选(type=3，选项：待调研/调研中/已完成)  完成时间 日期(type=5，留空)
只写「品类名 + 状态=待调研」，完成时间留空；app_token/table_id 支持 env 覆盖。
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

from feishu.auth import FeishuAuth
from feishu.config import FeishuConfig

logger = logging.getLogger(__name__)

_REQ_TIMEOUT = 15
# 用户新建的「调研需求池」Base / 「调研需求」表；仅从环境变量读取，避免配置进入代码仓库。
_OPEN_STATUS = "待调研"
_ACTIVE_STATES = {"待调研", "调研中"}  # 处于这两态视为已在队列，不重复登记
_FIELD_CATEGORY = "品类名"
_FIELD_STATUS = "状态"


class ResearchPoolError(RuntimeError):
    """调研需求池读取/写入失败（权限、接口、字段不符等）。"""


def _plain_text(value: Any) -> str:
    """多维表读出来的文本可能是字符串或富文本片段数组，统一拍平成纯文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for seg in value:
            if isinstance(seg, dict):
                parts.append(str(seg.get("text") or seg.get("name") or ""))
            else:
                parts.append(str(seg))
        return "".join(parts).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    return str(value).strip()


class ResearchPoolClient:
    def __init__(self, auth: FeishuAuth, app_token: str, table_id: str):
        self.auth = auth
        self.base = (
            "https://open.feishu.cn/open-apis/bitable/v1/apps"
            f"/{app_token}/tables/{table_id}"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def find_active(self, category: str) -> dict[str, Any] | None:
        """找到该品类处于 待调研/调研中 的记录则返回（去重）；无则 None。"""
        target = (category or "").strip()
        page_token = ""
        for _ in range(10):  # 需求池很小，分页兜底即可
            url = f"{self.base}/records?page_size=100"
            if page_token:
                url += f"&page_token={page_token}"
            resp = requests.get(url, headers=self._headers(), timeout=_REQ_TIMEOUT)
            data = resp.json()
            if data.get("code") != 0:
                raise ResearchPoolError(f"读取调研需求池失败: code={data.get('code')} msg={data.get('msg')}")
            block = data.get("data", {})
            for rec in block.get("items", []) or []:
                fields = rec.get("fields", {})
                if _plain_text(fields.get(_FIELD_CATEGORY)) == target and \
                        _plain_text(fields.get(_FIELD_STATUS)) in _ACTIVE_STATES:
                    return rec
            if not block.get("has_more"):
                break
            page_token = block.get("page_token", "")
            if not page_token:
                break
        return None

    def create_request(self, category: str) -> dict[str, Any]:
        """新增一条调研需求：品类名 + 状态=待调研（完成时间留空）。"""
        payload = {"fields": {_FIELD_CATEGORY: category.strip(), _FIELD_STATUS: _OPEN_STATUS}}
        resp = requests.post(
            f"{self.base}/records", headers=self._headers(),
            json=payload, timeout=_REQ_TIMEOUT,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise ResearchPoolError(
                f"写入调研需求池失败: code={data.get('code')} msg={data.get('msg')} payload={payload}"
            )
        return data.get("data", {}).get("record", {})


def submit_research_request(category: str) -> tuple[bool, str]:
    """登记一条新品类调研需求（带去重）。

    Returns:
        (created, record_id)：created=True 表示新建，False 表示已有在途记录（未重复写）。
    Raises:
        ResearchPoolError：凭证缺失或读写接口失败。
    """
    category = (category or "").strip()
    if not category:
        raise ResearchPoolError("品类名为空，无法登记调研需求")

    app_token = os.getenv("FEISHU_RESEARCH_BASE_APP_TOKEN", "").strip()
    table_id = os.getenv("FEISHU_RESEARCH_TABLE_ID", "").strip()
    if not app_token or not table_id:
        raise ResearchPoolError(
            "调研需求池未配置：请设置 FEISHU_RESEARCH_BASE_APP_TOKEN 和 FEISHU_RESEARCH_TABLE_ID"
        )

    config = FeishuConfig.from_env()
    if not (config.app_id and config.app_secret):
        raise ResearchPoolError("飞书 app_id/app_secret 未配置")

    client = ResearchPoolClient(FeishuAuth(config), app_token, table_id)
    existing = client.find_active(category)
    if existing is not None:
        logger.info("品类「%s」已在调研需求队列（record=%s），不重复登记", category, existing.get("record_id"))
        return False, existing.get("record_id", "")
    record = client.create_request(category)
    logger.info("品类「%s」已登记调研需求，record=%s", category, record.get("record_id"))
    return True, record.get("record_id", "")

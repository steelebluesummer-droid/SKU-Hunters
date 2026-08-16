"""
飞书消息发送
"""
from typing import Any

import requests

from .auth import FeishuAuth

# 飞书 API 正常响应 <2s；10s 无响应视为对端挂死，防止请求方被拖死
_REQ_TIMEOUT = 10


class FeishuBot:
    """飞书机器人消息发送器"""

    def __init__(self, auth: FeishuAuth):
        self.auth = auth
        self.base_url = "https://open.feishu.cn/open-apis/im/v1/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        """发送纯文本消息"""
        resp = requests.post(
            f"{self.base_url}?receive_id_type=chat_id",
            headers=self._headers(),
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": '{"text": "' + text + '"}',
            },
            timeout=_REQ_TIMEOUT,
        )
        return resp.json()

    def send_card(self, chat_id: str, card: dict[str, Any]) -> dict[str, Any]:
        """发送交互卡片消息"""
        import json
        resp = requests.post(
            f"{self.base_url}?receive_id_type=chat_id",
            headers=self._headers(),
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
            timeout=_REQ_TIMEOUT,
        )
        return resp.json()

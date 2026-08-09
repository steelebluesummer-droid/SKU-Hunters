"""
飞书消息发送
"""
import requests
from typing import Dict, Any, List

from .auth import FeishuAuth
from .cards import (
    build_committee_card,
    build_start_card,
    build_summary_card,
)


class FeishuBot:
    """飞书机器人消息发送器"""

    def __init__(self, auth: FeishuAuth):
        self.auth = auth
        self.base_url = "https://open.feishu.cn/open-apis/im/v1/messages"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def send_text(self, chat_id: str, text: str) -> Dict[str, Any]:
        """发送纯文本消息"""
        resp = requests.post(
            f"{self.base_url}?receive_id_type=chat_id",
            headers=self._headers(),
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": '{"text": "' + text + '"}',
            },
        )
        return resp.json()

    def send_card(self, chat_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
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
        )
        return resp.json()

    # ===== 便捷方法：各委员发言 =====

    def send_committee_report(
        self,
        chat_id: str,
        role: str,
        content: str,
        evidence: List[str] = None,
        score: float = None,
    ) -> Dict[str, Any]:
        """发送委员发言卡片"""
        card = build_committee_card(
            role=role,
            content=content,
            evidence=evidence,
            score=score,
        )
        return self.send_card(chat_id, card)

    def send_review_start(self, chat_id: str, topic: str) -> Dict[str, Any]:
        """发送评审开始卡片"""
        card = build_start_card(topic)
        return self.send_card(chat_id, card)

    def send_review_summary(
        self,
        chat_id: str,
        topic: str,
        final_score: float,
        recommendation: str,
    ) -> Dict[str, Any]:
        """发送评审总结卡片"""
        card = build_summary_card(topic, final_score, recommendation)
        return self.send_card(chat_id, card)

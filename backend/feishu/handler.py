"""
消息处理器 - 接收飞书消息，调度 Agent，发送结果
目前只接了趋势官，其他 Agent 后续补充
"""
import re
import asyncio
from typing import Dict, Any

from .bot import FeishuBot


class MessageHandler:
    """飞书消息处理器"""

    def __init__(self, bot: FeishuBot):
        self.bot = bot

    async def handle_message(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理飞书消息事件

        Args:
            event: 飞书回调的事件数据
        """
        # 解析消息
        msg = event.get("message", {})
        chat_id = msg.get("chat_id", "")
        msg_type = msg.get("message_type", "")
        content = msg.get("content", "{}")

        # 只处理文本消息
        if msg_type != "text":
            return {"code": 0, "msg": "ignored"}

        import json
        try:
            content_data = json.loads(content)
            text = content_data.get("text", "")
        except Exception:
            text = content

        # 去掉 @机器人 的部分
        text = re.sub(r"@_user_1\s*", "", text).strip()

        # 判断指令
        if text.startswith("评审") or text.startswith("分析"):
            # 提取主题
            topic = re.sub(r"^(评审|分析)(一下|下)?", "", text).strip()
            if not topic:
                topic = "解压玩具"  # 默认主题
            asyncio.create_task(self._run_review(chat_id, topic))
            return {"code": 0, "msg": "ok"}

        elif text == "帮助" or text == "help":
            self.bot.send_text(
                chat_id,
                "SKU Hunters · AI Product Committee\n\n"
                "使用方式：\n"
                "• @我 说「评审 XXX」 - 启动一轮商品评审\n"
                "• @我 说「帮助」 - 查看帮助\n\n"
                "七位委员：趋势官、用户官、IP官、创意官、商业官、全球化官、学习官",
            )
            return {"code": 0, "msg": "ok"}

        return {"code": 0, "msg": "ignored"}

    async def handle_card_action(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理卡片按钮点击事件
        """
        action = event.get("action", {})
        value = action.get("value", {})
        action_type = value.get("action", "")
        topic = value.get("topic", "")

        # 获取用户信息
        user = event.get("user", {})
        user_name = user.get("name", "有人")

        chat_id = event.get("open_chat_id", "")

        if action_type == "approve":
            self.bot.send_text(
                chat_id,
                f"✅ {user_name} 已通过「{topic}」的立项建议\n\n"
                f"学习官将持续追踪上市表现，定期复盘。",
            )
        elif action_type == "reject":
            self.bot.send_text(
                chat_id,
                f"❌ {user_name} 否决了「{topic}」的立项建议\n\n"
                f"请在下方留言否决理由，学习官将记录并反哺全员。",
            )

        return {"code": 0, "msg": "ok"}

    async def _run_review(self, chat_id: str, topic: str):
        """
        运行一轮完整评审
        目前只实现了趋势官，其他 Agent 后续补充
        """
        # 1. 发送评审开始卡片
        self.bot.send_review_start(chat_id, topic)

        # 模拟延迟，营造讨论感
        await asyncio.sleep(2)

        # 2. 第一幕：趋势官（已实现，对接 app.agents.trend_agent）
        try:
            from app.agents.trend_agent import TrendAgent
            agent = TrendAgent()
            result = await agent.run({
                "keywords": [topic],
                "category": topic,
                "geo": "",
            })

            # FeatureMatrix → 卡片内容适配
            trends = result.get("trends", [])
            if trends:
                lines = [result.get("summary", "")]
                for t in trends[:3]:
                    lines.append(
                        f"· {t['keyword']}：热度 {t['heat_index']}（{t['lifecycle']}）"
                    )
                content = "\n".join(lines)
            else:
                content = result.get("summary", "趋势分析完成")

            evidence = [
                f"{e['title']}：{e['snippet'][:60]}"
                for e in result.get("evidence_refs", [])[:3]
            ]

            self.bot.send_committee_report(
                chat_id=chat_id,
                role="trend",
                content=content,
                evidence=evidence,
            )
        except Exception as e:
            # 任何失败（网络/Key/数据源）都降级为占位，不阻塞会议
            self.bot.send_committee_report(
                chat_id=chat_id,
                role="trend",
                content=f"正在分析「{topic}」的市场趋势数据...\n\n"
                       f"（数据源暂不可用：{str(e)[:50]}，已降级为占位内容）",
                evidence=["淘宝搜索数据 - 待接入", "抖音热榜 - 待接入", "小红书趋势 - 待接入"],
            )

        await asyncio.sleep(2)

        # 3. 第一幕：用户官（占位，待实现）
        self.bot.send_committee_report(
            chat_id=chat_id,
            role="user",
            content=f"正在挖掘「{topic}」相关的用户需求与痛点...\n\n"
                   f"（用户官 Agent 开发中，此处为占位内容）",
            evidence=["B站评论 - 待接入", "知乎问答 - 待接入", "小红书笔记 - 待接入"],
        )

        await asyncio.sleep(2)

        # 4. 第一幕：IP官（占位，待实现）
        self.bot.send_committee_report(
            chat_id=chat_id,
            role="ip",
            content=f"正在评估「{topic}」相关 IP 的热度与窗口期...\n\n"
                   f"（IP官 Agent 开发中，此处为占位内容）",
            evidence=["IP授权库 - 待接入", "社交媒体热度 - 待接入"],
        )

        await asyncio.sleep(3)

        # 5. 第二幕：创意官（占位，待实现）
        self.bot.send_committee_report(
            chat_id=chat_id,
            role="creative",
            content=f"综合三方输入，正在生成「{topic}」的商品创意方案...\n\n"
                   f"（创意官 Agent 开发中，此处为占位内容）",
        )

        await asyncio.sleep(2)

        # 6. 第三幕：商业官 + 全球化官（占位，待实现）
        self.bot.send_committee_report(
            chat_id=chat_id,
            role="business",
            content=f"正在进行「{topic}」的五维机会值评估...\n\n"
                   f"（商业官 Agent 开发中，此处为占位内容）",
            score=72.5,  # 示例分数
        )

        await asyncio.sleep(2)

        self.bot.send_committee_report(
            chat_id=chat_id,
            role="global",
            content=f"正在制定「{topic}」的全球上市批次与定价策略...\n\n"
                   f"（全球化官 Agent 开发中，此处为占位内容）",
        )

        await asyncio.sleep(2)

        # 7. Decision Engine 总结（占位）
        self.bot.send_review_summary(
            chat_id=chat_id,
            topic=topic,
            final_score=72.5,
            recommendation=(
                f"基于七位委员的综合分析，「{topic}」方向具有一定市场机会，"
                f"建议进入打样阶段，优先测试东南亚市场。\n\n"
                f"（Decision Engine 开发中，此处为示例结论）"
            ),
        )

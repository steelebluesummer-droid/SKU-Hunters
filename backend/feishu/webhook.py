"""
飞书 Webhook 路由 - 接收飞书消息回调和卡片事件
集成到你的 FastAPI 应用中
"""

from fastapi import APIRouter, HTTPException, Request

from .auth import FeishuAuth
from .bot import FeishuBot
from .config import FeishuConfig
from .handler import MessageHandler


def create_feishu_router(config: FeishuConfig) -> APIRouter:
    """
    创建飞书 Webhook 路由

    使用方式：
        from feishu import create_feishu_router, FeishuConfig
        config = FeishuConfig.from_env()
        app.include_router(create_feishu_router(config), prefix="/feishu")
    """
    router = APIRouter()

    auth = FeishuAuth(config)
    bot = FeishuBot(auth)
    handler = MessageHandler(bot)

    @router.post("/events")
    async def feishu_events(request: Request):
        """
        飞书事件回调入口
        飞书开放平台配置的回调地址填这个：https://your-domain.com/api/v1/feishu/events
        """
        body = await request.json()

        # 1. URL 验证（飞书第一次配置回调时会发验证请求）
        if "challenge" in body:
            return {"challenge": body["challenge"]}

        # 2. 验证 token（可选，但建议开启）
        if config.verification_token:
            token = body.get("token", "")
            if token != config.verification_token:
                raise HTTPException(status_code=403, detail="Invalid token")

        # 3. 处理事件
        header = body.get("header", {})
        event_type = header.get("event_type", "")
        event = body.get("event", {})

        if event_type == "im.message.receive_v1":
            # 接收消息事件
            await handler.handle_message(event)
        elif event_type == "card.action.trigger":
            # 卡片按钮点击事件
            await handler.handle_card_action(event)

        return {"code": 0, "msg": "ok"}

    @router.get("/health")
    async def health():
        """健康检查"""
        return {"status": "ok", "service": "feishu-bot"}

    return router

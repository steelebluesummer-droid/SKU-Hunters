"""SKU Hunters — AI Product Committee 后端服务"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 飞书机器人模块（backend/feishu/，需从 backend/ 目录启动以保证可导入）
from feishu import FeishuConfig
from feishu.webhook import create_feishu_router

app = FastAPI(
    title="SKU Hunters — AI Product Committee",
    description="名创优品 AI 商品开发智能决策引擎",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 飞书回调路由：POST /api/v1/feishu/events
feishu_config = FeishuConfig.from_env()
app.include_router(
    create_feishu_router(feishu_config),
    prefix="/api/v1/feishu",
    tags=["feishu"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI Product Committee"}


@app.get("/")
async def root():
    return {
        "name": "SKU Hunters",
        "version": "0.1.0",
        "agents": [
            "trend",
            "consumer_insight",
            "ip_strategy",
            "product_ideation",
            "business_evaluation",
            "go_to_market",
            "learning",
        ],
    }
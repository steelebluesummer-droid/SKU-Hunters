"""SKU Hunters — AI Product Committee 后端服务"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 飞书机器人模块（backend/feishu/，需从 backend/ 目录启动以保证可导入）
from feishu import FeishuConfig
from feishu.webhook import create_feishu_router

from app.api.routes import router as committee_router

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

# 评审 API：POST/GET /api/v1/reviews...
app.include_router(committee_router)

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


# 生产模式：前端 build 产物由后端托管（npm run build 后一条 uvicorn 命令起全站）。
# 注意：mount("/") 会遮蔽下面的 root() 发现页——dist 存在时 "/" 即前端首页，符合预期；
# dist 不存在（纯 API 模式）时 root() 照常工作。mount 必须在所有 API 路由之后注册。
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")


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
"""SKU Hunters — AI 新品企划工作室 后端服务"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 启动即加载 backend/.env（LLM Key、即梦 AK/SK、飞书配置）——必须在 app.* 导入前
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.api.planning import router as planning_router
from app.api.routes import router as committee_router
from app.xhs.api import router as xhs_router

# 飞书机器人模块（backend/feishu/，需从 backend/ 目录启动以保证可导入）
from feishu import FeishuConfig
from feishu.webhook import create_feishu_router

from app.api.planning import router as planning_router
from app.api.routes import router as committee_router

app = FastAPI(
    title="SKU Hunters — AI 新品企划工作室",
    description="名创优品 AI 驱动的产品开发智能决策引擎",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 企划工作室 API：POST/GET /api/v1/plans...（v2.0 主链路）
app.include_router(planning_router)

# 评审 API（旧评审委员会链路，复盘归档阶段复用）：POST/GET /api/v1/reviews...
app.include_router(committee_router)

# 小红书公开数据接入（第一阶段：本地导入 + 统计）：/api/v1/xhs...
app.include_router(xhs_router)

# 飞书回调路由：POST /api/v1/feishu/events
feishu_config = FeishuConfig.from_env()
app.include_router(
    create_feishu_router(feishu_config),
    prefix="/api/v1/feishu",
    tags=["feishu"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI 新品企划工作室"}


# 生产模式：前端 build 产物由后端托管（npm run build 后一条 uvicorn 命令起全站）。
# 注意：mount("/") 会遮蔽下面的 root() 发现页——dist 存在时 "/" 即前端首页，符合预期；
# dist 不存在（纯 API 模式）时 root() 照常工作。mount 必须在所有 API 路由之后注册。
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")


@app.get("/")
async def root():
    return {
        "name": "SKU Hunters · AI 新品企划工作室",
        "version": "2.0.0",
        "pipeline": [
            "企划约束",
            "五看洞察（趋势/用户/竞品 + 名创内部 + 流行元素板）",
            "机会生成",
            "创意设计",
            "商品策略（成本校验回环）",
            "新品企划卡",
        ],
    }

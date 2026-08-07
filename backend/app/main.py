"""SKU Hunters — AI Product Committee 后端服务"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
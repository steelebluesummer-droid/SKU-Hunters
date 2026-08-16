"""Stage 12A · 异步边界回归测试

验证 async 接口把同步重活放入线程池（asyncio.to_thread）后，
洞察生成期间事件循环不被占用：/health 与 /plans 仍能在合理时间返回。
"""
import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI

from app.api.planning import router
from app.planning import repository
from app.planning.insight_resolver import LLMGenerationError

app = FastAPI()
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    snapshot = dict(repository._PLANS)
    repository._PLANS.clear()
    monkeypatch.setattr(repository, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(repository, "_STATE_FILE", tmp_path / "plans_state.json")
    monkeypatch.setattr(repository, "_LEGACY_STATE_FILE", tmp_path / "legacy_plans_state.json")
    yield
    repository._PLANS.clear()
    repository._PLANS.update(snapshot)


async def _create(client, brief=None) -> str:
    r = await client.post("/api/v1/plans", json={"brief": brief or {
        "theme": "2027夏季户外系列", "category": "风扇", "priceRange": [39, 99], "costLimit": 25,
    }})
    assert r.status_code == 201, r.text
    return r.json()["plan_id"]


def test_health_not_blocked_during_slow_insights(monkeypatch):
    """generate-insights 用 to_thread 后，洞察慢执行时 /health 不被阻塞"""
    # 慢同步生成（模拟 LLM 长时间调用）
    def slow_gen(plan):
        time.sleep(1.2)
        raise LLMGenerationError("模拟慢 LLM")
    monkeypatch.setattr("app.planning.pipeline.generate_insights", slow_gen)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            pid = await _create(c)
            t1 = asyncio.create_task(c.post(f"/api/v1/plans/{pid}/actions/generate-insights"))
            await asyncio.sleep(0.15)  # 让洞察任务进入慢执行
            t0 = time.monotonic()
            r_health = await asyncio.wait_for(c.get("/health"), timeout=0.8)
            elapsed = time.monotonic() - t0
            r_ins = await t1
            return r_health, elapsed, r_ins

    r_health, elapsed, r_ins = asyncio.run(run())
    assert r_health.status_code == 200, "洞察执行期间 /health 必须可访问"
    assert elapsed < 0.8, f"/health 被洞察任务阻塞，耗时 {elapsed:.2f}s"
    # 洞察本身因慢 LLM 返回 503（明确错误，而非事件循环挂死）
    assert r_ins.status_code == 503


def test_plans_list_not_blocked_during_slow_insights(monkeypatch):
    """任务列表 /plans 在洞察执行期间不被阻塞"""
    def slow_gen(plan):
        time.sleep(1.2)
        raise LLMGenerationError("模拟慢 LLM")
    monkeypatch.setattr("app.planning.pipeline.generate_insights", slow_gen)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            pid = await _create(c)
            t1 = asyncio.create_task(c.post(f"/api/v1/plans/{pid}/actions/generate-insights"))
            await asyncio.sleep(0.15)
            t0 = time.monotonic()
            r_list = await asyncio.wait_for(c.get("/api/v1/plans"), timeout=0.8)
            elapsed = time.monotonic() - t0
            await t1
            return r_list, elapsed

    r_list, elapsed = asyncio.run(run())
    assert r_list.status_code == 200
    assert elapsed < 0.8, f"/plans 被洞察任务阻塞，耗时 {elapsed:.2f}s"

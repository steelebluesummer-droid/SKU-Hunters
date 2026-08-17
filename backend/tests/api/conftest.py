"""tests/api 共享 fixtures：隔离外部依赖（HTTP 层测试不烧真实外部服务）

- fake_card_llm：企划卡/企划案的 LLM 字段生成注入确定性返回
- fast_insight_agents：洞察链的 LLM 增强代理 fail-soft（返回 None，与 CI 无 Key 行为一致）
- fast_image：即梦出图 fail-soft
- fast_feishu：飞书通知 fail-soft

注：不改动 BASE_PROVIDER_MODE 与主洞察数据源——洞察主链路读本地缓存/飞书，
行为与 tests/planning 保持一致；此处只隔离「生成类」LLM 代理。
"""

import pytest


@pytest.fixture(autouse=True)
def fake_card_llm(monkeypatch):
    CARD_FIELDS = {
        "name": "测试企划卡",
        "concept": "测试概念",
        "designLanguage": "圆润极简",
        "keywords": ["轻量"],
        "features": ["挂绳", "磨砂质感"],
        "fusion": "摆件 × 风扇",
        "pricingReason": "落在机会价格带",
        "schedule": [{"time": "第 1-4 周", "action": "开模打样"}],
        "validation": ["首月售罄率达标"],
    }
    PROPOSAL_FIELDS = {
        "name": "测试企划案",
        "slogan": "测试定位",
        "concept": "测试概念",
        "pattern": "极简纹理",
        "moodboardPrompt": "minimal style",
        "specification": [{"module": "结构", "solution": "折叠收纳"}],
        "skuStrategy": "基础款",
        "launchPlan": "夏季前上市",
        "growthPath": [{"stage": "上市期", "action": "门店陈列"}],
    }
    monkeypatch.setattr(
        "app.planning.plan_card_builder._llm_plan_card_fields",
        lambda plan, opportunity: dict(CARD_FIELDS),
    )
    monkeypatch.setattr(
        "app.planning.plan_card_builder._llm_proposal_fields",
        lambda plan, opportunity, asset: dict(PROPOSAL_FIELDS),
    )


@pytest.fixture(autouse=True)
def frozen_insights(monkeypatch):
    """洞察解析注入冻结 bundle（与 mode=fixture 分支同构）：HTTP 层测试
    不依赖数据源（feishu/爬取）与 LLM；洞察逻辑由 tests/planning 锁定"""
    from app.planning.fixtures import (
        COMPETITIVE_MAP,
        CONSUMER_VOICE,
        INSIGHT_BASE,
        TREND_GALLERY,
        TREND_RADAR,
    )

    def _frozen_bundle(category, brief=None):
        return {
            "trendRadar": {
                **TREND_RADAR,
                "processLog": ["HTTP 层测试：冻结 fixtures 五看洞察"],
            },
            "consumerVoice": CONSUMER_VOICE,
            "competitiveMap": COMPETITIVE_MAP,
            "insightBase": INSIGHT_BASE,
            "trendGallery": TREND_GALLERY,
            "dataSource": "fixture",
        }

    monkeypatch.setattr(
        "app.planning.service._resolve_insight_bundle", _frozen_bundle
    )


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """统一 LLM fail-soft（与 CI 无 Key 行为一致）：洞察主链路读飞书/本地缓存，
    生成类 LLM 代理（机会池/增强/资产适配等）全部走 None 降级分支"""
    monkeypatch.setattr("app.engine.llm.complete", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def fast_insight_agents(monkeypatch):
    """洞察链 LLM 增强代理 fail-soft：本机配了 Key 的环境不发真实请求导致挂起；
    代理逻辑由 tests/planning/ 下各自单测锁定。"""
    monkeypatch.setattr(
        "app.planning.asset_fit_agent.build_asset_fit",
        lambda category, bundle, brief: None,
    )
    monkeypatch.setattr(
        "app.planning.consumer_voice_agent.build_consumer_voice_chains",
        lambda category, bundle, brief: None,
    )
    monkeypatch.setattr(
        "app.planning.competitive_map_agent.build_competitive_map_analysis",
        lambda category, bundle, brief: None,
    )
    monkeypatch.setattr(
        "app.planning.insight_enrichment.build_enrichment",
        lambda category, bundle, brief: None,
    )


@pytest.fixture(autouse=True)
def fast_image(monkeypatch):
    monkeypatch.setattr(
        "app.services.jimeng.generate_concept_image",
        lambda prompt, fallback: fallback,
    )


@pytest.fixture(autouse=True)
def fast_feishu(monkeypatch):
    # 飞书通知 fail-soft：不碰真实飞书 API（通知逻辑由 tests/feishu 锁定）
    monkeypatch.setattr(
        "feishu.notify.notify_opportunities_ready", lambda plan, opportunities: True
    )
    monkeypatch.setattr("feishu.notify.notify_plan_archived", lambda plan: True)


@pytest.fixture(autouse=True)
def fast_live_board(monkeypatch):
    """实时数据看板不爬真实平台（真实链路由 tests/planning/test_live_data 锁定）"""
    from app.planning import fixtures as _fx

    monkeypatch.setattr(
        "app.api.planning.build_live_data_board",
        lambda: {**_fx.DATA_BOARD, "priceBands": _fx.COMPETITIVE_MAP["priceBands"]},
    )

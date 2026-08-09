"""LangGraph 编排 — 五幕圆桌会议图 + 双门人在回路

拓扑（与全景设计文档 4.2/5.5 一致）：

    START → brief_node ─┬─→ trend_agent ─┐
                        ├─→ user_agent  ─┼─→ 🚪act1_gate ─→ creative_agent ─┬─→ business_agent ─┐
                        └─→ ip_agent    ─┘        ↕ qa                       └─→ gtm_agent     ─┴─→ decision_engine
                                                                                                        │
                              ┌─ retro_qa ←→ 🚪retro_gate ←─ 🚪human_gate ←─────────────────────────────┘
                              ↓            （复盘窗：chat/done，  ↕ qa
                              └──────────→ learning_node         不打回重做）
                                             ↓
                                            END

关键设计：
- 真/假 Agent 零成本替换：节点是薄包装层，只认 AGENT_REGISTRY 注册表
- 双门 interrupt：超时逻辑不在图里，由 run_review 的 ask_human 回调实现
- run_review(brief) → async iterator，事件格式 {"role","content","evidence","score"}
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.mock_agents import (
    MockBusinessAgent,
    MockCreativeAgent,
    MockGTMAgent,
    MockIPAgent,
    MockTrendAgent,
    MockUserAgent,
)
from app.engine import llm
from app.engine.decision_engine import DecisionEngine
from app.engine.state import CommitteeState
from app.schemas import (
    Brief,
    Confidence,
    ConflictRecord,
    ConflictType,
    FeatureMatrix,
    GTMPlan,
    IPAssessment,
    OpportunityScore,
    ProposalSet,
    UserSentiment,
    Weights,
    WeightTemplate,
)

# ── Agent 注册表：真 Agent 出炉后只改这里 ──────────────────────
AGENT_REGISTRY: dict[str, type] = {
    "trend": MockTrendAgent,
    "user": MockUserAgent,
    "ip": MockIPAgent,
    "creative": MockCreativeAgent,
    "business": MockBusinessAgent,
    "gtm": MockGTMAgent,
}

# ── 权重模板：把参数问题翻译成业务语言（剧本 5.4）──────────────
_TEMPLATE_WEIGHTS = {
    WeightTemplate.DEFAULT: Weights(),
    WeightTemplate.VOLUME: Weights(
        trend_heat=0.25, user_demand=0.40, ip_fit=0.15,
        competition=0.10, history_analog=0.10,
    ),
    WeightTemplate.IMAGE: Weights(
        trend_heat=0.45, user_demand=0.20, ip_fit=0.20,
        competition=0.05, history_analog=0.10,
    ),
    WeightTemplate.PROFIT: Weights(
        trend_heat=0.30, user_demand=0.20, ip_fit=0.20,
        competition=0.15, history_analog=0.15,
    ),
}


# ══════════════════ 节点 ══════════════════

async def brief_node(state: CommitteeState) -> dict[str, Any]:
    """BRIEF_LOCKED：冻结输入，解析权重"""
    brief = Brief.model_validate(state["brief"])
    weights = brief.custom_weights or _TEMPLATE_WEIGHTS[brief.weight_template]
    return {
        "weights": weights.model_dump(),
        "current_act": "brief",
        "review_logs": [{"node": "brief_node", "act": "brief", "status": "locked"}],
    }


def _feedback(state: CommitteeState) -> str:
    """提取最近一次人工修改意见（供重跑的 Agent 参考）"""
    decision = state.get("human_decision") or {}
    if decision.get("action") == "modify":
        return decision.get("suggestion", "")
    return ""


def _check_evidence(dump: dict[str, Any], agent_key: str, act: str) -> list[dict]:
    """铁律之二：无证据不得发言。

    证据非空 → 放行；证据为空但声明 UNKNOWN → 合法，记 C5 冲突；
    证据为空且自称有把握 → 拒绝（数据不足却硬编结论）。
    """
    if dump.get("evidence_refs"):
        return []
    if dump.get("confidence") == Confidence.UNKNOWN.value:
        return [
            ConflictRecord(
                conflict_type=ConflictType.C5_INSUFFICIENT,
                parties=[agent_key],
                description="证据不足，该委员声明无法判断",
                resolution="open",
                act=act,
            ).model_dump()
        ]
    raise ValueError(f"{agent_key} 输出缺少证据引用（无证据不得发言）")


def _make_insight_node(agent_key: str, artifact_key: str, schema: type):
    """ACT1 洞察官节点工厂：三官并行，各自写自己的 artifact 键"""

    async def node(state: CommitteeState) -> dict[str, Any]:
        agent = AGENT_REGISTRY[agent_key]()
        raw = await agent.run({
            "brief": state["brief"],
            "feedback": _feedback(state),
        })
        artifact = schema.model_validate(raw).model_dump(mode="json")
        return {
            artifact_key: artifact,
            # 注意：并行节点不写 current_act 等共享标量键，
            # 否则 LastValue channel 报并发写冲突；幕标记由下游门节点写
            "conflicts": _check_evidence(artifact, agent_key, "act1"),
            "review_logs": [{"node": agent_key, "act": "act1", "status": "ok"}],
        }

    return node


async def creative_node(state: CommitteeState) -> dict[str, Any]:
    """ACT2 创意官：汇聚三方情报（fan-in）"""
    agent = AGENT_REGISTRY["creative"]()
    raw = await agent.run({
        "brief": state["brief"],
        "feature_matrix": state.get("feature_matrix"),
        "user_sentiment": state.get("user_sentiment"),
        "ip_assessment": state.get("ip_assessment"),
        "feedback": _feedback(state),
    })
    return {
        "proposal_set": ProposalSet.model_validate(raw).model_dump(mode="json"),
        "current_act": "act2",
        "review_logs": [{"node": "creative", "act": "act2", "status": "ok"}],
    }


async def business_node(state: CommitteeState) -> dict[str, Any]:
    """ACT3 商业官：对每个提案出五维评分（算术由 schema 强制校验）"""
    agent = AGENT_REGISTRY["business"]()
    upstream = [
        state.get("feature_matrix", {}).get("confidence", "unknown"),
        state.get("user_sentiment", {}).get("confidence", "unknown"),
        state.get("ip_assessment", {}).get("confidence", "unknown"),
    ]
    raw = await agent.run({
        "brief": state["brief"],
        "weights": state["weights"],
        "proposal_set": state["proposal_set"],
        "upstream_confidences": upstream,
        "feedback": _feedback(state),
    })
    scores = [
        OpportunityScore.model_validate(s).model_dump(mode="json")
        for s in raw["opportunity_scores"]
    ]
    return {
        "opportunity_scores": scores,
        "current_act": "act3",
        "review_logs": [{"node": "business", "act": "act3", "status": "ok"}],
    }


async def gtm_node(state: CommitteeState) -> dict[str, Any]:
    """ACT3 全球化官（Phase 2 占位，与商业官并行）"""
    agent = AGENT_REGISTRY["gtm"]()
    raw = await agent.run({
        "brief": state["brief"],
        "proposal_set": state["proposal_set"],
    })
    plans = [
        GTMPlan.model_validate(p).model_dump(mode="json") for p in raw["gtm_plans"]
    ]
    return {
        "gtm_plans": plans,
        "review_logs": [{"node": "gtm", "act": "act3", "status": "ok"}],
    }


async def decision_node(state: CommitteeState) -> dict[str, Any]:
    """ACT4 Decision Engine：合成立项建议书"""
    rec = DecisionEngine().synthesize(
        proposal_set=state["proposal_set"],
        opportunity_scores=state["opportunity_scores"],
        conflicts=state.get("conflicts", []),
    )
    return {
        "recommendation": rec.model_dump(mode="json"),
        "current_act": "act4",
        "review_logs": [{"node": "decision_engine", "act": "act4", "status": "ok"}],
    }


# ── 双门 ────────────────────────────────────

def _gate(decision: dict[str, Any], act: str) -> dict[str, Any]:
    """门节点公共返回：记录人工决定；修改/否决记 C4 人机冲突（人赢，留理由）

    reweight（modify + custom_weights）时把新权重写进 state，商业官重算即生效。
    """
    action = decision.get("action", "confirm")
    update: dict[str, Any] = {
        "human_decision": decision,
        "current_act": act,
        "review_logs": [{"node": act, "decision": action,
                         "detail": decision.get("suggestion")
                         or decision.get("reason")
                         or decision.get("question", "")}],
    }
    if action in ("modify", "reject"):
        reason = decision.get("suggestion") or decision.get("reason", "")
        prefix = "人否决立项" if action == "reject" else "人工要求修改"
        update["conflicts"] = [
            ConflictRecord(
                conflict_type=ConflictType.C4_HUMAN_AI,
                parties=["human", "committee"],
                description=f"{prefix}：{reason}",
                resolution="resolved",
                act=act,
            ).model_dump()
        ]
    if decision.get("custom_weights"):
        update["weights"] = Weights.model_validate(
            decision["custom_weights"]
        ).model_dump()
    return update


def act1_gate(state: CommitteeState) -> dict[str, Any]:
    """🚪 Gate 1：洞察确认门——方向不对趁早打回，省掉后面 2/3 计算"""
    decision = interrupt({
        "gate": "act1_gate",
        "prompt": "三位洞察官已完成陈述，请确认方向（确定/修改/疑问）",
        "options": ["confirm", "modify", "question"],
    })
    return _gate(decision, "act1_gate")


def human_gate(state: CommitteeState) -> dict[str, Any]:
    """🚪 Gate 2：立项拍板门——AI 建议在此刻变成人的决策，留痕"""
    decision = interrupt({
        "gate": "human_gate",
        "prompt": "立项建议书已生成，请拍板（确定/修改/疑问）",
        "options": ["confirm", "modify", "question"],
    })
    return _gate(decision, "human_gate")


def _make_qa_node(gate: str):
    """疑问节点：只读 state 作答，不污染任何 artifact，答完回到同一个门"""

    def node(state: CommitteeState) -> dict[str, Any]:
        question = (state.get("human_decision") or {}).get("question", "")
        artifacts = [
            k for k in ("feature_matrix", "user_sentiment", "ip_assessment",
                        "proposal_set", "opportunity_scores", "recommendation")
            if state.get(k)
        ]
        answer = (
            f"关于「{question}」：当前会议已产出 {len(artifacts)} 份产物"
            f"（{', '.join(artifacts)}），每条结论的证据见对应委员卡片的"
            f"证据来源栏。（QA 节点占位，接入 LLM 后基于证据链作答）"
        )
        return {
            "current_act": f"qa@{gate}",
            "review_logs": [{"node": f"qa@{gate}", "act": gate, "answer": answer}],
        }

    return node


# ── 会后复盘窗 ──────────────────────────────────

def retro_gate(state: CommitteeState) -> dict[str, Any]:
    """🚪 复盘窗：结论已定，不再打回重做；人可自由对话、总结教训（学习官的输入）

    chat/question → retro_qa 作答后回到本窗；done/confirm → 学习官归档。
    """
    decision = interrupt({
        "gate": "retro",
        "prompt": "评审已结论。复盘窗口开启：可提问、讨论、总结教训（chat），或结束（done）",
        "options": ["chat", "done"],
    })
    decision = decision or {"action": "done"}
    return {
        "human_decision": decision,
        "current_act": "retro",
        "review_logs": [{"node": "retro_gate", "decision": decision.get("action", "done"),
                         "detail": decision.get("question")
                         or decision.get("content", "")}],
    }


def _state_digest(state: CommitteeState) -> str:
    """把本场会议产物压成纯文本摘要，供 LLM 复盘作答"""
    parts = []
    if fm := state.get("feature_matrix"):
        parts.append(f"趋势官：{fm.get('summary', '')}")
    if us := state.get("user_sentiment"):
        parts.append(f"用户官：{us.get('summary', '')}")
    if ip := state.get("ip_assessment"):
        parts.append(f"IP官：{ip.get('strategy_note', '')}")
    for s in state.get("opportunity_scores", []):
        parts.append(f"商业官评分：{s.get('proposal_name', '')} {s.get('total_score', 0):.1f} 分")
    if rec := state.get("recommendation"):
        parts.append(
            f"立项建议：{rec.get('decision', '')}，"
            f"Top1「{rec.get('proposal', {}).get('name', '')}」，"
            f"{rec.get('summary', '')}"
        )
    return "\n".join(parts)


def retro_qa_node(state: CommitteeState) -> dict[str, Any]:
    """复盘作答：LLM 基于本场证据链回答；无 Key/故障时降级为产物索引"""
    decision = state.get("human_decision") or {}
    question = decision.get("question") or decision.get("content", "")
    digest = _state_digest(state)

    answer = llm.complete(
        system_prompt=(
            "你是 SKU Hunters 商品评审会的复盘助手。基于给定的本场会议产物，"
            "回答商品经理的问题、帮助总结教训。只依据给定材料作答，禁止编造"
            "材料中不存在的数字；材料里没有的信息直接说明。150 字以内。"
        ),
        user_prompt=f"【本场会议产物】\n{digest}\n\n【商品经理的问题】\n{question}",
        max_tokens=400,
    )
    if answer is None:
        answer = (
            f"关于「{question}」：本场会议产物摘要如下——\n{digest}\n"
            f"（LLM 未配置或暂不可用，以上为原始产物索引）"
        )
    return {
        "current_act": "retro",
        "review_logs": [{"node": "retro", "act": "retro",
                         "question": question, "answer": answer}],
    }


async def learning_node(state: CommitteeState) -> dict[str, Any]:
    """ACT5 学习官：会内唯一动作——建档快照（复盘是离线任务）

    bad case（人否决）与通过案同等归档：人决策 + 复盘对话是最宝贵的训练信号。
    """
    rec = state.get("recommendation", {})
    logs = state.get("review_logs", [])
    gate2 = next(
        (log for log in reversed(logs) if log.get("node") == "human_gate"), {}
    )
    snapshot = {
        "session_id": state.get("session_id", ""),
        "proposal": rec.get("proposal", {}).get("name", ""),
        "predicted_score": rec.get("opportunity_score", {}).get("total_score"),
        "ai_decision": rec.get("decision", ""),
        "human_action": gate2.get("decision", ""),
        "retro_turns": sum(1 for log in logs if log.get("node") == "retro"),
        "status": "rejected" if gate2.get("decision") == "reject" else "archived",
    }
    return {
        "current_act": "act5",
        "review_logs": [{"node": "learning", "act": "act5", "snapshot": snapshot}],
    }


# ── 门路由 ───────────────────────────────────

def _route_act1_gate(state: CommitteeState) -> Any:
    action = (state.get("human_decision") or {}).get("action", "confirm")
    if action == "modify":
        # 创意官尚未跑，全场最便宜的回退点：三洞察官重跑
        return ["trend_agent", "user_agent", "ip_agent"]
    if action == "question":
        return "qa_act1_node"
    return "creative_agent"


def _route_human_gate(state: CommitteeState) -> str:
    decision = state.get("human_decision") or {}
    action = decision.get("action", "confirm")
    if action == "modify":
        # 最小失效：参数微调只回退商业官重算，方案大改才回退创意官
        if decision.get("scope") == "creative":
            return "creative_agent"
        return "business_agent"
    if action == "question":
        return "qa_act4_node"
    # confirm / reject 都进复盘窗：通过案与 bad case 同等留对话机会
    return "retro_gate"


def _route_retro_gate(state: CommitteeState) -> str:
    action = (state.get("human_decision") or {}).get("action", "done")
    if action in ("chat", "question"):
        return "retro_qa_node"
    return "learning_node"


# ══════════════════ 建图 ══════════════════

def build_graph() -> Any:
    g = StateGraph(CommitteeState)

    g.add_node("brief_node", brief_node)
    g.add_node("trend_agent", _make_insight_node("trend", "feature_matrix", FeatureMatrix))
    g.add_node("user_agent", _make_insight_node("user", "user_sentiment", UserSentiment))
    g.add_node("ip_agent", _make_insight_node("ip", "ip_assessment", IPAssessment))
    g.add_node("act1_gate", act1_gate)
    g.add_node("qa_act1_node", _make_qa_node("act1_gate"))
    g.add_node("creative_agent", creative_node)
    g.add_node("business_agent", business_node)
    g.add_node("gtm_agent", gtm_node)
    g.add_node("decision_engine", decision_node)
    g.add_node("human_gate", human_gate)
    g.add_node("qa_act4_node", _make_qa_node("human_gate"))
    g.add_node("retro_gate", retro_gate)
    g.add_node("retro_qa_node", retro_qa_node)
    g.add_node("learning_node", learning_node)

    g.add_edge(START, "brief_node")
    g.add_edge("brief_node", "trend_agent")
    g.add_edge("brief_node", "user_agent")
    g.add_edge("brief_node", "ip_agent")

    # ACT1 fan-in → Gate 1
    g.add_edge("trend_agent", "act1_gate")
    g.add_edge("user_agent", "act1_gate")
    g.add_edge("ip_agent", "act1_gate")
    g.add_conditional_edges("act1_gate", _route_act1_gate)
    g.add_edge("qa_act1_node", "act1_gate")

    # ACT2 → ACT3 双轨 fan-out
    g.add_edge("creative_agent", "business_agent")
    g.add_edge("creative_agent", "gtm_agent")

    # ACT3 fan-in → ACT4
    g.add_edge("business_agent", "decision_engine")
    g.add_edge("gtm_agent", "decision_engine")
    g.add_edge("decision_engine", "human_gate")

    # Gate 2 → 复盘窗 → ACT5
    g.add_conditional_edges("human_gate", _route_human_gate)
    g.add_edge("qa_act4_node", "human_gate")
    g.add_conditional_edges("retro_gate", _route_retro_gate)
    g.add_edge("retro_qa_node", "retro_gate")
    g.add_edge("learning_node", END)

    return g.compile(checkpointer=MemorySaver())


# ══════════════════ 事件翻译 ══════════════════

def _evidence_of(artifact: dict[str, Any]) -> list[str]:
    """事件 evidence 只从产物 evidence_refs 提取，不允许自由发挥"""
    return [
        f"{ref['title']}：{ref['snippet']}"
        for ref in artifact.get("evidence_refs", [])
    ]


def _translate(node_name: str, update: dict[str, Any]) -> dict[str, Any] | None:
    """节点 state 更新 → 飞书卡片事件 {"role","content","evidence","score"}"""
    if node_name == "trend_agent":
        a = update["feature_matrix"]
        return {"role": "trend", "content": a["summary"],
                "evidence": _evidence_of(a), "score": None}
    if node_name == "user_agent":
        a = update["user_sentiment"]
        return {"role": "user", "content": a["summary"],
                "evidence": _evidence_of(a), "score": None}
    if node_name == "ip_agent":
        a = update["ip_assessment"]
        top = a["ip_ranking"][0] if a["ip_ranking"] else {}
        content = (
            f"{a.get('strategy_note', '')}\n"
            f"首选 IP：{top.get('ip_name', '无')}"
            f"（热度 {top.get('heat_score', 0)}，窗口期 {top.get('window_estimate', '-')}）"
        )
        return {"role": "ip", "content": content,
                "evidence": _evidence_of(a), "score": None}
    if node_name == "creative_agent":
        a = update["proposal_set"]
        lines = [f"{i}. {p['name']}（{p['product_form']}，{p['price_band']}）"
                 for i, p in enumerate(a["proposals"], 1)]
        return {"role": "creative",
                "content": "创意方案：\n" + "\n".join(lines),
                "evidence": [], "score": None}
    if node_name == "business_agent":
        scores = update["opportunity_scores"]
        top = max(scores, key=lambda s: s["total_score"])
        lines = [f"· {s['proposal_name']}：{s['total_score']:.1f} 分"
                 for s in scores]
        return {"role": "business",
                "content": "五维机会值评分：\n" + "\n".join(lines),
                "evidence": _evidence_of(top), "score": top["total_score"]}
    if node_name == "gtm_agent":
        return {"role": "global",
                "content": f"已生成 {len(update['gtm_plans'])} 份上市策略（Phase 2 占位）",
                "evidence": [], "score": None}
    if node_name == "decision_engine":
        rec = update["recommendation"]
        return {"role": "decision",
                "content": rec["summary"],
                "evidence": _evidence_of(rec["opportunity_score"]),
                "score": rec["opportunity_score"]["total_score"],
                "report": rec}  # 完整建议书：API report 端点用，四键契约不变
    if node_name == "learning_node":
        snap = update["review_logs"][-1].get("snapshot", {})
        bad = snap.get("status") == "rejected"
        return {"role": "learning",
                "content": (
                    f"已建档{'（bad case）' if bad else ''}："
                    f"「{snap.get('proposal', '')}」"
                    f"预测分 {snap.get('predicted_score')}，"
                    f"AI 建议 {snap.get('ai_decision')} / 人决策 {snap.get('human_action')}，"
                    f"复盘对话 {snap.get('retro_turns', 0)} 轮已入档。"
                ),
                "evidence": [], "score": None}
    if node_name == "retro_qa_node":
        answer = update["review_logs"][-1].get("answer", "")
        return {"role": "retro", "content": answer, "evidence": [], "score": None}
    if node_name.startswith("qa_"):
        answer = update["review_logs"][-1].get("answer", "")
        return {"role": "qa", "content": answer, "evidence": [], "score": None}
    return None  # brief_node / 门节点不产生委员事件


def _describe(decision: dict[str, Any]) -> str:
    action = decision.get("action", "confirm")
    if action == "modify":
        return f"✏️ 修改：{decision.get('suggestion', '')}（回退重跑）"
    if action == "reject":
        return f"❌ 否决立项：{decision.get('reason', '')}（归档为 bad case）"
    if action == "question":
        return f"❓ 疑问：{decision.get('question', '')}"
    if action == "chat":
        return f"💬 复盘：{decision.get('question') or decision.get('content', '')}"
    if action == "done":
        return "📝 复盘结束，归档"
    return "✅ 确定，继续"


# ══════════════════ 驱动入口 ══════════════════

AskHuman = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def _auto_confirm(gate_info: dict[str, Any]) -> dict[str, Any]:
    """默认问人回调：直接确定（CI/演示用；飞书侧实现带 10 秒超时的版本）"""
    return {"action": "confirm"}


async def run_review(
    brief: dict[str, Any],
    ask_human: AskHuman | None = None,
    session_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """跑一轮完整评审，以异步事件流输出

    Args:
        brief: 评审输入（Brief 契约，dict 形式）
        ask_human: 门节点问人回调，返回 {"action": confirm/modify/question, ...}。
                   超时逻辑由调用方在此回调内实现（如 asyncio.wait_for 10s）。
        session_id: 会话 ID（checkpoint thread_id，可恢复）

    Yields:
        {"role", "content", "evidence", "score"} —— handler README 约定格式，
        门事件 role 为 act1_gate/human_gate，问答事件 role 为 qa。
    """
    ask = ask_human or _auto_confirm
    Brief.model_validate(brief)
    graph = build_graph()
    config = {"configurable": {"thread_id": session_id or str(uuid.uuid4())}}

    payload: Any = {
        "brief": brief,
        "session_id": config["configurable"]["thread_id"],
        "current_act": "init",
    }
    while True:
        pending_gate: dict[str, Any] | None = None
        async for chunk in graph.astream(payload, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                if node_name == "__interrupt__":
                    pending_gate = update[0].value
                    continue
                event = _translate(node_name, update)
                if event:
                    yield event
        if pending_gate is None:
            return
        yield {"role": pending_gate["gate"], "content": pending_gate["prompt"],
               "evidence": [], "score": None}
        decision = await ask(pending_gate)
        yield {"role": pending_gate["gate"], "content": _describe(decision),
               "evidence": [], "score": None}
        payload = Command(resume=decision)

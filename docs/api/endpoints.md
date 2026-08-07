# API 端点约定（D1 冻结版）

> 前端（组员B）与后端（组长/组员A）的对接契约。冻结后任何变更需在群里声明。

Base URL: `/api/v1`

## 1. 发起评审

```
POST /reviews
```

**Request**
```json
{
  "brief": {
    "category": "潮玩",
    "market": "TH",
    "budget_range": "mid",
    "time_window": "2026-Q4",
    "weight_template": "default",
    "custom_weights": null,
    "candidate_pool": ["Labubu", "Chiikawa", "线条小狗"]
  }
}
```

**Response 201**
```json
{ "session_id": "sess_20260808_a1b2", "status": "created" }
```

## 2. 查询会议状态（前端轮询/长连接）

```
GET /reviews/{session_id}
```

**Response 200**
```json
{
  "session_id": "sess_20260808_a1b2",
  "current_act": "act3_dual_review",
  "status": "running",
  "acts_completed": ["brief_locked", "act1_insights", "act1_gate", "act2_ideation", "act2_challenge"],
  "live_feed": [
    {
      "act": "act1",
      "agent": "trend_agent",
      "speech_card": {
        "conclusion": "Labubu 处于扩散后期",
        "confidence": "medium",
        "caveats": ["B站排行 ≠ 全网创作热度"],
        "evidence_count": 2
      },
      "timestamp": "2026-08-08T10:01:22Z"
    }
  ],
  "conflicts": [
    {
      "conflict_type": "c1_data_signal",
      "parties": ["trend_agent", "consumer_insight_agent"],
      "description": "消费需求信号与内容创作信号背离"
    }
  ]
}
```

`current_act` 枚举：`brief_locked / act1_insights / act1_gate / act2_ideation / act2_challenge / act3_dual_review / act4_decision / human_gate / approved / revised / rejected / act5_retro / learned / failed`

## 3. 获取立项建议书

```
GET /reviews/{session_id}/report
```

**Response 200**
```json
{
  "session_id": "sess_20260808_a1b2",
  "proposals": [
    {
      "name": "IP娃衣系列",
      "total_score": 76,
      "star_rating": 4,
      "recommendation": "hold",
      "dimension_scores": [
        {"dimension": "trend_heat", "score": 62, "source_agent": "trend_agent"}
      ],
      "risk_warnings": [{"risk": "娃衣复购依赖IP持续热度", "source_dimension": "trend_heat"}],
      "evidence_refs": [{"url": "...", "title": "...", "snippet": "..."}]
    }
  ],
  "divergence_records": [],
  "open_questions": ["需补充多平台趋势数据后复审方向一"],
  "markdown_url": "/api/v1/reviews/{session_id}/report.md"
}
```

## 4. 人工决策（HUMAN_GATE）

```
POST /reviews/{session_id}/decision
```

**Request**
```json
{
  "action": "approve | reject | revise | reweight",
  "reason": "否决/批准理由（action 为 approve/reject 时必填）",
  "custom_weights": null,
  "interrupt": null
}
```

- `reweight`：带 `custom_weights`，仅重跑评分合成（秒级）
- `interrupt`：打断注入，结构 `{"type": "challenge|supplement|redirect", "content": "...", "target_node": "ip_strategy_agent"}`

**Response 200**：返回更新后的状态（同端点 2 格式）

## 5. 权重模板列表

```
GET /weights/templates
```

**Response 200**
```json
{
  "templates": [
    {"key": "default", "label": "默认均衡", "weights": {"trend_heat": 0.35, "..." : "..."}},
    {"key": "volume", "label": "走量款", "weights": {}},
    {"key": "image", "label": "形象款", "weights": {}},
    {"key": "profit", "label": "利润款", "weights": {}}
  ]
}
```

## 错误格式（统一）

```json
{ "error": { "code": "WEIGHT_SUM_INVALID", "message": "五维权重之和必须为 1.0" } }
```

| 错误码 | 含义 |
|:---|:---|
| `BRIEF_INVALID` | 输入契约校验失败 |
| `WEIGHT_SUM_INVALID` | 权重和不为 1 |
| `SESSION_NOT_FOUND` | 会议不存在 |
| `SESSION_NOT_AT_GATE` | 未到人工决策点，不能提交 decision |
| `DECISION_REASON_REQUIRED` | approve/reject 未填理由 |

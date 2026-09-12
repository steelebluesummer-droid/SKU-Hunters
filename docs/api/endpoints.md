# API 端点说明

> 当前后端 API 以 `backend/app/api/planning.py` 为事实源。除 `/health` 和根路径外，企划、数据看板与小红书接口统一挂在 `/api/v1`。

## 运行状态

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查，返回严格模式和 Mock 是否允许 |
| GET | `/` | 服务基本信息 |

## 企划任务

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/plans` | 同步创建企划任务 |
| POST | `/api/v1/plans/async` | 异步创建任务并后台执行洞察、机会 |
| POST | `/api/v1/plans/aily-create` | Aily 轻入口，异步创建任务；完成后可由飞书通知 |
| GET | `/api/v1/plans` | 任务列表 |
| GET | `/api/v1/plans/{plan_id}` | 任务详情、状态和已生成产物 |
| DELETE | `/api/v1/plans/{plan_id}` | 删除任务 |
| GET | `/api/v1/plans/{plan_id}/insights` | 读取五看洞察 |
| GET | `/api/v1/plans/{plan_id}/opportunities` | 读取机会方向 |

创建请求的 `brief` 至少包含 `theme`、`category`；`market`、`audience`、`price_range`、`cost_limit`、`ip_strategy`、`launch_window` 和 `goals` 可选。任务数据模式由 `mode`/部署配置控制。当前支持 `fixture`（显式演示）、`crawled`（本地采集，非生产默认）和 `live`（真实数据）；严格生产模式固定走 `live`，失败不会静默回退演示数据。

## 企划流程动作

前端和新客户端应优先使用以下原子动作。每个动作负责生成产物并在成功后推进状态，避免“状态已推进但产物未生成”的半完成态。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/plans/{plan_id}/actions/generate-insights` | 生成洞察 |
| POST | `/api/v1/plans/{plan_id}/actions/generate-opportunities` | 生成机会方向 |
| POST | `/api/v1/plans/{plan_id}/actions/generate-plan-card` | 根据 `opportunity_id` 生成企划卡 |
| POST | `/api/v1/plans/{plan_id}/actions/rechoose-opportunity` | 重新选择机会方向 |
| POST | `/api/v1/plans/{plan_id}/actions/archive` | 归档企划并触发飞书同步 |
| POST | `/api/v1/plans/{plan_id}/revise/preview` | 预览改稿结果 |
| POST | `/api/v1/plans/{plan_id}/revise/apply` | 应用改稿 |
| POST | `/api/v1/plans/{plan_id}/revise/cancel` | 取消改稿 |
| POST | `/api/v1/plans/{plan_id}/review` | 归档后的只读复盘追问 |

以下路径仅为旧客户端兼容入口，新代码不要继续使用：

- `/api/v1/plans/{plan_id}/advance`
- `/api/v1/plans/{plan_id}/plan-card`
- `/api/v1/plans/{plan_id}/archive`
- `/api/v1/plans/{plan_id}/revise`

## 数据看板与资源

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/data-board` | 全局数据看板 |
| GET | `/api/v1/insight-base?topic=...` | 洞察库 |
| GET | `/api/v1/trend-gallery?topic=...` | 趋势色板与趋势图库 |
| GET | `/api/v1/trend-scan` | 趋势扫描结果 |
| GET | `/api/v1/ip-library` | IP 库 |
| GET | `/api/v1/ip-library/image?file_token=...` | IP 图片代理 |
| GET | `/api/v1/ip-resource` | IP 资源详情 |

## 小红书独立数据接口

小红书目前是“本地文件导入 + 清洗统计”的独立链路，不是企划任务的实时数据源，也不会把本地样例伪装成实时采集。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/xhs/ingest` | 导入本地 JSON/CSV |
| GET | `/api/v1/xhs/notes` | 笔记列表 |
| GET | `/api/v1/xhs/notes/{note_id}` | 笔记详情 |
| GET | `/api/v1/xhs/stats` | 统计汇总 |
| GET | `/api/v1/xhs/stats/keywords` | 关键词统计 |
| GET | `/api/v1/xhs/stats/engagement` | 互动量与互动率 |
| GET | `/api/v1/xhs/stats/tags` | 高频标签 |
| GET | `/api/v1/xhs/stats/trend` | 发布时间趋势 |
| GET | `/api/v1/xhs/stats/top` | Top 笔记 |
| GET | `/api/v1/xhs/stats/wordfreq` | 文本词频 |
| GET | `/api/v1/xhs/runs` | 导入运行记录 |

## 相关实现

- 企划路由：`backend/app/api/planning.py`
- 企划编排：`backend/app/planning/pipeline.py`
- 持久化：`backend/app/planning/repository.py`
- 前端请求层：`frontend/src/api/{client,plans,insights,dashboard}.js`
- 飞书群机器人：`backend/feishu/group_bot.py`；长连接入口：`backend/feishu/longconn.py`

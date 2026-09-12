# AGENTS.md — AI 编程工具协作者指南

> 本文件面向 AI 编程助手（Claude Code / Cursor / Copilot 等）。
> 人类队友请先看各模块 README；本文件是当前仓库的机器可执行接口契约。

## 项目一句话

SKU Hunters 是一个证据驱动的 AI 新品企划工作室：FastAPI 后端负责“五看洞察 → 机会方向 → 企划卡 → 归档复盘”链路，React 前端负责工作室交互，飞书负责群入口、通知和资产归档。

## 当前架构

- `backend/app/api/planning.py`：`/api/v1/plans` 及原子业务动作 API。
- `backend/app/planning/repository.py`：企划任务持久化、创建、查询和状态事实源。
- `backend/app/planning/service.py`：洞察、机会、企划卡、改稿、归档和复盘服务。
- `backend/app/planning/pipeline.py`：规划服务的兼容导出入口；新代码优先调用明确的 service/API 函数。
- `backend/app/engine/strict_mode.py`：严格真实模式和默认任务模式的单一事实源。
- `backend/feishu/group_bot.py`：飞书群需求解析、表单补全、机会点选、企划卡生成和归档闭环。
- `backend/feishu/longconn.py`：飞书 WebSocket 长连接；由 `app.main` 启动，不依赖公网 webhook 或内网穿透。
- `backend/feishu/cards_v2.py`、`doc_report.py`：新版飞书卡片和在线报告。
- `frontend/src/api/`：按 `client`、`plans`、`insights`、`dashboard` 拆分的请求层。
- `frontend/src/features/`：任务中心、任务流程、洞察、机会、企划卡和数据看板页面。

## 硬性纪律（违反 = CI 红）

1. **密钥只存在于 `.env`**，禁止硬编码 App ID / Secret / API Key。
2. **D1 已冻结的 schema 不得修改**（`backend/app/schemas/` 现有文件）；新增契约必须新增文件。
3. 所有路径用 `Path(__file__).resolve()` 锚定，禁止写死绝对路径。
4. 提交前从仓库根运行 `ruff check backend/`，从 `backend/` 运行 `pytest tests/ --cov=app`。

## 严格真实模式（Strict Real Mode）

生产环境使用以下配置：

```env
APP_ENV=production
ALLOW_MOCK=false
BASE_PROVIDER_MODE=feishu
PLANNING_DEFAULT_MODE=live
AGENT_PROVIDER=real
LEARNING_AGENT_PROVIDER=real
```

- `APP_ENV=production` 且 `ALLOW_MOCK=false` 时，禁止 Mock、fixture 和 demo 回退；LLM/数据源失败必须显式阻断，真实数据不足使用 `unavailable`，字段缺失使用 `unknown`。
- 严格模式默认任务模式强制为 `live`，禁止创建或打开 fixture/demo 任务；`/health` 应返回 `mock_allowed=false, strict_real=true`。
- 非生产环境默认允许测试/演示用的 fixture；任务默认模式由 `PLANNING_DEFAULT_MODE` 控制，未配置时为 `crawled`。
- `live` 任务的数据事实源应记录为 Feishu 或 `unavailable`，不可静默伪装成 fixture。

## 后端 API 契约

主要链路：

1. `POST /api/v1/plans`：同步创建企划任务。
2. `POST /api/v1/plans/async`：异步创建并后台执行洞察、机会。
3. `GET /api/v1/plans/{id}`：读取任务、状态和产物。
4. `POST /api/v1/plans/{id}/actions/generate-insights`：生成五看洞察。
5. `POST /api/v1/plans/{id}/actions/generate-opportunities`：生成机会方向。
6. `POST /api/v1/plans/{id}/actions/generate-plan-card`：点选方向后生成企划卡。
7. `POST /api/v1/plans/{id}/actions/archive`：归档并触发飞书同步。
8. `POST /api/v1/plans/{id}/revise/preview`、`revise/apply`、`revise/cancel`：改稿预览、应用和取消。
9. `POST /api/v1/plans/{id}/review`：归档后的只读复盘追问。

`advance`、无 `actions` 的 `plan-card` 和 `archive` 端点仍保留为旧客户端兼容入口；新客户端使用 `actions/*` 原子动作，避免状态已推进但产物未生成的半完成态。

## 飞书群闭环

飞书群里 @机器人后：

```text
一句话需求 → NL 解析品类/IP/价格/人群
→ 信息不足时发 Card 2.0 表单补全
→ 五看洞察 → 三张机会方向卡
→ 人工点选方向 → 生成企划卡/概念图
→ 归档 → 群内回传报告卡，并同步企划资产库
```

入站事件由 `longconn.py` 接收，重任务交给 `group_bot.py` 线程池；长连接回调必须快速返回。飞书卡片使用新版 schema 2.0。归档后可在前端或 API 只读复盘，不能继续改稿。

## 修改和验证原则

- 不依赖未声明的 state 字段；API/服务边界返回值必须通过对应 Pydantic schema 校验。
- 前端展示组件使用 props 和事件回调，不直接 import 企划 fixture，不在请求失败时静默替换成演示数据。
- 真实数据来源必须显式标注：`feishu`、`crawled`、`llm`、`fixture` 或 `unavailable`。
- 修改完成后至少执行 `git diff --check`、目标文件语法/构建检查，以及项目规定的 ruff/pytest 命令；若环境缺依赖，必须在提交说明中如实记录。

## 排障速查

| 现象 | 优先检查 |
|:---|:---|
| API 后台任务不推进 | 使用 `with TestClient(app) as c:`，保证后台任务生命周期持续 |
| 企划卡状态错误 | 确认调用的是 `actions/generate-*` 原子端点，而不是旧兼容组合 |
| 飞书群无响应 | 检查 `FEISHU_APP_ID/SECRET`、`FEISHU_LONGCONN`，并确认单进程、单 worker |
| 飞书卡片无回调 | 检查卡片 schema 2.0、唯一 `name` 和 callback 行为 |
| 严格模式仍出现演示数据 | 检查 `APP_ENV`、`ALLOW_MOCK`、`BASE_PROVIDER_MODE` 和 fallback 守卫 |

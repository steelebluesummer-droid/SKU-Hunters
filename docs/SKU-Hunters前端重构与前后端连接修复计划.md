# SKU-Hunters 前端重构与前后端连接修复（历史实施记录）

> 文档状态：本文件记录早期前端重构的背景、方案和验收口径，不是当前开发规范。
> 主要工作已经落地；当前实现以 `frontend/src/`、`backend/app/`、`README.md` 和
> `AGENTS.md` 为准。文中旧的 `src/api.js`、`src/mock/fanData.js`、`Home.jsx`、
> `api.js` 原地 mutate 方案仅保留作历史背景，不应按此继续开发。

## 一、历史背景

早期版本存在机会卡不遵守 IP 约束、动态企划卡可能 404、前后端键名不一致、任务详情误用 demo 数据，以及前端组件直接依赖 mock 常量等问题。该阶段的修复目标是把前端改成 props/API 驱动，并把企划流程收敛到统一的后端状态机。

## 二、当前已落地结果

- 机会方向会读取当前企划的 IP 策略；指定 IP 会在机会卡和概念图 prompt 中锁定。
- 非 fixture 任务使用动态企划卡组装路径，包含概念、设计、定价、成本校验和上市节奏。
- 前端 API 已拆分为 `frontend/src/api/client.js`、`plans.js`、`insights.js` 和 `dashboard.js`。
- 当前页面由真实任务数据驱动：任务中心、任务流程、洞察驾驶舱、机会卡、企划卡、数据看板、IP 资源库和流行元素板。
- 企划流程使用原子动作接口：

  ```text
  POST /api/v1/plans/{id}/actions/generate-insights
  POST /api/v1/plans/{id}/actions/generate-opportunities
  POST /api/v1/plans/{id}/actions/generate-plan-card
  POST /api/v1/plans/{id}/actions/archive
  ```

- 任务状态为 `brief_locked → insights_ready → opportunities_ready → plan_card_ready → archived`；异步后台阶段另用 `insights/opportunities/done/failed` 表示进度。
- 请求失败显示结构化错误和重试，不自动切换到本地 mock。离线演示需显式使用 fixture 任务。

## 三、当前前端入口

| 路由 | 页面 |
|:---|:---|
| `/` | 企划中心 |
| `/new` | 新建新品企划 |
| `/tasks/:id` | 企划流程 |
| `/dashboard` | 数据看板 |
| `/insight-base` | 名创内部资产 |
| `/ip-library` | IP 资源库 |
| `/trend-gallery` | 流行元素板 |

## 四、后续工作

- 按需补齐小红书统计到数据看板的显式字段映射；当前小红书模块仍是独立导入与统计 API。
- 完善 `source_plan_id` 的复用率统计和展示。
- 继续维护严格真实模式，确保生产环境不静默回退 Mock/fixture。

## 五、验证命令

```bash
# 后端
cd backend
python -m pytest tests/ -q

# 前端
cd frontend
npm test
npm run build
```

具体接口和运行配置请看 [API/运行说明](../README.md)、[前端说明](../frontend/README.md) 和 [飞书说明](../backend/feishu/README.md)。

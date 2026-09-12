# frontend — SKU Hunters 新品企划工作室

前端是 React + Vite + Ant Design + ECharts 工作室，不是旧版“圆桌会议 Dashboard”。页面只通过 API 获取任务数据，接口失败时显示错误和重试，不静默替换成本地演示数据。

## 页面与路由

| 路由 | 页面 | 作用 |
|:---|:---|:---|
| `/` | 企划中心 | 按进行中、已完成、已归档查看任务，支持收藏和删除 |
| `/new` | 新建新品企划 | 填写品类、市场、价格/成本约束、IP 策略和上新窗口 |
| `/tasks/:id` | 企划流程 | 企划约束 → 洞察驾驶舱 → 机会生成 → 新品企划卡 |
| `/dashboard` | 数据看板 | 查看全局趋势和品类数据 |
| `/insight-base` | 名创内部资产 | 查看策展的内部商品资产 |
| `/ip-library` | IP 资源库 | 查看 IP 合作资源和图片 |
| `/trend-gallery` | 流行元素板 | 查看跨品类色彩、纹样和形态趋势 |

## API 请求层

`src/api/` 已按职责拆分：

- `client.js`：统一 `fetch`、30 秒 GET 缓存和结构化错误。
- `plans.js`：创建、查询、删除任务，以及生成洞察、机会、企划卡、改稿、归档和复盘。
- `insights.js`：只读获取五看洞察和机会方向。
- `dashboard.js`：数据看板、内部资产、IP 资源库和流行元素板。

企划生成使用原子动作接口：

```text
POST /api/v1/plans/{id}/actions/generate-insights
POST /api/v1/plans/{id}/actions/generate-opportunities
POST /api/v1/plans/{id}/actions/generate-plan-card
POST /api/v1/plans/{id}/actions/archive
```

旧版 `/api/v1/reviews/*`、`/weights/templates` 和 `src/api.js` 已不属于当前前端架构。

## 状态与数据来源

任务状态为：`brief_locked → insights_ready → opportunities_ready → plan_card_ready → archived`。

异步创建额外使用 `stage=insights|opportunities|done|failed` 表示后台进度。来源标识由后端返回，常见值为 `crawled`、`llm`、`feishu`、`fixture` 和 `unavailable`；生产严格模式禁止 Mock/fixture 回退。

## 本地开发

```bash
npm install
npm run dev       # http://localhost:5173
npm run build
npm test
```

后端 API 默认通过 `/api/v1` 访问；开发时请同时启动 `backend` 服务。

# 飞书对接模块使用说明

当前模块服务于 SKU Hunters 新品企划工作室，包含两条飞书链路：

1. **群机器人闭环**：群里 @机器人提需求，补全约束、生成五看洞察和机会方向，人工点选方向后生成企划卡并归档；归档后生成包含完整企划与概念图的在线云文档并回群。
2. **后端通知/归档**：前端或 Aily 触发的企划任务完成后，后端把机会卡或归档摘要推送到指定群，并把归档结果同步到飞书多维表格；完整云文档交付由群机器人归档流程负责。

本模块不是旧版“七委员圆桌评审会”，不使用 `cards.py`、`handler.py` 或 `webhook.py`，也不依赖公网回调地址。

## 文件结构

```text
feishu/
├── auth.py          # tenant_access_token 获取与缓存
├── config.py        # 环境变量配置
├── bot.py           # 飞书 IM 发消息封装
├── cards_v2.py      # Card schema 2.0 表单、机会选择和状态卡
├── group_bot.py     # 群消息解析、企划流程和卡片回调
├── longconn.py      # WebSocket 长连接生命周期
├── nl_brief.py      # 一句话需求解析和 IP/约束归一化
├── doc_report.py    # 归档企划案在线文档/报告卡
├── bitable_sync.py  # 企划归档同步到多维表格
└── notify.py        # Aily/后端任务结果通知
```

## 快速开始

### 1. 创建飞书应用

在飞书开放平台创建企业自建应用并开启机器人能力，按实际部署开通消息接收、发送消息和多维表格读写权限。将应用机器人拉入目标群。

长连接使用 `im.message.receive_v1` 和 `card.action.trigger` 事件。长连接由后端主动建立，因此不需要配置公网 webhook、cpolar 或 ngrok 回调地址。

### 2. 配置环境变量

在 `backend/.env` 中填写密钥；不要把真实值提交到 Git：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_LONGCONN=1

# 企划归档同步（可选）
FEISHU_BITABLE_APP_TOKEN=
FEISHU_BITABLE_TABLE_ID=

# Aily/后端任务完成后的通知群（可选）
FEISHU_NOTIFY_CHAT_ID=
FRONTEND_BASE_URL=http://localhost:5173
```

使用飞书真实洞察数据时，还需要配置 `BASE_PROVIDER_MODE=feishu`、`FEISHU_BASE_APP_TOKEN`、`FEISHU_DATA_TABLE_ID` 和相应的摘要/竞品表变量；详见 [飞书 Base 字段映射](../../docs/guides/feishu-base-mapping.md)。

### 3. 启动后端

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

`app.main` 启动时会幂等拉起飞书长连接。建议单进程、单 worker 运行，不要使用 `--reload` 或多个 worker，否则可能产生多个竞争连接。

### 4. 群内使用

在群里 @机器人，例如：

```text
帮我做一个 2027 夏季户外小风扇企划，价格带 39-99 元，联名三丽鸥
```

流程为：

```text
一句话需求
→ 缺少品类/IP 时填写 Card 2.0 表单
→ 五看洞察
→ 三张机会方向卡
→ 人工点选方向
→ 企划卡与概念图
→ 归档、同步多维表格
→ 生成在线完整企划文档（含概念图）并回传报告卡
```

IP 下拉选项来自资源库；已指定的 IP 会被锁定到所有机会方向和概念图 prompt。任何阶段失败都会回传明确错误，不会伪装成成功。

## 与后端 API 的关系

前端工作室使用 `/api/v1/plans` 和 `actions/*` 原子动作接口；飞书群机器人在 `group_bot.py` 内调用同一套 planning service/pipeline，不再调用旧的 `run_review()` 评审事件流。

归档后的企划可以在前端或 `POST /api/v1/plans/{plan_id}/review` 进行只读复盘；归档任务不可继续改稿。

## 排障

- 群里无响应：检查 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_LONGCONN`，以及应用是否已加入群。
- 长连接重复或不稳定：确认只有一个 uvicorn 进程和一个 worker。
- 卡片回调失败：确认使用 Card schema 2.0、表单组件 `name` 唯一且非空。
- 归档未写入多维表格：检查 `FEISHU_BITABLE_APP_TOKEN`、`FEISHU_BITABLE_TABLE_ID` 和对应权限；同步失败不影响本地归档状态。
- Aily 没有结果通知：检查 `FEISHU_NOTIFY_CHAT_ID`；Aily 入口仍可使用 `/api/v1/plans/aily-create`，但任务由后端后台执行。

## 运行边界

- 长连接必须在单进程中运行；回调线程只做解析和分发，洞察、出图、归档等重任务交给后台线程池。
- 密钥只从环境变量读取，日志不打印 Secret、Token 或完整原始记录。
- 生产环境按 `AGENTS.md` 启用 Strict Real Mode，禁止 Mock/fixture 演示数据静默回退。

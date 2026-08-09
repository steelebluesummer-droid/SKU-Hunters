# 飞书对接模块使用说明

## 功能

- 飞书群里 @机器人 说「评审 XXX」，自动启动一轮 AI 委员会评审
- 7 个委员用不同颜色的卡片发言，模拟圆桌讨论
- 最后输出评审结论卡片，带「通过/否决」按钮，真人拍板
- 目前趋势官已接入，其他委员为占位内容，后续补充

## 文件结构

```
feishu/
├── __init__.py      # 模块入口
├── config.py        # 配置（从环境变量读取）
├── auth.py          # Token 管理（自动缓存刷新）
├── cards.py         # 7个委员的卡片模板
├── bot.py           # 消息发送封装
├── handler.py       # 消息处理 + 评审流程调度
└── webhook.py       # FastAPI 路由
```

## 快速开始

### 1. 创建飞书应用

1. 访问 https://open.feishu.cn → 开发者后台
2. 创建企业自建应用，名字「SKU 委员会」
3. 添加应用能力 → 开启「机器人」
4. 权限管理 → 开通：
   - `im:message`（发送消息）
   - `im:message.receive_v1`（接收消息）
5. 事件与回调 → 配置请求地址：
   - `https://你的域名/feishu/webhook`
   - 本地开发用内网穿透（cpolar/ngrok）
   - 订阅事件：`接收消息 v2.0`
6. 拿到 App ID 和 App Secret

### 2. 配置环境变量

在 `.env` 文件中添加：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxx  # 事件与回调页面的 Verification Token
FEISHU_ENCRYPT_KEY=xxxxxxxx         # 加密 Key（如果开启了加密）
```

### 3. 集成到 FastAPI

在你的主应用文件中添加：

```python
from fastapi import FastAPI
from feishu import FeishuConfig
from feishu.webhook import create_feishu_router

app = FastAPI()

# 注册飞书路由
config = FeishuConfig.from_env()
app.include_router(create_feishu_router(config), prefix="/feishu")
```

### 4. 把机器人拉进群

1. 在飞书群里 → 群设置 → 群机器人 → 添加机器人
2. 搜索你创建的「SKU 委员会」应用，添加进去

### 5. 测试

在群里 @SKU委员会 说：
```
评审 解压玩具
```

应该会看到：
1. 一张「评审开始」卡片
2. 然后依次出现 7 个委员的发言卡片（趋势官是真实逻辑，其他是占位）
3. 最后一张「评审结论」卡片，带通过/否决按钮

## 接入你的 Agent

### 接入趋势官（已预留接口）

在 `handler.py` 的 `_run_review` 方法中，趋势官部分：

```python
# 已经写好了，只要你的 TrendAgent 有 analyze 方法，返回 dict
from agents.trend_agent import TrendAgent
agent = TrendAgent()
result = agent.analyze(topic)
# result 格式：
# {
#     "content": "趋势分析内容...",
#     "evidence": ["来源1", "来源2", ...]
# }
```

### 接入其他 Agent

把 `handler.py` 中对应的占位代码替换成真实 Agent 调用即可。每个 Agent 的返回格式统一为：

```python
{
    "content": "分析内容（支持 markdown）",
    "evidence": ["证据1", "证据2", ...],  # 可选
    "score": 85.5,  # 可选，商业官用
}
```

## 后续替换为 LangGraph

等你的 LangGraph 编排写好了，把 `handler.py` 里的 `_run_review` 方法整个替换掉就行：

```python
async def _run_review(self, chat_id: str, topic: str):
    # 原来的串行代码替换成 LangGraph 调用
    from your_langgraph_app import run_review
    async for event in run_review(topic):
        # event: {"role": "trend", "content": "...", "evidence": [...]}
        self.bot.send_committee_report(
            chat_id=chat_id,
            role=event["role"],
            content=event["content"],
            evidence=event.get("evidence"),
            score=event.get("score"),
        )
```

## 本地开发调试

### 内网穿透（让飞书能调通你本地的接口）

推荐用 cpolar 或 ngrok：

```bash
# 假设你的 FastAPI 跑在 8000 端口
cpolar http 8000
# 得到一个公网地址，比如 https://abc.cpolar.cn
# 飞书回调地址填：https://abc.cpolar.cn/feishu/webhook
```

### 测试发送消息

不用等飞书回调，直接写个测试脚本：

```python
from feishu import FeishuConfig
from feishu.auth import FeishuAuth
from feishu.bot import FeishuBot

config = FeishuConfig.from_env()
auth = FeishuAuth(config)
bot = FeishuBot(auth)

# 发个测试消息（chat_id 从群链接或 API 获取）
bot.send_text("oc_xxxxxxxxxx", "hello from SKU Hunters!")
```

## 常见问题

**Q: 收不到消息回调？**
- 检查回调地址是否正确（要公网可访问）
- 检查事件订阅是否开启了「接收消息 v2.0」
- 检查机器人是否已经被拉进群

**Q: 发消息失败？**
- 检查 App ID 和 App Secret 是否正确
- 检查权限是否开通了 `im:message`
- 检查机器人是否在群里

**Q: @机器人没反应？**
- 检查消息里是否真的 @ 了机器人（飞书会把 @ 替换成 @_user_1）
- 检查 handler.py 里的正则是否匹配

# 飞书 AI 功能使用指南

本指南说明如何在 SKU Hunters 项目中利用飞书 AI 能力，提升开发效率和产品价值。

## 一、飞书 AI 能力全景

| 能力 | 用途 | 在本项目中的角色 |
|:---|:---|:---|
| **企业豆包（AI 助手）** | 智能问答、内容生成、代码辅助 | Agent 推理引擎、报告生成、方案撰写 |
| **飞书 Aily（智能体平台）** | 可视化创建 AI 业务流程 | 商品委员会工作流编排、审批流程 |
| **多维表格智能体** | 数据驱动的自动化分析 | 商品数据查询、进度同步、实时看板 |
| **妙记（会议纪要）** | 语音转文字 + AI 摘要 | 团队周会记录、需求评审纪要 |
| **飞书知识库** | 企业知识管理 + RAG 检索 | 知识底座：存储商品知识、IP信息、历史数据 |
| **飞书妙搭（低代码）** | 快速搭建业务应用 | 商品立项 Dashboard、数据分析看板 |

## 二、核心功能详解

### 2.1 企业豆包 — Agent 推理引擎

**定位**：作为 AI 商品委员会 7 个 Agent 的核心推理引擎。

**使用方式**：

```python
# 通过飞书开放 API 调用企业豆包
import requests

FEISHU_APP_ID = "your_app_id"
FEISHU_APP_SECRET = "your_app_secret"

def get_tenant_token():
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET
    })
    return resp.json().get("tenant_access_token")

def call_agent_llm(prompt: str, agent_role: str) -> str:
    """调用企业豆包进行 Agent 推理"""
    token = get_tenant_token()
    url = "https://open.feishu.cn/open-apis/ai/llm/completions"
    headers = {"Authorization": f"Bearer {token}"}
    
    system_prompt = f"你是一名{agent_role}，请基于以下信息进行分析..."
    
    resp = requests.post(url, json={
        "prompt": prompt,
        "system_prompt": system_prompt,
        "temperature": 0.3,
        "stream": False
    }, headers=headers)
    return resp.json().get("choices", [{}])[0].get("text", "")
```

**场景示例**：
- 趋势官：调用豆包分析 TikTok 趋势数据，生成趋势报告
- 商业官：调用豆包评估商品机会值，输出五维评分
- 创意官：调用豆包综合多方输入，生成商品创意方案

### 2.2 飞书 Aily — 可视化工作流编排

**定位**：将 AI 商品委员会的协作流程可视化，无需编写复杂编排代码。

**使用步骤**：

1. **创建智能体**：在飞书 Aily 平台创建一个新的智能体
2. **定义流程**：拖拽式搭建商品委员会工作流
   ```
   [趋势数据输入] → [趋势官分析] → [用户官分析] → [IP官分析]
        ↓
   [创意官综合] → [商业官评估] → [全球化官评估]
        ↓
   [Decision Engine] → [立项建议书输出]
   ```
3. **配置 Agent**：每个节点绑定企业豆包，配置角色提示词
4. **发布使用**：将智能体发布到飞书工作台，商品经理可直接使用

**价值**：降低技术门槛，商品经理可直接在工作流中调整 Agent 参数。

### 2.3 多维表格智能体 — 商品数据看板

**定位**：实时商品数据查询与进度同步。

**使用方式**：

1. 创建"商品立项"多维表格，包含字段：
   - 商品名称、品类、目标市场、机会值评分
   - 推荐等级、状态（待评审/已通过/已打样/已上市）
   - 各 Agent 分析摘要、证据链接
2. 配置智能体：当状态变更时，自动触发通知
3. 进群协作：将多维表格智能体拉入项目群，可通过自然语言查询
   - "帮我查一下当前机会值80分以上的商品有哪些"
   - "泰国市场最近评审通过了几款商品"

### 2.4 飞书知识库 — RAG 知识底座

**定位**：存储历史商品数据、IP 信息、市场报告，供 Agent 检索。

**使用方式**：

```python
# 通过飞书开放 API 搜索知识库
def search_knowledge_base(query: str, page_size: int = 10) -> list:
    """搜索飞书知识库"""
    token = get_tenant_token()
    url = "https://open.feishu.cn/open-apis/wiki/v2/search"
    headers = {"Authorization": f"Bearer {token}"}
    
    resp = requests.post(url, json={
        "query": query,
        "page_size": page_size
    }, headers=headers)
    return resp.json().get("items", [])
```

**知识库内容建议**：
- 名创优品历史爆品案例库
- IP 合作信息与授权库
- 各国市场消费偏好报告
- 商品开发 SOP 文档

## 三、开发环境配置

### 3.1 获取飞书开发者凭证

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用 → 获取 App ID 和 App Secret
3. 开启所需权限：
   - 智能助手：`ai.llm`
   - 知识库：`wiki:wiki`
   - 多维表格：`bitable:app`
   - 云文档：`docx:document`

### 3.2 环境变量配置

```bash
# .env 文件
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_KNOWLEDGE_BASE_ID=xxxxx
```

## 四、在比赛方案中的展示建议

### 方案文档中需体现的内容

| 飞书能力 | 展示方式 | 建议截图/演示 |
|:---|:---|:---|
| 企业豆包 | Agent 推理过程截图 | 展示 Agent 调用豆包生成分析的过程 |
| Aily 工作流 | 商品委员会工作流拓扑图 | 拖拽式流程编排截图 |
| 多维表格 | 商品立项看板 | 多维表格展示商品状态流转 |
| 知识库 | RAG 检索效果 | 知识库中存储的商品数据截图 |

### 加分项

- 演示视频中包含飞书 AI 功能实际操作
- 展示多维表格智能体与群聊的交互过程
- 展示 Aily 工作流编排的灵活性和可调整性
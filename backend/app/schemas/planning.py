"""企划工作室 v2 核心数据结构 — 六步企划管线输入输出契约

对应全景设计文档 v2.0 的业务链路：
    ① PlanBrief（约束）→ ② InsightBundle（五看洞察）→ ③ Opportunity[]（3 张方向卡）
    → ④⑤⑥ PlanCard（创意设计 + 商品策略 + 企划卡组装）

全部模型为 pydantic BaseModel，前端只需认 JSON Schema；
素材替换只改 fixtures.py，管线代码不动。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ══════════════════  ① 企划约束  ══════════════════

class PlanBrief(BaseModel):
    """企划约束输入 — 对应名创「年度品类规划 → 企划案」的约束下达"""

    theme: str = Field(..., description="企划主题，如 2027夏季户外生活系列")
    category: str = Field(..., description="品类，如 小风扇")
    market: str = Field(default="中国大陆", description="目标市场")
    audience: str = Field(default="", description="目标人群")
    price_range: list[float] = Field(default=[39, 99], description="价格带 [下限, 上限]（元）")
    cost_limit: float = Field(default=25, description="成本上限（元），商品策略校验回环用")
    ip_strategy: list[str] = Field(default_factory=list, description="IP 策略，如 ['三丽鸥']")
    launch_window: str = Field(default="", description="上新窗口")
    goals: list[str] = Field(default_factory=list, description="商业目标")
    mode: str = Field(default="fixture", description="数据模式：fixture（默认冻结数据）| live（真实 LLM + 即梦）")


# ══════════════════  ② 五看洞察  ══════════════════

# ── 趋势洞察 ──

class TrendSignal(BaseModel):
    """单条趋势信号"""
    name: str
    metric: str
    period: str
    domains: list[str] = Field(default_factory=list)
    opportunity: str = ""


class HeatCurveSeries(BaseModel):
    """热度曲线单条序列"""
    name: str
    data: list[float]


class HeatCurve(BaseModel):
    """多序列热度曲线"""
    weeks: list[str]
    series: list[HeatCurveSeries]


class TrendRadar(BaseModel):
    """趋势机会雷达 — 趋势洞察 Agent 产物"""
    process_log: list[str] = Field(default_factory=list, description="渐进过程日志")
    signals: list[TrendSignal] = Field(default_factory=list)
    heat_curve: HeatCurve | None = None
    hot_words: list[str] = Field(default_factory=list)


# ── 用户洞察 ──

class PainPoint(BaseModel):
    """用户痛点"""
    text: str
    count: int = 0


class SceneDist(BaseModel):
    """使用场景分布"""
    name: str
    value: int = 0


class UserQuote(BaseModel):
    """用户原句引用"""
    text: str
    source: str = ""


class ConsumerVoice(BaseModel):
    """消费者声音 — 用户洞察 Agent 产物"""
    process_log: list[str] = Field(default_factory=list)
    pain_points: list[PainPoint] = Field(default_factory=list)
    scenes: list[SceneDist] = Field(default_factory=list)
    quotes: list[UserQuote] = Field(default_factory=list)
    summary: str = ""


# ── 竞品分析 ──

class CompetitorProduct(BaseModel):
    """竞品数据点"""
    name: str
    price: float
    design: float = Field(ge=0, le=10, description="设计感评分 0-10")


class GapZone(BaseModel):
    """机会空白区"""
    x: list[float] = Field(description="价格区间 [下, 上]")
    y: list[float] = Field(description="设计感区间 [下, 上]")
    label: str = ""


class PriceBand(BaseModel):
    """价格带分布"""
    band: str
    pct: float


class SellingPoint(BaseModel):
    """卖点关键词频次"""
    word: str
    count: int = 0


class CompetitiveMap(BaseModel):
    """竞品矩阵 — 竞品分析 Agent 产物"""
    process_log: list[str] = Field(default_factory=list)
    products: list[CompetitorProduct] = Field(default_factory=list)
    gap_zone: GapZone | None = None
    price_bands: list[PriceBand] = Field(default_factory=list)
    selling_points: list[SellingPoint] = Field(default_factory=list)


# ── 名创内部 ──

class HitProduct(BaseModel):
    """历史爆品特征"""
    name: str
    index: float = Field(ge=0, le=100, description="爆品指数 0-100")
    factors: list[str] = Field(default_factory=list)
    note: str = ""


class IPPoolItem(BaseModel):
    """IP 资源池条目"""
    name: str
    status: str = ""       # 合作中 | 洽谈中
    heat: str = ""         # ↑ 上升 | → 稳定
    fit: list[str] = Field(default_factory=list)


class InsightBase(BaseModel):
    """名创内部 Insight Base — 策展数据（非 Agent 实时搜）"""
    hit_products: list[HitProduct] = Field(default_factory=list)
    ip_pool: list[IPPoolItem] = Field(default_factory=list)
    design_language: list[str] = Field(default_factory=list)


# ── 流行元素板 ──

class TrendColor(BaseModel):
    """跨品类流行色"""
    name: str
    hex: str = ""
    source: str = ""


class TrendPattern(BaseModel):
    """跨品类流行花纹/图案"""
    name: str
    source: str = ""
    note: str = ""


class TrendShape(BaseModel):
    """跨品类流行形态"""
    name: str
    source: str = ""
    note: str = ""


class TrendExpression(BaseModel):
    """表情语言趋势"""
    name: str
    emoji: str = ""
    note: str = ""


class TrendGallery(BaseModel):
    """流行元素板 — 策展数据（非 Agent 实时搜）"""
    colors: list[TrendColor] = Field(default_factory=list)
    patterns: list[TrendPattern] = Field(default_factory=list)
    shapes: list[TrendShape] = Field(default_factory=list)
    expressions: list[TrendExpression] = Field(default_factory=list)


# ── 洞察汇总 ──

class InsightBundle(BaseModel):
    """五看洞察汇总 — 前端洞察驾驶舱渲染的完整数据"""
    trend_radar: TrendRadar = Field(default_factory=TrendRadar)
    consumer_voice: ConsumerVoice = Field(default_factory=ConsumerVoice)
    competitive_map: CompetitiveMap = Field(default_factory=CompetitiveMap)
    insight_base: InsightBase = Field(default_factory=InsightBase)
    trend_gallery: TrendGallery = Field(default_factory=TrendGallery)


# ══════════════════  ③ 机会生成  ══════════════════

class EvidenceLink(BaseModel):
    """方向卡依据标签 — 可回溯到洞察模块"""
    source: str = Field(validation_alias="from", description="来源模块：趋势洞察 / 用户洞察 / 竞品分析 / 名创内部 / 流行元素")
    text: str = Field(description="依据摘要")


class Opportunity(BaseModel):
    """单张方向卡"""
    id: str = Field(..., description="唯一标识")
    emoji: str = ""
    title: str = ""
    direction: str = ""          # 方向标签，如 IP收藏风
    pitch: str = ""              # 一句话卖点
    price_band: str = ""         # 建议价格带，如 59-79 元
    keywords: list[str] = Field(default_factory=list)
    evidence: list[EvidenceLink] = Field(default_factory=list, description="四方依据链")


# ══════════════════  ④⑤⑥ 新品企划卡  ══════════════════

class PricingInfo(BaseModel):
    """定价信息"""
    price: str = ""              # 如 "59 元"
    reason: str = ""             # 定价理由


class ScheduleItem(BaseModel):
    """上新节奏节点"""
    time: str = ""               # 如 "2027.02"
    action: str = ""


class CostCheck(BaseModel):
    """成本校验结果"""
    passed: bool = False
    price: float | None = None
    cost_limit: float | None = None
    margin: float | None = None
    reason: str = ""


class PlanCard(BaseModel):
    """新品企划卡 — 六步管线最终输出

    包含创意设计（概念/视觉/功能）+ 商品策略（定价/节奏/验证）+ 成本校验。
    以结构化模板组装，非 LLM 自由发挥。
    """
    name: str = ""
    concept_image: str = ""      # 即梦文生图 URL 或本地路径
    concept: str = ""            # 一句话概念
    design_language: str = ""    # 设计语言描述
    keywords: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    fusion: str = ""             # 跨品类融合说明
    pricing: PricingInfo = Field(default_factory=PricingInfo)
    schedule: list[ScheduleItem] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)  # 上市验证指标
    process_log: list[str] = Field(default_factory=list)  # 创意/商品策略思考过程（导师专项：呈现推理过程）
    cost_check: CostCheck | None = None
    opportunity_id: str = ""
    source: str = "fixture"      # fixture | live
    source_plan_id: str = ""     # 复用来源：基于哪张归档企划卡做的企划（plan_id），空为原创


# ══════════════════  数据看板  ══════════════════

class CategoryRank(BaseModel):
    """品类热度排行"""
    name: str
    heat: float = Field(default=0, ge=0, le=100)


class HotProductRank(BaseModel):
    """热销商品榜"""
    rank: int
    name: str
    price: float
    point: str = ""
    sales: float = 0


class VoiceTrend(BaseModel):
    """社媒声量趋势"""
    weeks: list[str] = Field(default_factory=list)
    xhs: list[float] = Field(default_factory=list)      # 小红书
    douyin: list[float] = Field(default_factory=list)    # 抖音


class DataBoard(BaseModel):
    """数据看板 — 大盘全貌"""
    category_rank: list[CategoryRank] = Field(default_factory=list)
    hot_products: list[HotProductRank] = Field(default_factory=list)
    voice_trend: VoiceTrend | None = None


# ══════════════════  任务列表  ══════════════════

class PlanSummary(BaseModel):
    """企划任务列表项（前端任务中心卡片用）"""
    plan_id: str
    theme: str = ""
    category: str = ""
    audience: str = ""
    status: str = ""             # brief_locked → … → archived
    created_at: str = ""

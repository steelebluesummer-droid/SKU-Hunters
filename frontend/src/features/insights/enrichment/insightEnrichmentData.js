/* ============================================================
 * SKU Hunters · AI Insight Enrichment Layer（小风扇品类）
 *
 * 定位：模拟「LLM 洞察增强服务」的结构化输出，不是页面文案层。
 * 所有字段面向未来 LLM structured output 设计——生产环境由
 * 洞察增强 Agent 按同一 schema 实时填充，前端组件无需改动。
 *
 * 内容来源：《风扇市场三平台数据趋势分析（2025-04 ~ 2026-08）》
 * （飞书 Bitable 三平台采集，1007 条去重样本），仅做事实提炼
 * 与推理结论结构化，不引入报告外数据。
 *
 * schema 约定：
 * - 所有数值/枚举字段可直接被 JSON schema 校验
 * - 不含任何排版样式、标题文案（标题由展示层决定）
 * - evidence / reasoning 字段保证「AI 判断可解释、可追问」
 * ============================================================ */

export const FAN_ENRICHMENT = {
  // 匹配的品类名（resolver 做包含匹配：小风扇 / 风扇 均命中）
  category: '风扇',

  // ── 1. 品类趋势总览 ─────────────────────────────────────
  trendSummary: {
    // 一句话市场判断
    verdict: '风扇市场正从「降温工具」向「便携化 + 情绪价值 + 场景细分」迁移',
    metrics: [
      { label: '大盘月同比增速', value: '+60%~95%', direction: 'up', note: '2026年1-8月所有月份同比均超+60%' },
      { label: '最强增长引擎', value: '复古风扇 +132%', direction: 'up', note: '颜值经济 + 复古回潮双重驱动' },
      { label: '三平台样本量', value: '1007 条', direction: 'flat', note: '小红书33% · 抖音36% · 淘宝31%' },
    ],
    keywords: ['复古风扇', '无叶风扇', '便携小风扇', '户外露营', 'AI智能'],
  },

  // ── 2. 热门话题聚类（源：报告热门话题 TOP20，AI 按需求类型聚类）──
  topicClusters: [
    {
      type: '功能需求',
      topics: [
        { name: '无叶风扇', count: 56 },
        { name: '便携小风扇', count: 43 },
        { name: 'AI智能风扇', count: 41 },
        { name: 'USB小风扇', count: 34 },
        { name: '空气循环扇', count: 33 },
      ],
    },
    {
      type: '场景需求',
      topics: [
        { name: '桌面风扇', count: 49 },
        { name: '空调房闷热', count: 39 },
        { name: '户外露营风扇', count: 37 },
        { name: '夏日降温', count: 22 },
      ],
    },
    {
      type: '情绪与内容',
      topics: [
        { name: '复古风扇', count: 36 },
        { name: '咱家风扇坏了', count: 42 },
        { name: '夹子音', count: 37 },
        { name: '风扇测评', count: 35 },
      ],
    },
  ],

  // ── 3. 子品类趋势（选赛道依据：样本量 × 同比增速）─────────
  // momentum: surge(爆发) | rising(上升) | stable(稳定大盘) | emerging(新兴)
  subCategoryTrends: [
    { name: '复古风扇', records: 32, growthPct: 132.0, momentum: 'surge', note: '同比增速第1' },
    { name: '户外/露营风扇', records: 38, growthPct: 80.5, momentum: 'surge', note: '露营经济 + 便携需求' },
    { name: '无叶风扇', records: 103, growthPct: 74.1, momentum: 'rising', note: '样本量第1的大盘品类' },
    { name: '落地扇', records: 69, growthPct: 72.5, momentum: 'rising', note: '家庭场景基本盘' },
    { name: '夹子/挂脖风扇', records: 45, growthPct: 68.3, momentum: 'rising', note: '办公/通勤场景增长强劲' },
    { name: '桌面风扇', records: 76, growthPct: null, momentum: 'stable', note: '样本量第2，桌搭场景刚需' },
    { name: 'AI智能风扇', records: 60, growthPct: 20.0, momentum: 'emerging', note: '结构性新增量' },
  ],

  // ── 4. 季节窗口（零售供应链节奏 → 上市决策）──────────────
  seasonPlan: {
    cycle: [
      { phase: '趋势萌芽', months: '1-3月', action: '完成设计定稿与打样（淡季同比仍+80%以上，智能化品类逆季增长）' },
      { phase: '需求爬坡', months: '4月', action: '小批量首发，测试转化' },
      { phase: '销售高峰', months: '5-8月', action: '营销爆发期，占全年热度65%，卡位618大促' },
      { phase: '淡季延续', months: '9-10月', action: '工厂直播 + 复古风测评延续流量' },
    ],
    launchSuggestion: '建议次年4月完成首发，卡住618预热窗口',
  },

  // ── 5. AI 机会判断（收口：为什么值得做）──────────────────
  opportunityJudgment: {
    summary: '「高颜值复古桌面风扇」存在设计溢价机会',
    confidence: 87,
    // 判断依据（页面可直接展示，回答评委“为什么”）
    evidence: [
      '复古风扇话题同比 +132%，颜值经济 + 复古回潮双重驱动',
      '桌面风扇样本量 76 条，稳居子品类 TOP2，桌搭场景是稳定刚需',
      '30-54 元中端价格带同比 +90%，用户愿意为升级付费',
      '夹子/挂脖风扇同比 +68%，办公/通勤场景需求持续扩张',
    ],
    // 推理链：信号 → 解读 → 机会（核心差异化：可解释的决策过程）
    reasoning: [
      {
        signal: '复古风扇同比 +132%',
        interpretation: '购买动机从功能转向情绪价值与颜值',
        opportunity: '复古/ins 设计语言可支撑设计溢价',
      },
      {
        signal: '桌面风扇稳居子品类 TOP2',
        interpretation: '办公桌场景是稳定刚需场景',
        opportunity: '桌面风扇适合做「桌搭美学」品类',
      },
      {
        signal: '30-54 元价格带同比 +90%',
        interpretation: '中端消费升级真实发生，脱离30元以下价格战',
        opportunity: '定价 39.9-49.9 元卡位中端真增长带',
      },
    ],
  },
};

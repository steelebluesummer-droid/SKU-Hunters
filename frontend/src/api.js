const BASE = '/api/v1';

async function request(url, opts = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data.detail?.error, ...data };
  return data;
}

// ── 企划工作室链路（v2 主链路） ─────────────────────────────
// 数据策略「真管线、冻数据」：启动时从后端拉取冻结数据覆盖本地 mock，
// 后端不在线则静默保持本地数据（组件零改动）。素材替换只改后端 fixtures.py。

import * as local from './mock/fanData';

// 用远端数据原地覆盖本地 fixture 对象
function override(target, source) {
  if (!source) return;
  if (Array.isArray(target)) {
    target.splice(0, target.length, ...source);
  } else {
    Object.assign(target, source);
  }
}

export async function bootstrapRemoteFixtures(timeoutMs = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const s = controller.signal;
    const opt = { signal: s };
    const [plan, insights, insightBase, trendGallery, dataBoard, opps] = await Promise.all([
      fetch(BASE + '/plans/demo', opt).then(r => r.ok ? r.json() : Promise.reject(r.status)),
      fetch(BASE + '/plans/demo/insights', opt).then(r => r.ok ? r.json() : Promise.reject(r.status)),
      fetch(BASE + '/insight-base', opt).then(r => r.ok ? r.json() : Promise.reject(r.status)),
      fetch(BASE + '/trend-gallery', opt).then(r => r.ok ? r.json() : Promise.reject(r.status)),
      fetch(BASE + '/data-board', opt).then(r => r.ok ? r.json() : Promise.reject(r.status)),
      fetch(BASE + '/plans/demo/opportunities', opt).then(r => r.ok ? r.json() : Promise.reject(r.status)),
    ]);
    override(local.DEMO_BRIEF, plan.brief);
    override(local.TREND_RADAR, insights.trendRadar);
    override(local.CONSUMER_VOICE, insights.consumerVoice);
    override(local.COMPETITIVE_MAP, insights.competitiveMap);
    override(local.INSIGHT_BASE, insightBase);
    override(local.TREND_GALLERY, trendGallery);
    override(local.DATA_BOARD, dataBoard);
    override(local.OPPORTUNITIES, opps.opportunities);
    console.info('[SKU Hunters] 数据源：后端 API（冻结 fixture）');
  } catch {
    console.info('[SKU Hunters] 后端不在线，使用本地 mock 数据');
  } finally {
    clearTimeout(timer);
  }
}

// 按具体任务拉取洞察：覆盖本地 mock 为该任务品类的真实五看数据
//（后端 get_insights 按 plan 的 category 解析，见 pipeline._resolve_insight_bundle）
export async function loadInsightsForPlan(planId) {
  try {
    const insights = await request(`/plans/${planId}/insights`);
    override(local.TREND_RADAR, insights.trendRadar);
    override(local.CONSUMER_VOICE, insights.consumerVoice);
    override(local.COMPETITIVE_MAP, insights.competitiveMap);
    override(local.INSIGHT_BASE, insights.insightBase);
    override(local.TREND_GALLERY, insights.trendGallery);
    // 机会卡也按该任务拉取（非 demo 任务不再是固定小风扇三张）
    const opps = await request(`/plans/${planId}/opportunities`);
    override(local.OPPORTUNITIES, opps.opportunities || []);
    console.info(`[SKU Hunters] 洞察+机会数据源：任务 ${planId}`);
    return insights;
  } catch {
    console.info('[SKU Hunters] 该任务洞察加载失败，保留现有数据');
    return null;
  }
}

// 选定方向 → 后端生成企划卡（含成本校验、概念图 URL）；失败返回 null 走本地模板
export async function generatePlanCard(opportunityId, planId = 'demo') {
  try {
    const data = await request(`/plans/${planId}/plan-card`, {
      method: 'POST',
      body: { opportunity_id: opportunityId },
    });
    return data.plan_card;
  } catch {
    return null;
  }
}

// 改稿沟通 → 后端 LLM 作答；失败返回 null 走本地固定回执
export async function revisePlan(message, planId = 'demo') {
  try {
    const data = await request(`/plans/${planId}/revise`, {
      method: 'POST',
      body: { message },
    });
    return data.reply;
  } catch {
    return null;
  }
}

// 新建企划（NewPlan 表单 → 后端创建真实任务，返回 plan_id）
export async function createPlan(brief) {
  try {
    return await request('/plans', { method: 'POST', body: { brief } });
  } catch (e) {
    console.error('创建企划失败', e);
    return null;
  }
}

// 任务列表 → 后端真实状态；失败返回 null 走本地 mock
export async function listPlans() {
  try {
    const data = await request('/plans');
    return data.plans;
  } catch {
    return null;
  }
}

// 任务详情（含进度与已选方向）；失败返回 null
export async function getPlan(planId = 'demo') {
  try {
    return await request(`/plans/${planId}`);
  } catch {
    return null;
  }
}

// 归档企划案；失败返回 null（前端按本地状态兜底）
export async function archivePlan(planId = 'demo') {
  try {
    const data = await request(`/plans/${planId}/archive`, { method: 'POST', body: {} });
    return data.status;
  } catch {
    return null;
  }
}

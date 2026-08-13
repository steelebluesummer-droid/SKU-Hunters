const BASE = '/api/v1';

/**
 * 统一请求封装：返回解析后的 JSON；非 2xx 抛出结构化错误。
 * 数据契约统一为 camelCase（与后端 loader / fixtures 对齐）。
 * 本模块只做纯 fetch，不改写任何 mock 常量（消除「原地覆盖 module 常量」反模式）。
 */
async function request(url, opts = {}) {
  let res;
  try {
    res = await fetch(BASE + url, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    // 网络层失败（后端不在线 / 断网）：抛出统一错误，由调用方决定是否走演示数据
    const err = new Error('网络请求失败');
    err.code = 'NETWORK_ERROR';
    err.cause = e;
    throw err;
  }

  let data;
  try {
    data = await res.json();
  } catch {
    data = {};
  }

  if (!res.ok) {
    const err = new Error(data?.detail?.error?.message || `请求失败（${res.status}）`);
    err.status = res.status;
    err.code = data?.detail?.error?.code || 'HTTP_ERROR';
    err.detail = data?.detail;
    throw err;
  }
  return data;
}

// ── 企划工作室链路（纯函数，返回 Promise<data>，失败抛出，不做静默 mock 回退）──

/** 新建企划 → 返回 { plan_id, status } */
export async function createPlan(brief) {
  const data = await request('/plans', { method: 'POST', body: { brief } });
  return data;
}

/** 任务列表 → 返回 { plans: [...] } */
export async function listPlans() {
  return request('/plans');
}

/** 任务详情（含 brief / status / plan_card） */
export async function getPlan(planId) {
  return request(`/plans/${planId}`);
}

/** 五看洞察（camelCase 契约） */
export async function getInsights(planId) {
  return request(`/plans/${planId}/insights`);
}

/** 机会生成（3 张方向卡 + processLog） */
export async function getOpportunities(planId) {
  return request(`/plans/${planId}/opportunities`);
}

/** 显式推进流程状态（GET 只读不推进；推进走本 POST action） */
export async function advancePlan(planId, to) {
  return request(`/plans/${planId}/advance`, { method: 'POST', body: { to } });
}

/** 选定方向 → 生成企划卡 → 返回 plan_card */
export async function generatePlanCard(opportunityId, planId) {
  const data = await request(`/plans/${planId}/plan-card`, {
    method: 'POST',
    body: { opportunity_id: opportunityId },
  });
  return data.plan_card;
}

/** 改稿沟通 → 返回 reply */
export async function revisePlan(message, planId) {
  const data = await request(`/plans/${planId}/revise`, {
    method: 'POST',
    body: { message },
  });
  return data;
}

/** 归档 → 返回 { status, archived_at } */
export async function archivePlan(planId) {
  return request(`/plans/${planId}/archive`, { method: 'POST', body: {} });
}

/** 名创内部 Insight Base（策展数据独立页） */
export async function getInsightBase(topic = '小风扇') {
  return request(`/insight-base?topic=${encodeURIComponent(topic)}`);
}

/** 流行元素板 Trend Gallery */
export async function getTrendGallery(topic = '小风扇') {
  return request(`/trend-gallery?topic=${encodeURIComponent(topic)}`);
}

/** 数据看板（大盘） */
export async function getDataBoard() {
  return request('/data-board');
}

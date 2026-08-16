/* ============================================================
 * SKU Hunters · 企划链路 API（plans）
 * 原子业务动作 + CRUD。失败 throw，不静默 mock 回退。
 * 对应后端 Stage 5 原子端点：
 *   POST /plans/{id}/actions/generate-insights
 *   POST /plans/{id}/actions/generate-opportunities
 *   POST /plans/{id}/actions/generate-plan-card
 *   POST /plans/{id}/actions/archive
 * ============================================================ */

import { request } from './client';

/** 新建企划 → 返回 { plan_id, status } */
export async function createPlan(brief) {
  return request('/plans', { method: 'POST', body: { brief } });
}

/** 任务列表 → 返回 { plans: [...] } */
export async function listPlans() {
  return request('/plans');
}

/** 任务详情（含 brief / status / plan_card） */
export async function getPlan(planId) {
  return request(`/plans/${planId}`);
}

/** 删除任务 → 204 空响应 */
export async function deletePlan(planId) {
  return request(`/plans/${planId}`, { method: 'DELETE' });
}

/** ② 原子动作：生成五看洞察 → 返回 { status, insights } */
export async function generateInsights(planId) {
  return request(`/plans/${planId}/actions/generate-insights`, { method: 'POST', body: {} });
}

/** ③ 原子动作：生成机会卡 → 返回 { status, opportunities, processLog } */
export async function generateOpportunities(planId) {
  return request(`/plans/${planId}/actions/generate-opportunities`, { method: 'POST', body: {} });
}

/** ④⑤⑥ 原子动作：选定方向生成企划卡 → 返回 { status, plan_card } */
export async function generatePlanCard(opportunityId, planId) {
  return request(`/plans/${planId}/actions/generate-plan-card`, {
    method: 'POST',
    body: { opportunity_id: opportunityId },
  });
}

/** 改稿沟通 → 返回 { reply, message, timestamp } */
export async function revisePlan(message, planId) {
  return request(`/plans/${planId}/revise`, { method: 'POST', body: { message } });
}

export async function revisePreview(message, planId) {
  return request(`/plans/${planId}/revise/preview`, { method: 'POST', body: { message } });
}

export async function reviseApply(planId) {
  return request(`/plans/${planId}/revise/apply`, { method: 'POST', body: {} });
}

export async function reviseCancel(planId) {
  return request(`/plans/${planId}/revise/cancel`, { method: 'POST', body: {} });
}

/** 归档 → 返回 { status, archived_at } */
export async function archivePlan(planId) {
  return request(`/plans/${planId}/actions/archive`, { method: 'POST', body: {} });
}

/** 重新选择机会方向（plan_card_ready → opportunities_ready，清除已选方向与企划产物） */
export async function rechooseOpportunity(planId) {
  return request(`/plans/${planId}/actions/rechoose-opportunity`, { method: 'POST', body: {} });
}

/** 复盘追问（只读）→ 返回 { question, answer } */
export async function reviewPlan(question, planId) {
  return request(`/plans/${planId}/review`, { method: 'POST', body: { question } });
}

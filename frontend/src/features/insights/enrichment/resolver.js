/* ============================================================
 * SKU Hunters · Insight Enrichment Resolver
 *
 * 职责：按品类获取 AI 洞察增强数据（Enrichment Layer）。
 * 当前实现：读取本地 insightEnrichmentData（模拟 LLM 增强服务输出）。
 *
 * 生产替换点：后端上线 /plans/{id}/insights/enrichment 后，
 * 仅需将本函数改为异步调用该接口，返回结构保持一致，
 * InsightCockpit 组件零改动。
 *
 * 返回 null = 该品类暂无增强数据 → 组件回退基础渲染。
 * ============================================================ */

import { FAN_ENRICHMENT } from './insightEnrichmentData';

const ENRICHMENT_TABLE = [FAN_ENRICHMENT];

/** 按品类取 AI 洞察增强数据（包含匹配：如「小风扇」命中「风扇」） */
export function getInsightEnrichment(category) {
  if (!category) return null;
  return ENRICHMENT_TABLE.find((e) => category.includes(e.category)) || null;
}

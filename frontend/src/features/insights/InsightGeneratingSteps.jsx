/* ============================================================
 * SKU Hunters · InsightGeneratingSteps（洞察分析·真实节点进度）
 * 生成洞察为同步请求：后端一次性跑完链路后返回完整 bundle。
 * 前端在等待期间无法获知单节点实时进度，因此这里展示的是
 * 后端 generate_insights 的【真实依赖链】节点，全部如实标注
 * "分析中"——不伪装任一节点已提前完成，不做假进度。
 * 完成后由 InsightCockpit 用后端返回的真实 processLog 呈现。
 * ============================================================ */

import { Spin } from 'antd';

// 后端 generate_insights 真实链路（service.py：飞书读取 → 机会池 → 用户声音 → {竞品‖资产} 并行）
const NODES = [
  { key: 'feishu', label: '读取飞书 Base 采集数据', desc: '实时明细 · 真实飞书数据' },
  { key: 'pool', label: '生成机会池', desc: '信号 → 机会方向' },
  { key: 'voice', label: '用户声音 · 痛点归因', desc: '消费者原声聚类' },
  { key: 'cm', label: '竞品满足矩阵', desc: '竞品 × 用户需求' },
  { key: 'asset', label: '名创内部资产适配', desc: 'IP / 设计语言匹配' },
];

export default function InsightGeneratingSteps() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="正在按真实链路生成洞察"
      style={{
        marginTop: 16,
        padding: '16px 20px',
        borderRadius: 8,
        border: '1px solid var(--color-border)',
        background: 'var(--color-surface-alt)',
        maxWidth: 720,
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: 'var(--color-text-primary)' }}>
        正在生成洞察（真实链路 · 请稍候）
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {NODES.map((n, i) => (
          <div key={n.key} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12 }}>
            <span
              style={{
                width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, color: 'var(--color-text-secondary)',
                background: 'var(--color-bg)', border: '1px solid var(--color-border)',
              }}
            >
              {i + 1}
            </span>
            <span style={{ fontWeight: 600, minWidth: 168 }}>{n.label}</span>
            <span style={{ color: 'var(--color-text-muted)', flex: 1 }}>{n.desc}</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--color-brand-accent)' }}>
              <Spin size="small" />
              分析中
            </span>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 12 }}>
        各节点按后端真实处理流程执行，失败仅报错不会伪造结果。
      </div>
    </div>
  );
}

/* ============================================================
 * SKU Hunters · SourceTag（数据来源标识）
 * 区分两类来源，可叠加：
 *   ① runSource（怎么产生的数据）：live | snapshot | fixture | demo
 *   ② evidenceType（数据来自哪类系统）：local_kb | warehouse | rule | external
 * ============================================================ */

import { Tag } from 'antd';

const RUN_SOURCE_META = {
  live: { label: '实时', color: 'purple' },
  snapshot: { label: '快照', color: 'blue' },
  fixture: { label: '冻结样本', color: 'cyan' },
  demo: { label: '演示兜底', color: 'default' },
};

const EVIDENCE_TYPE_META = {
  local_kb: { label: '名创内部库', color: 'geekblue' },
  warehouse: { label: '数据仓库', color: 'blue' },
  rule: { label: '规则推导', color: 'green' },
  external: { label: '外部社媒', color: 'orange' },
};

/**
 * @param {string} runSource      数据运行来源
 * @param {string} evidenceType   证据类型（可选）
 */
export default function SourceTag({ runSource, evidenceType }) {
  const tags = [];
  if (runSource && RUN_SOURCE_META[runSource]) {
    const m = RUN_SOURCE_META[runSource];
    tags.push(
      <Tag key={`run-${runSource}`} color={m.color} style={{ marginRight: 4 }}>
        {m.label}
      </Tag>
    );
  }
  if (evidenceType && EVIDENCE_TYPE_META[evidenceType]) {
    const m = EVIDENCE_TYPE_META[evidenceType];
    tags.push(
      <Tag key={`ev-${evidenceType}`} color={m.color} style={{ marginRight: 4 }}>
        {m.label}
      </Tag>
    );
  }
  return <span>{tags}</span>;
}

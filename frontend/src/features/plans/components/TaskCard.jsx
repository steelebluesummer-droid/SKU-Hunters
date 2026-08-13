/* ============================================================
 * SKU Hunters · TaskCard（任务卡片，纯展示/事件组件）
 * 数据由 TaskCenter 拉取后传入，不 import fixtures、不发请求。
 * 整块可点击（含键盘 Enter/Space），卡片内部不再嵌套可点击元素。
 * 状态用「文字标签」表达，不依赖左侧颜色条。
 * ============================================================ */

import { Card, Tag, Typography } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import SourceTag from '../../../shared/components/SourceTag';

const { Paragraph } = Typography;

// 后端落盘状态 → 阶段展示（文字 + 颜色，颜色仅作辅助，状态含义由文字承载）
const STATUS_META = {
  brief_locked: { label: '企划约束', color: 'blue' },
  insights_ready: { label: '洞察驾驶舱', color: 'blue' },
  opportunities_ready: { label: '机会生成', color: 'blue' },
  plan_card_ready: { label: '新品企划卡', color: 'blue' },
  archived: { label: '已归档', color: 'default' },
};

/**
 * @param {object} task     任务摘要（plan_id / theme / category / audience / status / created_at / mode）
 * @param {Function} onClick 整卡点击
 */
export default function TaskCard({ task, onClick }) {
  const meta = STATUS_META[task.status] || STATUS_META.brief_locked;
  const isArchived = task.status === 'archived';
  // 数据来源：demo 任务以 plan_id 识别；其余按 mode（后端 list 暂无 mode 时回退 fixture）
  const runSource = task.plan_id === 'demo' ? 'demo' : task.mode || 'fixture';
  const created = (task.created_at || '').slice(0, 10);

  return (
    <Card
      hoverable
      size="small"
      role="button"
      tabIndex={0}
      aria-label={`查看企划：${task.theme || '未命名企划'}`}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      style={{ cursor: 'pointer', height: '100%' }}
    >
      {/* 阶段 + 归档只读标记（文字表达状态，不依赖颜色） */}
      <div style={{ marginBottom: 8 }}>
        <Tag color={meta.color}>{meta.label}</Tag>
        {isArchived ? (
          <Tag icon={<LockOutlined />}>只读</Tag>
        ) : null}
      </div>

      {/* 主题：超长/英文自动换行，超两行截断并悬停显示完整标题 */}
      <Paragraph
        ellipsis={{ rows: 2, tooltip: task.theme || '未命名企划' }}
        style={{ fontWeight: 600, marginBottom: 8, minHeight: 40, wordBreak: 'break-word' }}
      >
        {task.theme || '未命名企划'}
      </Paragraph>

      {/* 品类 + 目标人群 */}
      <div style={{ fontSize: 13, color: '#666', marginBottom: 8, wordBreak: 'break-word' }}>
        {task.category || '未分类'}
        {task.audience ? ` · ${task.audience}` : ''}
      </div>

      {/* 创建时间 + 数据来源 */}
      <div
        style={{
          fontSize: 12,
          color: '#999',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
        }}
      >
        <span>{created || '—'}</span>
        <SourceTag runSource={runSource} />
      </div>
    </Card>
  );
}

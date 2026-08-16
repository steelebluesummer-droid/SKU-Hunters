/* ============================================================
 * SKU Hunters · TaskCard（任务卡片，纯展示/事件组件）
 * 数据由 TaskCenter 拉取后传入，不 import fixtures、不发请求。
 * 整块可点击（含键盘 Enter/Space）；右上角删除按钮 stopPropagation，不触发整卡跳转。
 * 状态用「文字标签 + 左侧彩色竖条」表达，不依赖单一颜色。
 * 卡片「左图右文」：左概念图缩略，右标题 + 品类·人群 + 事实芯片（定价/毛利）+ 日期。
 * ============================================================ */

import { useState } from 'react';
import { Button, Card, Popconfirm, Tag, Typography } from 'antd';
import { DeleteOutlined, LockOutlined, StarOutlined, StarFilled } from '@ant-design/icons';

const { Paragraph } = Typography;

// 收藏任务 plan_id 的本地持久化 key（浏览器 localStorage，刷新保留，不涉及后端）
const FAV_KEY = 'sku_fav_plan_ids';

// 后端落盘状态 → 阶段展示（文字 + 标签色 + 左侧竖条色；颜色仅辅助，状态含义由文字承载）
const STATUS_META = {
  brief_locked: { label: '企划约束', color: 'orange', bar: '#fa8c16' },
  insights_ready: { label: '洞察驾驶舱', color: 'blue', bar: '#1677ff' },
  opportunities_ready: { label: '机会生成', color: 'green', bar: '#52c41a' },
  plan_card_ready: { label: '新品企划卡', color: 'purple', bar: '#722ed1' },
  archived: { label: '已归档', color: 'default', bar: '#d9d9d9' },
};

/**
 * @param {object} task     任务摘要（plan_id / theme / category / audience / status / created_at / mode / concept_image / price / margin）
 * @param {Function} onClick 整卡点击
 * @param {Function} onDelete 删除回调（可选；Popconfirm 二次确认后触发，不冒泡整卡跳转）
 */
export default function TaskCard({ task, onClick, onDelete }) {
  const meta = STATUS_META[task.status] || STATUS_META.brief_locked;
  const isArchived = task.status === 'archived';
  const created = (task.created_at || '').slice(0, 10);

  // 收藏状态：读 localStorage 初始化，点击切换（stopPropagation，不触发整卡跳转）
  const [fav, setFav] = useState(() => {
    try {
      const list = JSON.parse(localStorage.getItem(FAV_KEY) || '[]');
      return Array.isArray(list) && list.includes(task.plan_id);
    } catch {
      return false;
    }
  });

  const toggleFav = (e) => {
    e.stopPropagation();
    try {
      const list = JSON.parse(localStorage.getItem(FAV_KEY) || '[]');
      const next = fav
        ? list.filter((id) => id !== task.plan_id)
        : [...list, task.plan_id];
      localStorage.setItem(FAV_KEY, JSON.stringify(next));
    } catch {
      /* 存储异常静默忽略，不影响界面切换 */
    }
    setFav((v) => !v);
  };

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
      className="task-card"
      style={{ cursor: 'pointer', height: '100%', borderLeft: `4px solid ${meta.bar}` }}
    >
      <div style={{ display: 'flex', gap: 12 }}>
        {/* 左：概念图缩略（未出企划卡显示占位） */}
        <div
          style={{
            width: 120,
            height: 120,
            flexShrink: 0,
            borderRadius: 8,
            overflow: 'hidden',
            background: 'var(--color-surface-alt)',
          }}
        >
          {task.concept_image ? (
            <img
              src={task.concept_image}
              alt={task.theme || '概念图'}
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
          ) : (
            <div
              style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--color-text-muted)',
                fontSize: 11,
                textAlign: 'center',
                padding: 4,
              }}
            >
              未出企划卡
            </div>
          )}
        </div>

        {/* 右：文字信息 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* 阶段 + 归档只读标记（文字表达状态）+ 收藏/删除 */}
          <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
            <Tag color={meta.color} style={{ marginRight: 0 }}>{meta.label}</Tag>
            {isArchived ? (
              <Tag icon={<LockOutlined />} style={{ marginRight: 0 }}>只读</Tag>
            ) : null}
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 2 }}>
              <Button
                type="text"
                size="small"
                aria-label={fav ? `取消收藏：${task.theme || '未命名企划'}` : `收藏：${task.theme || '未命名企划'}`}
                icon={fav ? <StarFilled style={{ color: '#fadb14' }} /> : <StarOutlined />}
                onClick={toggleFav}
              />
              {onDelete ? (
                <Popconfirm
                  title="删除该企划任务？"
                  description="删除后不可恢复"
                  okText="删除"
                  okButtonProps={{ danger: true }}
                  cancelText="取消"
                  onConfirm={(e) => {
                    e?.stopPropagation?.();
                    onDelete(task);
                  }}
                  onCancel={(e) => e?.stopPropagation?.()}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={`删除企划：${task.theme || '未命名企划'}`}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              ) : null}
            </span>
          </div>

          {/* 主题：超长/英文自动换行，超两行截断并悬停显示完整标题 */}
          <Paragraph
            ellipsis={{ rows: 2, tooltip: task.theme || '未命名企划' }}
            style={{ fontWeight: 600, marginBottom: 6, minHeight: 40, fontSize: 14, wordBreak: 'break-word' }}
          >
            {task.theme || '未命名企划'}
          </Paragraph>

          {/* 品类 + 目标人群 */}
          <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginBottom: 6, wordBreak: 'break-word' }}>
            {task.category || '未分类'}
            {task.audience ? ` · ${task.audience}` : ''}
          </div>

          {/* 事实芯片：定价 / 毛利（有值才显示，未出企划卡无） */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
            {task.price ? (
              <Tag color="gold" style={{ fontSize: 11, marginRight: 0 }}>定价 {task.price}</Tag>
            ) : null}
            {task.margin != null ? (
              <Tag color="green" style={{ fontSize: 11, marginRight: 0 }}>毛利 {(task.margin * 100).toFixed(1)}%</Tag>
            ) : null}
          </div>

          {/* 创建时间 */}
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
            <span>{created || '—'}</span>
          </div>
        </div>
      </div>
    </Card>
  );
}

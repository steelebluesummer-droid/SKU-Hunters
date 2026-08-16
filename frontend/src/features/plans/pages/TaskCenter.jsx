/* ============================================================
 * SKU Hunters · TaskCenter（任务中心）
 * 使用 api/plans.js 的 listPlans，明确区分 loading / error / empty / success。
 * 真实接口失败不显示 demo 任务（demo 任务仅在后端真实返回时以 SourceTag 标注）。
 * 左上角下拉切换「按流程分 / 按品类分」：按流程 = 5 个状态阶段各一组；
 * 按品类 = 按 category 各一组（中文名排序）；唯一主 CTA 为「新建企划」。
 * 响应式：375 单列 / 768 两列 / 1440 三列。
 * ============================================================ */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Button, Divider, Empty, message, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { listPlans, deletePlan } from '../../../api/plans';
import TaskCard from '../components/TaskCard';
import PageHeader from '../components/PageHeader';
import StateCard from '../../../shared/components/StateCard';

// 流程分组顺序：按任务状态细分（前 4 个为「进行中」的进程，最后为「已归档」）
const FLOW_GROUPS = [
  { key: 'brief_locked', label: '企划约束' },
  { key: 'insights_ready', label: '洞察驾驶舱' },
  { key: 'opportunities_ready', label: '机会生成' },
  { key: 'plan_card_ready', label: '新品企划卡' },
  { key: 'archived', label: '已归档' },
];

export default function TaskCenter() {
  const nav = useNavigate();
  const [plans, setPlans] = useState(null); // null = 尚未成功加载
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [groupBy, setGroupBy] = useState('flow'); // flow 按流程分 | category 按品类分

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPlans();
      setPlans(Array.isArray(data?.plans) ? data.plans : []);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const active = (plans || []).filter((t) => t.status !== 'archived');
  const archived = (plans || []).filter((t) => t.status === 'archived');

  // 删除任务：真实调后端 DELETE，成功后刷新列表（不做本地假删）
  const onDelete = async (task) => {
    try {
      await deletePlan(task.plan_id);
      message.success(`已删除「${task.theme || '未命名企划'}」`);
      load();
    } catch (e) {
      message.error(`删除失败：${e?.message || '请检查后端服务'}`);
    }
  };

  const newPlanCta = (
    <Button type="primary" icon={<PlusOutlined />} onClick={() => nav('/new')}>
      新建企划
    </Button>
  );

  // 加载中
  if (loading) {
    return (
      <div>
        <PageHeader title="新品企划任务" subtitle="企划约束由商品经理下达，AI 在约束内做有依据的创意" extra={newPlanCta} />
        <StateCard status="loading" />
      </div>
    );
  }

  // 加载失败：显式报错 + 重试（不显示 demo 任务）
  if (error) {
    return (
      <div>
        <PageHeader title="新品企划任务" extra={newPlanCta} />
        <StateCard status="error" onRetry={load} emptyText="任务列表加载失败" />
      </div>
    );
  }

  // 空列表：明确空态 + 保留新建 CTA
  if (!plans || plans.length === 0) {
    return (
      <div>
        <PageHeader title="新品企划任务" subtitle="企划约束由商品经理下达，AI 在约束内做有依据的创意" extra={newPlanCta} />
        <Empty description="暂无企划任务，点击右上角「新建企划」开始" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '48px 0' }} />
      </div>
    );
  }

  // ── 分组数据 ───────────────────────────────────────────
  const flowGroups = FLOW_GROUPS.map((g) => ({
    ...g,
    plans: plans.filter((t) => t.status === g.key),
  }));

  const categories = [...new Set(plans.map((t) => t.category || '未分类'))].sort((a, b) =>
    a.localeCompare(b, 'zh')
  );
  const categoryGroups = categories.map((c) => ({
    key: c,
    label: c,
    plans: plans.filter((t) => (t.category || '未分类') === c),
  }));

  const groups = groupBy === 'flow' ? flowGroups : categoryGroups;
  const summary =
    groupBy === 'flow'
      ? `进行中 ${active.length} · 已归档 ${archived.length}`
      : `共 ${plans.length} 个任务 · ${categories.length} 个品类`;

  const renderGroup = (label, groupPlans) => {
    if (groupPlans.length === 0) return null;
    return (
      <div key={label}>
        <Divider orientation="left" style={{ fontSize: 14, margin: '8px 0 16px' }}>
          {label}
        </Divider>
        <Row gutter={[16, 16]}>
          {groupPlans.map((t) => (
            <Col xs={24} md={12} lg={8} key={t.plan_id}>
              <TaskCard task={t} onClick={() => nav(`/tasks/${t.plan_id}`)} onDelete={onDelete} />
            </Col>
          ))}
        </Row>
      </div>
    );
  };

  return (
    <div>
      <PageHeader title="新品企划任务" extra={newPlanCta} />

      {/* 左上角：分组切换下拉 + 统计摘要 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
        <Select
          value={groupBy}
          onChange={setGroupBy}
          style={{ width: 160 }}
          options={[
            { value: 'flow', label: '按流程分' },
            { value: 'category', label: '按品类分' },
          ]}
        />
        <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>{summary}</span>
      </div>

      {groups.map((g) => renderGroup(g.label, g.plans))}
    </div>
  );
}

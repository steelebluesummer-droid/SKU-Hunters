/* ============================================================
 * SKU Hunters · TaskCenter（任务中心）
 * 使用 api/plans.js 的 listPlans，明确区分 loading / error / empty / success。
 * 真实接口失败不显示 demo 任务（demo 任务仅在后端真实返回时以 SourceTag 标注）。
 * 左上角下拉切换「按流程分 / 按品类分」：按流程 = 5 个状态阶段各一组；
 * 按品类 = 按 category 各一组（中文名排序）；唯一主 CTA 为「新建企划」。
 * 响应式：375 单列 / 768 两列 / 1440 三列。
 * ============================================================ */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Button, Checkbox, Divider, Empty, message, Popconfirm, Select } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { listPlans, deletePlan } from '../../../api/plans';
import { invalidateGetCache } from '../../../api/client';
import TaskCard from '../components/TaskCard';
import PageHeader from '../components/PageHeader';
import StateCard from '../../../shared/components/StateCard';

// flow 视图三段分组：进行中 / 已完成 / 已归档
// 「进行中」= 后台正在跑 + 各中间态 + failed（等待用户推进或已失败）；
// 「已完成」= stage=done 且未归档（异步链路后台跑完，等用户选定方向出企划卡）。
const RUNNING_STATUSES = ['running', 'brief_locked', 'insights_ready', 'opportunities_ready', 'failed'];

// 不可删（批量管理禁选）：仅限后台管线正在执行的任务——
// status=running，或 stage 非空且未到终态（done/failed）。
// 机会卡已就绪（stage=done）、已失败（failed）、归档、以及用户手动推进的旧任务均可删。
const isBackendRunning = (t) =>
  t.status === 'running' || (!!t.stage && !['done', 'failed'].includes(t.stage));

// stage 序号 → 细进度条（1/3 洞察 → 2/3 机会 → 3/3 完成）
const STAGE_ORDER = { insights: 1, opportunities: 2, done: 3 };

export default function TaskCenter() {
  const nav = useNavigate();
  const [plans, setPlans] = useState(null); // null = 尚未成功加载
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [groupBy, setGroupBy] = useState('flow'); // flow 按流程分 | category 按品类分
  const [selectMode, setSelectMode] = useState(false); // 批量管理模式（勾选删除）
  const [selected, setSelected] = useState([]); // 已选 plan_id 列表

  // plansRef 跟踪最新列表：load 依赖保持 []（引用稳定），
  // 避免 plans 变化 → load 重建 → useEffect 重新执行 → 再拉取 的无限循环闪烁
  const plansRef = useRef(null);
  const load = useCallback(async ({ silent = false } = {}) => {
    // silent：已有数据时静默刷新（删除后列表原地更新，不闪白屏 loading 态）
    if (!silent || !plansRef.current) setLoading(true);
    setError(null);
    try {
      const data = await listPlans();
      const next = Array.isArray(data?.plans) ? data.plans : [];
      plansRef.current = next;
      setPlans(next);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 三段分组数据：进行中（中间态+failed）· 已完成（stage=done 未归档）· 已归档
  const running = (plans || []).filter((t) => RUNNING_STATUSES.includes(t.status));
  const done = (plans || []).filter((t) => t.stage === 'done' && t.status !== 'archived');
  const archived = (plans || []).filter((t) => t.status === 'archived');
  const byCreatedDesc = (a, b) => (b.created_at || '').localeCompare(a.created_at || '');

  // 删除任务：真实调后端 DELETE，成功后刷新列表（不做本地假删）
  const onDelete = async (task) => {
    try {
      await deletePlan(task.plan_id);
      invalidateGetCache('/plans'); // 删除后使 GET 缓存失效，确保拉到最新列表
      message.success(`已删除「${task.theme || '未命名企划'}」`);
      load({ silent: true }); // 静默刷新：保留当前列表渲染，不闪 loading
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
        <div style={{ textAlign: 'center', padding: '56px 0' }}>
          <Empty description="暂无企划任务" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginBottom: 24 }} />
          <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => nav('/new')}>
            新建第一个企划
          </Button>
        </div>
      </div>
    );
  }

  // 可勾选任务：仅后台正在执行的任务禁选（防误删跑一半的任务），其余均可删
  const deletable = (plans || []).filter((t) => !isBackendRunning(t));
  const deletableIds = deletable.map((t) => t.plan_id);

  const toggleSelect = (id) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelected([]);
  };

  // 批量删除：逐个调后端 DELETE，统计成功/失败，结束刷新列表
  const onBatchDelete = async () => {
    const ids = selected.filter((id) => deletableIds.includes(id));
    if (ids.length === 0) return;
    let ok = 0;
    let fail = 0;
    for (const id of ids) {
      try {
        await deletePlan(id);
        invalidateGetCache('/plans'); // 批量删除后使 GET 缓存失效
        ok += 1;
      } catch {
        fail += 1;
      }
    }
    exitSelectMode();
    if (fail === 0) {
      message.success(`已删除 ${ok} 个企划任务`);
    } else {
      message.warning(`删除完成：成功 ${ok} 个、失败 ${fail} 个（失败项请检查后端服务）`);
    }
    load({ silent: true }); // 静默刷新：保留当前列表渲染，不闪 loading
  };

  // ── 分组数据 ───────────────────────────────────────────
  // 进行中/已完成均按创建时间倒序（最新在最上）
  const flowGroups = [
    { key: 'running', label: `进行中 · ${running.length}`, plans: [...running].sort(byCreatedDesc) },
    { key: 'done', label: `已完成 · ${done.length}`, plans: [...done].sort(byCreatedDesc) },
    { key: 'archived', label: `已归档 · ${archived.length}`, plans: [...archived].sort(byCreatedDesc) },
  ].filter((g) => g.plans.length > 0);

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
      ? `总 ${plans.length} · 进行中 ${running.length} · 完成 ${done.length} · 已归档 ${archived.length}`
      : `共 ${plans.length} 个任务 · ${categories.length} 个品类`;

  const renderGroup = (label, groupPlans) => {
    if (groupPlans.length === 0) return null;
    return (
      <div key={label}>
        <Divider orientation="left" style={{ fontSize: 14, margin: '8px 0 16px' }}>
          {label}
        </Divider>
        <Row gutter={[16, 16]}>
          {groupPlans.map((t) => {
            // 批量模式：卡片不跳详情（点击卡片即切换勾选）；运行中卡片禁选
            const selectable = deletableIds.includes(t.plan_id);
            const checked = selected.includes(t.plan_id);
            const card = (
              <TaskCard
                task={t}
                onClick={selectMode ? undefined : () => nav(`/tasks/${t.plan_id}`)}
                onDelete={selectMode ? undefined : onDelete}
                style={selectMode && checked ? { border: '2px solid var(--color-action-primary)', borderRadius: 8 } : undefined}
              />
            );
            if (!selectMode) return <Col xs={24} md={12} lg={8} key={t.plan_id}>{card}</Col>;
            return (
              <Col xs={24} md={12} lg={8} key={t.plan_id}>
                <div
                  style={{
                    position: 'relative',
                    cursor: selectable ? 'pointer' : 'not-allowed',
                    opacity: selectable ? 1 : 0.35,
                  }}
                  onClick={() => selectable && toggleSelect(t.plan_id)}
                >
                  {card}
                  <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 2 }}>
                    <Checkbox
                      disabled={!selectable}
                      checked={checked}
                      onChange={() => toggleSelect(t.plan_id)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`选择：${t.theme || '未命名企划'}`}
                    />
                  </div>
                </div>
              </Col>
            );
          })}
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
        {!selectMode ? (
          <Button
            size="small"
            style={{ marginLeft: 'auto' }}
            disabled={deletable.length === 0}
            onClick={() => setSelectMode(true)}
          >
            批量管理
          </Button>
        ) : (
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            <Checkbox
              checked={selected.length > 0 && selected.length === deletableIds.length}
              indeterminate={selected.length > 0 && selected.length < deletableIds.length}
              onChange={(e) => setSelected(e.target.checked ? [...deletableIds] : [])}
            >
              全选
            </Checkbox>
            <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>已选 {selected.length} 项</span>
            <Popconfirm
              title={`删除选中的 ${selected.length} 个企划任务？`}
              description="删除后不可恢复"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={onBatchDelete}
              disabled={selected.length === 0}
            >
              <Button size="small" danger icon={<DeleteOutlined />} disabled={selected.length === 0}>
                删除所选
              </Button>
            </Popconfirm>
            <Button size="small" onClick={exitSelectMode}>退出管理</Button>
          </span>
        )}
      </div>

      {groups.map((g) => renderGroup(g.label, g.plans))}
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Tag, Button, Empty, Statistic, Divider, Alert, Spin } from 'antd';
import { PlusOutlined, ClockCircleOutlined, CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { listPlans } from '../api';

// 后端 status → 列表展示
const STATUS_MAP = {
  brief_locked:         { label: '企划约束',    step: 0, color: 'blue' },
  insights_ready:       { label: '洞察驾驶舱',  step: 1, color: 'blue' },
  opportunities_ready:  { label: '机会生成',    step: 2, color: 'blue' },
  plan_card_ready:      { label: '新品企划卡',  step: 3, color: 'blue' },
  archived:             { label: '已归档',      step: 4, color: 'default' },
};

const STEP_LABELS = ['企划约束', '洞察驾驶舱', '机会生成', '新品企划卡', '归档'];

/** 企划任务卡片 */
function TaskCard({ task, onClick }) {
  const s = STATUS_MAP[task.status] || STATUS_MAP.brief_locked;
  const isArchived = task.status === 'archived';
  return (
    <Card
      hoverable
      onClick={onClick}
      size="small"
      style={{ borderLeft: `3px solid ${isArchived ? '#bbb' : '#7c5cfc'}` }}
      title={
        <span style={{ fontSize: 14 }}>
          <Tag color={s.color} style={{ marginRight: 8 }}>{s.label}</Tag>
          {task.theme || '未命名企划'}
        </span>
      }
    >
      <p style={{ margin: '0 0 4px', color: '#666', fontSize: 13 }}>
        {task.category} {task.audience ? `· ${task.audience}` : ''}
      </p>
      <p style={{ margin: 0, fontSize: 12, color: '#999' }}>
        当前环节：{STEP_LABELS[s.step]}
        {task.created_at && <span>　|　{(task.created_at || '').slice(0, 10)}</span>}
      </p>
    </Card>
  );
}

/** 任务中心：企划任务列表（只读真实后端数据，失败显式报错并提供重试） */
export default function Home() {
  const nav = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = () => {
    setLoading(true);
    setError(null);
    listPlans()
      .then(data => setTasks(Array.isArray(data?.plans) ? data.plans : []))
      .catch(e => setError(e?.message || '任务列表加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const activeTasks = tasks.filter(t => t.status !== 'archived');
  const archivedTasks = tasks.filter(t => t.status === 'archived');

  return (
    <div>
      {/* 顶部操作栏 */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>新品企划任务</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => nav('/new')}>新建企划</Button>
      </div>

      {/* 加载 / 错误状态 */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip="正在加载任务列表…" />
        </div>
      )}

      {!loading && error && (
        <Alert
          type="error"
          showIcon
          message="无法连接后端服务"
          description={error}
          action={<Button size="small" icon={<ReloadOutlined />} onClick={load}>重试</Button>}
          style={{ marginBottom: 20 }}
        />
      )}

      {!loading && !error && (
        <>
          {/* 概览统计 */}
          <Row gutter={16} style={{ marginBottom: 20 }}>
            <Col span={6}>
              <Card size="small">
                <Statistic title="进行中" value={activeTasks.length} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#7c5cfc' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title="已归档" value={archivedTasks.length} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#999' }} />
              </Card>
            </Col>
          </Row>

          {/* 进行中任务 */}
          <Divider orientation="left" style={{ fontSize: 14, margin: '8px 0 16px' }}>
            <ClockCircleOutlined style={{ marginRight: 6 }} />进行中
          </Divider>
          {activeTasks.length === 0 ? (
            <Empty description="暂无进行中的企划任务" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '24px 0' }} />
          ) : (
            <Row gutter={[16, 16]}>
              {activeTasks.map(t => (
                <Col span={8} key={t.plan_id}>
                  <TaskCard task={t} onClick={() => nav(`/tasks/${t.plan_id}`)} />
                </Col>
              ))}
            </Row>
          )}

          {/* 已归档任务 */}
          {archivedTasks.length > 0 && (
            <>
              <Divider orientation="left" style={{ fontSize: 14, margin: '24px 0 16px' }}>
                <CheckCircleOutlined style={{ marginRight: 6 }} />已归档
              </Divider>
              <Row gutter={[16, 16]}>
                {archivedTasks.map(t => (
                  <Col span={8} key={t.plan_id}>
                    <TaskCard task={t} onClick={() => nav(`/tasks/${t.plan_id}`)} />
                  </Col>
                ))}
              </Row>
            </>
          )}
        </>
      )}
    </div>
  );
}

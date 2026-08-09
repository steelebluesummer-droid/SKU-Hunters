import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Spin, Steps, Tabs, Result } from 'antd';
import { api } from '../api';
import LiveFeed from './detail/LiveFeed';
import Report from './detail/Report';
import Retro from './detail/Retro';

const STEPS = [
  { key: 'brief_locked', title: '锁定需求' },
  { key: 'act1_insights', title: '情报洞察' },
  { key: 'act1_gate', title: 'Gate 1' },
  { key: 'act2_ideation', title: '方案提出' },
  { key: 'act3_dual_review', title: '双轨评审' },
  { key: 'act4_decision', title: 'AI 建议' },
  { key: 'human_gate', title: 'Gate 2' },
  { key: 'act5_retro', title: '归档复盘' },
];

export default function ReviewDetail() {
  const { id } = useParams();
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try { setState(await api.getReview(id)); setError(null); } catch (e) { setError(e); }
  }, [id]);

  useEffect(() => { refresh(); const t = setInterval(refresh, 1000); return () => clearInterval(t); }, [refresh]);

  if (error) return <Result status="404" title="会议不存在" subTitle={error.message || String(error)} />;
  if (!state) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;

  const stepIdx = STEPS.findIndex(s => s.key === state.current_act);
  const current = stepIdx >= 0 ? stepIdx : 0;

  return (
    <div>
      <Steps current={current} size="small" style={{ marginBottom: 24 }}
        items={STEPS.map(s => ({ title: s.title }))} />
      <Tabs defaultActiveKey="live" items={[
        { key: 'live', label: '会议直播', children: <LiveFeed state={state} sessionId={id} onRefresh={refresh} /> },
        { key: 'report', label: '立项建议书', children: <Report sessionId={id} /> },
        { key: 'retro', label: '复盘', children: <Retro state={state} sessionId={id} onRefresh={refresh} /> },
      ]} />
    </div>
  );
}

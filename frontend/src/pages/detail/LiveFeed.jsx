import { useState } from 'react';
import { Timeline, Tag, Card, Button, Input, Slider, Space, message, Alert, Radio } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, EditOutlined, QuestionCircleOutlined, ExperimentOutlined } from '@ant-design/icons';
import { api } from '../../api';

const ROLE_ICON = { trend: '📈', user: '👤', ip: '🎯', creative: '💡', challenge: '⚔️', business: '💰', global: '🌍', decision: '📋', learning: '📚', qa: '💬', retro: '🔄' };
const ROLE_LABEL = { trend: '趋势官', user: '用户官', ip: 'IP 策略官', creative: '创意官', challenge: '圆桌质询', business: '商业官', global: '全球化官', decision: '决策引擎', learning: '学习官', qa: '问答', retro: '复盘助手' };

const DIMS = ['趋势热度', '用户需求', 'IP 契合', '竞争格局', '历史类比'];
const DIM_KEYS = ['trend_heat', 'user_demand', 'ip_fit', 'competition', 'history_analog'];

export default function LiveFeed({ state, sessionId, onRefresh }) {
  const gate = state.pending_gate;
  const [reason, setReason] = useState('');
  const [question, setQuestion] = useState('');
  const [scope, setScope] = useState('business');
  const [weights, setWeights] = useState({ trend_heat: 0.35, user_demand: 0.25, ip_fit: 0.20, competition: 0.10, history_analog: 0.10 });
  const [submitting, setSubmitting] = useState(false);

  const act = async (payload) => {
    setSubmitting(true);
    try { await api.decide(sessionId, payload); setReason(''); setQuestion(''); setTimeout(onRefresh, 300); }
    catch (e) { message.error(e?.message || '提交失败'); }
    setSubmitting(false);
  };

  const sum = DIM_KEYS.reduce((s, k) => s + (weights[k] || 0), 0);
  const sumValid = Math.abs(sum - 1.0) < 0.005;

  return (
    <div>
      {/* 委员发言时间线 */}
      <Timeline items={state.live_feed.map((e, i) => {
        const icon = ROLE_ICON[e.role] || '📌';
        const label = ROLE_LABEL[e.role] || e.role;
        const isGate = ['act1_gate', 'human_gate', 'retro'].includes(e.role);
        return {
          color: isGate ? 'red' : e.role === 'decision' ? 'blue' : 'green',
          children: (
            <Card key={i} size="small" style={{ marginBottom: 8 }} title={<>{icon} {label} {e.score != null && <Tag>{e.score.toFixed(1)} 分</Tag>}</>}>
              <p>{e.content}</p>
              {e.evidence?.length > 0 && <details><summary>证据 ({e.evidence.length} 条)</summary><ul>{e.evidence.map((ev, j) => <li key={j} style={{ fontSize: 12 }}>{ev}</li>)}</ul></details>}
            </Card>
          ),
        };
      })} />

      {/* 冲突 */}
      {state.conflicts?.length > 0 && (
        <Alert type="warning" message="分歧记录" description={state.conflicts.map((c, i) => <div key={i}>{c.description || c.conflict_type}</div>)} style={{ marginBottom: 16 }} />
      )}

      {/* 门操作面板 */}
      {gate && (
        <Card title={`🚪 ${gate.gate} — ${gate.prompt}`} style={{ borderColor: '#e60012' }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {/* reweight 面板 */}
            {(gate.gate === 'act1_gate' || gate.gate === 'human_gate') && (
              <Card size="small" title={<><ExperimentOutlined /> 权重调整 (reweight)</>} style={{ marginBottom: 12 }}>
                {DIM_KEYS.map((k, i) => (
                  <div key={k} style={{ marginBottom: 8 }}>
                    <span style={{ width: 80, display: 'inline-block' }}>{DIMS[i]}</span>
                    <Slider min={0} max={1} step={0.05} value={weights[k]} onChange={v => setWeights(prev => ({ ...prev, [k]: v }))} style={{ width: 300, margin: '0 12px' }} />
                    <span>{(weights[k] * 100).toFixed(0)}%</span>
                  </div>
                ))}
                <div style={{ marginTop: 8 }}>
                  <Tag color={sumValid ? 'green' : 'red'}>合计: {(sum * 100).toFixed(1)}% {sumValid ? '✅' : '❌ 必须 = 100%'}</Tag>
                  <Button size="small" disabled={!sumValid} onClick={() => act({ action: 'reweight', reason: reason || '手动调权', custom_weights: { ...weights } })} style={{ marginLeft: 12 }}>
                    重新计算
                  </Button>
                </div>
              </Card>
            )}

            <Input.TextArea rows={2} placeholder={gate.gate === 'retro' ? '输入问题' : '理由/修改意见'} value={gate.gate === 'retro' ? question : reason}
              onChange={e => (gate.gate === 'retro' ? setQuestion : setReason)(e.target.value)} />

            {gate.gate === 'human_gate' && (
              <Radio.Group value={scope} onChange={e => setScope(e.target.value)}>
                <Radio.Button value="business">仅商业官重算</Radio.Button>
                <Radio.Button value="creative">回退重做方案</Radio.Button>
              </Radio.Group>
            )}

            <Space>
              {gate.gate !== 'retro' ? (
                <>
                  <Button type="primary" icon={<CheckCircleOutlined />} loading={submitting}
                    onClick={() => act({ action: 'approve', reason: reason || '认可' })}>批准</Button>
                  {gate.gate === 'human_gate' && (
                    <Button danger icon={<CloseCircleOutlined />} loading={submitting}
                      onClick={() => act({ action: 'reject', reason: reason || '否决' })}>否决</Button>
                  )}
                  <Button icon={<EditOutlined />} loading={submitting}
                    onClick={() => act({ action: 'revise', reason: reason || '修改', scope })}>打回修改</Button>
                  <Button icon={<QuestionCircleOutlined />} loading={submitting}
                    onClick={() => act({ action: 'question', question: question || '请解释' })}>提问</Button>
                </>
              ) : (
                <>
                  <Button type="primary" loading={submitting}
                    onClick={() => act({ action: 'chat', content: question || '复盘' })}>💬 提问</Button>
                  <Button loading={submitting} onClick={() => act({ action: 'done' })}>📝 结束复盘</Button>
                </>
              )}
            </Space>
          </Space>
        </Card>
      )}
    </div>
  );
}

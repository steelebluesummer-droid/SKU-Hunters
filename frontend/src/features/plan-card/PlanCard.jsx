import { useEffect, useRef, useState } from 'react';
import { Card, Row, Col, Tag, Timeline, Input, Button, List, Spin, Space, Alert } from 'antd';
import { SendOutlined, LoadingOutlined } from '@ant-design/icons';
import ProcessLog from '../../shared/components/ProcessLog';

const GRADIENTS = {
  'ip-collect': 'linear-gradient(135deg, #f3e6ff 0%, #e0ccfa 50%, #fad1dc 100%)',
  'healing-nature': 'linear-gradient(135deg, #e0f5ec 0%, #cde7f0 60%, #b8e6d0 100%)',
  'outdoor-clip': 'linear-gradient(135deg, #fdf3e0 0%, #f8d5b0 55%, #f5e6b8 100%)',
};
const DEFAULT_GRADIENT = 'linear-gradient(135deg, #f6f3ff 0%, #d9ccff 100%)';

const QUICK_SUGGESTIONS = [
  '配色再柔和一点',
  '加一个挂绳/挂扣功能',
  '价格压到 55 元以内',
  '增加联名 IP 的视觉占比',
  '材质换成磨砂质感',
];

/**
 * 新品企划卡（纯展示/事件组件）：创意设计 + 商品策略 + 对话式改稿。
 * 不 import API、不接收 planId、不发请求；生成/改稿均通过事件回调由容器（usePlanWorkspace）执行。
 * @param {object} card        已生成的企划卡（可为 null）
 * @param {object} opportunity 选中的机会卡对象
 * @param {object} brief       约束（camelCase）
 * @param {string} status      'idle' | 'loading' | 'success' | 'error'
 * @param {Function} onGenerate(opportunityId) 生成/重试企划卡
 * @param {Function} onRevise(message) 改稿沟通（返回 { reply }）
 */
export default function PlanCard({ card, opportunity, brief, status, onGenerate, onRevise }) {
  const [chats, setChats] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [logDone, setLogDone] = useState(false);
  const chatEnd = useRef(null);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }); }, [chats]);

  const send = async (text) => {
    const message = (text || input).trim();
    if (!message || sending) return;
    setInput('');
    setSending(true);
    setChats((cs) => [...cs, { role: 'user', text: message }]);
    try {
      const data = await onRevise(message);
      setChats((cs) => [...cs, { role: 'ai', text: data?.reply || '(无回复)' }]);
    } catch (e) {
      setChats((cs) => [...cs, { role: 'ai', text: `改稿沟通失败：${e?.message || '请确认后端在线'}` }]);
    } finally {
      setSending(false);
    }
  };

  if (status === 'loading') {
    return <div style={{ textAlign: 'center', padding: 60 }} aria-busy="true"><Spin size="large" /></div>;
  }

  if (status === 'error' && !card) {
    return (
      <Alert
        type="error"
        showIcon
        role="alert"
        message="企划卡生成失败"
        action={<Button size="small" onClick={() => onGenerate?.(opportunity?.id)}>重试</Button>}
      />
    );
  }

  if (!card) return null;

  const emoji = opportunity?.emoji || '✨';
  const direction = opportunity?.direction || '';
  const gradient = GRADIENTS[card.opportunityId] || DEFAULT_GRADIENT;
  const priceRange = brief?.priceRange || [39, 99];
  const costLimit = brief?.costLimit ?? 25;

  return (
    <div>
      {card.processLog && (
        <Card size="small" title="企划生成 · 思考过程" style={{ marginBottom: 16, background: '#f6f3ff', border: '1px solid #d9ccff' }}>
          <ProcessLog key={opportunity?.id} lines={card.processLog} onDone={() => setLogDone(true)} />
        </Card>
      )}

      <div style={{ opacity: !card.processLog || logDone ? 1 : 0, transition: 'opacity 0.5s', pointerEvents: !card.processLog || logDone ? 'auto' : 'none' }}>
        <Card>
          <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>
            {brief?.theme} · {brief?.category} · 价格带 {priceRange[0]}-{priceRange[1]} 元 · 成本 ≤{costLimit} 元
          </div>
          <h1 style={{ margin: '0 0 4px' }}>{emoji} {card.name}</h1>
          <p style={{ color: '#666' }}>{card.concept}</p>

          <Row gutter={24} style={{ marginTop: 16 }}>
            <Col span={10}>
              {card.conceptImage ? (
                <img src={card.conceptImage} alt="产品概念图" style={{ width: '100%', borderRadius: 12 }} />
              ) : (
                <div className="concept-image" style={{ background: gradient }}>
                  <div>{emoji}</div>
                  <div className="concept-caption">产品概念图 · 即梦文生图接入后替换</div>
                </div>
              )}
              {card.costCheck && (
                <div style={{ fontSize: 12, color: card.costCheck.passed ? '#3a7d44' : '#e60012', marginTop: 6, padding: '6px 10px', background: card.costCheck.passed ? '#eef7ef' : '#fff0f0', borderRadius: 6 }}>
                  {card.costCheck.passed ? '✅' : '❌'} 成本校验：{card.costCheck.reason}
                </div>
              )}
            </Col>
            <Col span={14}>
              <h3>设计语言<span className="plan-section-tag">创意设计</span></h3>
              <p style={{ fontSize: 13 }}>{card.designLanguage}</p>
              <h3>关键词<span className="plan-section-tag">创意设计</span></h3>
              <p>{(card.keywords || []).map((k) => <Tag key={k} color="purple">{k}</Tag>)}</p>
              <h3>功能点<span className="plan-section-tag">创意设计</span></h3>
              <ul style={{ fontSize: 13, paddingLeft: 18, margin: 0 }}>
                {(card.features || []).map((f) => <li key={f}>{f}</li>)}
              </ul>
            </Col>
          </Row>

          <Card size="small" style={{ margin: '16px 0', background: '#faf8ff' }}>
            <b>跨品类融合说明：</b>{card.fusion}
          </Card>

          <Row gutter={24}>
            <Col span={8}>
              <h3>定价<span className="plan-section-tag">商品策略</span></h3>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#e60012' }}>{card.pricing?.price || '—'}</div>
              <p style={{ fontSize: 12, color: '#666' }}>{card.pricing?.reason}</p>
            </Col>
            <Col span={9}>
              <h3>上新节奏<span className="plan-section-tag">商品策略</span></h3>
              <Timeline
                items={(card.schedule || []).map((s) => ({ children: <span style={{ fontSize: 12 }}><b>{s.time}</b>　{s.action}</span> }))}
              />
            </Col>
            <Col span={7}>
              <h3>上市验证计划<span className="plan-section-tag">商品策略</span></h3>
              <ul style={{ fontSize: 12, paddingLeft: 18 }}>
                {(card.validation || []).map((v) => <li key={v} style={{ marginBottom: 6 }}>{v}</li>)}
              </ul>
            </Col>
          </Row>
        </Card>
      </div>

      <Card title="💬 改稿沟通" size="small" style={{ marginTop: 16 }}>
        {chats.length > 0 && (
          <div style={{ maxHeight: 320, overflow: 'auto', marginBottom: 12 }}>
            <List
              size="small"
              split={false}
              dataSource={chats}
              renderItem={(c) => (
                <List.Item style={{ padding: '4px 0', border: 'none', flexDirection: c.role === 'user' ? 'row-reverse' : 'row' }}>
                  <div style={{
                    maxWidth: '80%', padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
                    background: c.role === 'user' ? '#7c5cfc' : '#f0f0f0',
                    color: c.role === 'user' ? '#fff' : '#333',
                    borderTopRightRadius: c.role === 'user' ? 4 : 12,
                    borderTopLeftRadius: c.role === 'ai' ? 4 : 12,
                  }}>
                    <span style={{ fontSize: 11, opacity: 0.7, display: 'block', marginBottom: 2 }}>
                      {c.role === 'user' ? '我' : 'AI 企划助手'}
                    </span>
                    {c.text}
                  </div>
                </List.Item>
              )}
            />
            {sending && (
              <div style={{ textAlign: 'left', padding: '8px 12px' }}>
                <Spin indicator={<LoadingOutlined />} size="small" /> <span style={{ color: '#999', fontSize: 12 }}>正在分析修改意见…</span>
              </div>
            )}
            <div ref={chatEnd} />
          </div>
        )}

        {chats.length === 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#999', marginBottom: 6 }}>快捷改稿建议：</div>
            <Space wrap size={[6, 6]}>
              {QUICK_SUGGESTIONS.map((s) => (
                <Tag key={s} style={{ cursor: 'pointer', padding: '4px 10px', fontSize: 12 }} onClick={() => send(s)}>{s}</Tag>
              ))}
            </Space>
          </div>
        )}

        <Input.Search
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onSearch={() => send()}
          enterButton={<><SendOutlined /> 提交修改意见</>}
          placeholder="如：配色再粉一点 / 加一个挂绳功能 / 价格压到 55 元以内"
          loading={sending}
        />
      </Card>
    </div>
  );
}

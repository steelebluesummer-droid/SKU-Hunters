import { useEffect, useRef, useState } from 'react';
import { Card, Row, Col, Tag, Timeline, Input, Button, List, Spin, Space, Alert } from 'antd';
import { SendOutlined, LoadingOutlined } from '@ant-design/icons';
import ProcessLog from '../../shared/components/ProcessLog';

const GRADIENTS = {
  'ip-collect': 'var(--grad-ip-collect)',
  'healing-nature': 'var(--grad-healing-nature)',
  'outdoor-clip': 'var(--grad-outdoor-clip)',
};
const DEFAULT_GRADIENT = 'var(--grad-default)';

const QUICK_SUGGESTIONS = [
  '配色再柔和一点',
  '加一个挂绳/挂扣功能',
  '价格压到 55 元以内',
  '增加联名 IP 的视觉占比',
  '材质换成磨砂质感',
];

/**
 * 新品企划卡（纯展示/事件组件）：创意设计 + 商品策略 + 改稿沟通 / 复盘追问。
 * 不 import API、不接收 planId、不发请求；生成/改稿/复盘均通过事件回调由容器执行。
 * 归档只读：plan_card_ready 显示「改稿沟通」，archived 显示「复盘追问」（只读回顾，不改稿）。
 * @param {object} card        已生成企划卡
 * @param {object} opportunity 选中的机会卡
 * @param {object} brief       约束（camelCase）
 * @param {string} status      'idle' | 'loading' | 'success' | 'error'（生成状态）
 * @param {boolean} isArchived 是否已归档（决定改稿 vs 复盘追问）
 * @param {Function} onGenerate(opportunityId) 生成/重试
 * @param {Function} onRevise(message) 改稿（仅 plan_card_ready）
 * @param {Function} onReview(question) 复盘追问（仅 archived，只读）
 */
export default function PlanCard({ card, opportunity, brief, status, isArchived, onGenerate, onRevise, onReview }) {
  const [chats, setChats] = useState([]);
  const [reviewChats, setReviewChats] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [logDone, setLogDone] = useState(false);
  const chatEnd = useRef(null);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }); }, [chats, reviewChats]);

  // 改稿（仅 plan_card_ready）
  const sendRevise = async (text) => {
    const message = (text || input).trim();
    if (!message || sending || isArchived) return;
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

  // 复盘追问（仅 archived，只读）
  const sendReview = async (text) => {
    const question = (text || input).trim();
    if (!question || sending || !isArchived) return;
    setInput('');
    setSending(true);
    setReviewChats((cs) => [...cs, { role: 'user', text: question }]);
    try {
      const data = await onReview(question);
      setReviewChats((cs) => [...cs, { role: 'ai', text: data?.answer || '(无回复)' }]);
    } catch (e) {
      setReviewChats((cs) => [...cs, { role: 'ai', text: `复盘追问失败：${e?.message || '请确认后端在线'}` }]);
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
        type="error" showIcon role="alert" message="企划卡生成失败"
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
        <Card size="small" title="企划生成 · 思考过程" style={{ marginBottom: 16, background: 'var(--color-surface-alt)', border: '1px solid var(--color-border-strong)' }}>
          <ProcessLog key={opportunity?.id} lines={card.processLog} onDone={() => setLogDone(true)} />
        </Card>
      )}

      <div style={{ opacity: !card.processLog || logDone ? 1 : 0, transition: 'opacity 0.5s', pointerEvents: !card.processLog || logDone ? 'auto' : 'none' }}>
        <Card>
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>
            {brief?.theme} · {brief?.category} · 价格带 {priceRange[0]}-{priceRange[1]} 元 · 成本 ≤{costLimit} 元
          </div>
          <h1 style={{ margin: '0 0 4px' }}>{emoji} {card.name}</h1>
          <p style={{ color: 'var(--color-text-secondary)' }}>{card.concept}</p>

          <Row gutter={24} style={{ marginTop: 16 }}>
            <Col xs={24} lg={10}>
              {card.conceptImage ? (
                <img src={card.conceptImage} alt="产品概念图" style={{ width: '100%', borderRadius: 12 }} />
              ) : (
                <div className="concept-image" style={{ background: gradient }}>
                  <div>{emoji}</div>
                  <div className="concept-caption">产品概念图 · 即梦文生图接入后替换</div>
                </div>
              )}
              {card.costCheck && (
                <div style={{ fontSize: 12, color: card.costCheck.passed ? 'var(--cost-pass-fg)' : 'var(--cost-fail-fg)', marginTop: 6, padding: '6px 10px', background: card.costCheck.passed ? 'var(--cost-pass-bg)' : 'var(--cost-fail-bg)', borderRadius: 6 }}>
                  {card.costCheck.passed ? '✅' : '❌'} 成本校验：{card.costCheck.reason}
                </div>
              )}
            </Col>
            <Col xs={24} lg={14}>
              <h3>设计语言<span className="plan-section-tag">创意设计</span></h3>
              <p style={{ fontSize: 13 }}>{card.designLanguage}</p>
              <h3>关键词<span className="plan-section-tag">创意设计</span></h3>
              <p>{(card.keywords || []).map((k) => <Tag key={k} color="purple" style={{ whiteSpace: 'normal', wordBreak: 'break-word', maxWidth: '100%', height: 'auto', lineHeight: '1.6' }}>{k}</Tag>)}</p>
              <h3>功能点<span className="plan-section-tag">创意设计</span></h3>
              <ul style={{ fontSize: 13, paddingLeft: 18, margin: 0 }}>
                {(card.features || []).map((f) => <li key={f}>{f}</li>)}
              </ul>
            </Col>
          </Row>

          <Card size="small" style={{ margin: '16px 0', background: 'var(--color-surface-alt)' }}>
            <b>跨品类融合说明：</b>{card.fusion}
          </Card>

          <Row gutter={24}>
            <Col xs={24} md={8}>
              <h3>定价<span className="plan-section-tag">商品策略</span></h3>
              <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--color-brand-accent)' }}>{card.pricing?.price || '—'}</div>
              <p style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{card.pricing?.reason}</p>
            </Col>
            <Col xs={24} md={9}>
              <h3>上新节奏<span className="plan-section-tag">商品策略</span></h3>
              <Timeline
                items={(card.schedule || []).map((s) => ({ children: <span style={{ fontSize: 12 }}><b>{s.time}</b>　{s.action}</span> }))}
              />
            </Col>
            <Col xs={24} md={7}>
              <h3>上市验证计划<span className="plan-section-tag">商品策略</span></h3>
              <ul style={{ fontSize: 12, paddingLeft: 18 }}>
                {(card.validation || []).map((v) => <li key={v} style={{ marginBottom: 6 }}>{v}</li>)}
              </ul>
            </Col>
          </Row>
        </Card>
      </div>

      {isArchived ? (
        <Card title="💬 复盘追问" size="small" style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 8 }}>企划案已归档，仅可复盘回顾，不可再改稿。</div>
          {reviewChats.length > 0 && (
            <div style={{ maxHeight: 320, overflow: 'auto', marginBottom: 12 }}>
              <List
                size="small" split={false} dataSource={reviewChats}
                renderItem={(c) => (
                  <List.Item style={{ padding: '4px 0', border: 'none', flexDirection: c.role === 'user' ? 'row-reverse' : 'row' }}>
                    <div style={{
                      maxWidth: '80%', padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
                      background: c.role === 'user' ? 'var(--chat-user-bg)' : 'var(--chat-ai-bg)', color: c.role === 'user' ? 'var(--chat-user-fg)' : 'var(--chat-ai-fg)',
                      borderTopRightRadius: c.role === 'user' ? 4 : 12, borderTopLeftRadius: c.role === 'ai' ? 4 : 12,
                    }}>
                      <span style={{ fontSize: 11, opacity: 0.7, display: 'block', marginBottom: 2 }}>
                        {c.role === 'user' ? '我' : 'AI 复盘助手'}
                      </span>
                      {c.text}
                    </div>
                  </List.Item>
                )}
              />
              {sending && (
                <div style={{ textAlign: 'left', padding: '8px 12px' }}>
                  <Spin indicator={<LoadingOutlined />} size="small" /> <span style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>正在复盘…</span>
                </div>
              )}
              <div ref={chatEnd} />
            </div>
          )}
          <Input.Search
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onSearch={() => sendReview()}
            enterButton={<><SendOutlined /> 提交追问</>}
            placeholder="如：这个定价的依据是什么？"
            loading={sending}
          />
        </Card>
      ) : (
        <Card title="💬 改稿沟通" size="small" style={{ marginTop: 16 }}>
          {chats.length > 0 && (
            <div style={{ maxHeight: 320, overflow: 'auto', marginBottom: 12 }}>
              <List
                size="small" split={false} dataSource={chats}
                renderItem={(c) => (
                  <List.Item style={{ padding: '4px 0', border: 'none', flexDirection: c.role === 'user' ? 'row-reverse' : 'row' }}>
                    <div style={{
                      maxWidth: '80%', padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
                      background: c.role === 'user' ? 'var(--chat-user-bg)' : 'var(--chat-ai-bg)', color: c.role === 'user' ? 'var(--chat-user-fg)' : 'var(--chat-ai-fg)',
                      borderTopRightRadius: c.role === 'user' ? 4 : 12, borderTopLeftRadius: c.role === 'ai' ? 4 : 12,
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
                  <Spin indicator={<LoadingOutlined />} size="small" /> <span style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>正在分析修改意见…</span>
                </div>
              )}
              <div ref={chatEnd} />
            </div>
          )}

          {chats.length === 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 6 }}>快捷改稿建议：</div>
              <Space wrap size={[6, 6]}>
                {QUICK_SUGGESTIONS.map((s) => (
                  <Button key={s} size="small" onClick={() => sendRevise(s)}>{s}</Button>
                ))}
              </Space>
            </div>
          )}

          <Input.Search
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onSearch={() => sendRevise()}
            enterButton={<><SendOutlined /> 提交修改意见</>}
            placeholder="如：配色再粉一点 / 加一个挂绳功能 / 价格压到 55 元以内"
            loading={sending}
          />
        </Card>
      )}
    </div>
  );
}

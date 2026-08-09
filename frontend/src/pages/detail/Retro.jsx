import { useState } from 'react';
import { Card, Tag, Input, Button, Timeline, message, Empty } from 'antd';
import { api } from '../../api';

export default function Retro({ state, sessionId, onRefresh }) {
  const archive = state.archive;
  const logs = state.retro_logs || [];
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const hasArchive = archive != null;

  const ask = async () => {
    if (!question.trim()) return;
    setLoading(true);
    try {
      const res = await api.retroChat(sessionId, question);
      message.success(res.answer?.slice(0, 60) + '...');
      setQuestion('');
      setTimeout(onRefresh, 500);
    } catch (e) { message.error(e?.message || '追问失败'); }
    setLoading(false);
  };

  return (
    <div>
      {archive ? (
        <Card title="归档快照" size="small" style={{ marginBottom: 16 }}>
          <p><Tag color={archive.status === 'rejected' ? 'red' : 'green'}>{archive.status}</Tag>
            &nbsp; AI 建议：{archive.ai_decision} / 人决策：{archive.human_action}</p>
          <p>提案：{archive.proposal} &nbsp;|&nbsp; 预测分：{archive.predicted_score?.toFixed(1)} &nbsp;|&nbsp; 复盘：{archive.retro_turns} 轮</p>
        </Card>
      ) : (
        <Empty description="尚未归档，复盘入口在 Gate 2 结论后开启" style={{ marginBottom: 16 }} />
      )}

      {logs.length > 0 && (
        <Card title="历史复盘对话" size="small" style={{ marginBottom: 16 }}>
          <Timeline items={logs.map((l, i) => ({
            children: <div key={i}><p style={{ fontWeight: 500 }}>❓ {l.question}</p><p>💬 {l.answer}</p><p style={{ color: '#999', fontSize: 12 }}>{l.timestamp?.slice(0, 19).replace('T', ' ')}</p></div>,
          }))} />
        </Card>
      )}

      {hasArchive && (
        <Card size="small" title="追问复盘助手">
          <Input.TextArea rows={2} value={question} onChange={e => setQuestion(e.target.value)}
            placeholder="如：为什么第二名落选？下次该提高哪个权重？" disabled={!hasArchive} />
          <Button type="primary" onClick={ask} loading={loading} disabled={!question.trim() || !hasArchive} style={{ marginTop: 8 }}>
            提问
          </Button>
        </Card>
      )}
    </div>
  );
}

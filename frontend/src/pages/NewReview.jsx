import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Select, Input, Button, Card, message } from 'antd';
import { api } from '../api';

const MARKETS = ['CN', 'US', 'JP', 'KR', 'TH', 'ID', 'BR', 'EU'];
const BUDGETS = ['low', 'mid', 'high'];

export default function NewReview() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  useEffect(() => { api.weightTemplates().then(r => setTemplates(r.templates)).catch(() => {}); }, []);

  const onFinish = async (v) => {
    setLoading(true);
    try {
      const res = await api.createReview({ category: v.category, market: v.market, budget_range: v.budget_range, weight_template: v.template, candidate_pool: v.pool?.split(/[,，]/).map(s => s.trim()).filter(Boolean) || [] });
      message.success('评审已发起');
      nav(`/reviews/${res.session_id}`);
    } catch (e) { message.error(e?.message || '发起失败'); }
    setLoading(false);
  };

  return (
    <Card title="新建评审" style={{ maxWidth: 600 }}>
      <Form layout="vertical" onFinish={onFinish} initialValues={{ market: 'CN', budget_range: 'mid', template: 'default' }}>
        <Form.Item label="品类" name="category" rules={[{ required: true, message: '必填' }]}>
          <Input placeholder="如 解压玩具、潮玩" />
        </Form.Item>
        <Form.Item label="目标市场" name="market"><Select options={MARKETS.map(m => ({ value: m, label: m }))} /></Form.Item>
        <Form.Item label="预算带" name="budget_range"><Select options={BUDGETS.map(b => ({ value: b, label: b }))} /></Form.Item>
        <Form.Item label="权重模板" name="template">
          <Select options={templates.map(t => ({ value: t.key, label: `${t.label}（${Object.entries(t.weights).map(([k, v]) => `${k}=${v}`).join(', ')}）` }))} />
        </Form.Item>
        <Form.Item label="候选 IP / 方向" name="pool"><Input placeholder="Labubu, Chiikawa, 线条小狗（逗号分隔）" /></Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>发起评审</Button>
      </Form>
    </Card>
  );
}

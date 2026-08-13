import { useEffect, useState } from 'react';
import { Card, Row, Col, Tag, Spin, Alert, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getTrendGallery } from '../api';

// 流行元素板 Trend Gallery：跨品类流行元素（配色/花纹/形状/表情化），创意设计的视觉输入
// 只读真实后端 /trend-gallery 数据，失败显式报错并提供重试。
export default function TrendGallery() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getTrendGallery()
      .then(d => setData(d || {}))
      .catch(e => setError(e?.message || 'Trend Gallery 加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '60px 0' }}><Spin tip="正在加载流行元素板…" /></div>;
  }
  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="无法连接后端服务"
        description={error}
        action={<Button size="small" icon={<ReloadOutlined />} onClick={load}>重试</Button>}
      />
    );
  }

  const colors = data.colors || [];
  const patterns = data.patterns || [];
  const shapes = data.shapes || [];
  const expressions = data.expressions || [];

  return (
    <div>
      <h2>流行元素板 · Trend Gallery</h2>
      <p style={{ color: '#888', fontSize: 13, marginTop: -8 }}>
        跨品类采集（服装 / 食品 / 美妆 / 潮玩），不绑定具体品类——企划生成时由创意设计模块调用融合
      </p>

      <Card title="配色趋势" size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          {colors.map(c => (
            <Col span={4} key={c.name}>
              <div className="swatch" style={{ background: c.hex }}>
                <div className="swatch-name">{c.name}</div>
                <div className="swatch-source">{c.hex} · {c.source}</div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="花纹图案" size="small" style={{ marginBottom: 16 }}>
            {patterns.map(p => (
              <Card key={p.name} size="small" style={{ marginBottom: 8 }}>
                <b>{p.name}</b> <Tag style={{ marginLeft: 8 }}>{p.source}</Tag>
                <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{p.note}</div>
              </Card>
            ))}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="形态结构" size="small" style={{ marginBottom: 16 }}>
            {shapes.map(s => (
              <Card key={s.name} size="small" style={{ marginBottom: 8 }}>
                <b>{s.name}</b> <Tag style={{ marginLeft: 8 }}>{s.source}</Tag>
                <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{s.note}</div>
              </Card>
            ))}
          </Card>
        </Col>
      </Row>

      <Card title="表情化趋势（IP 情绪语言）" size="small">
        <Row gutter={16}>
          {expressions.map(e => (
            <Col span={8} key={e.name}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 36, letterSpacing: 2 }}>{e.emoji}</div>
                <b>{e.name}</b>
                <div style={{ fontSize: 12, color: '#666' }}>{e.note}</div>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}

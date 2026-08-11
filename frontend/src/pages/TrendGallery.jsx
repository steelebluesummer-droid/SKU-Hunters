import { Card, Row, Col, Tag } from 'antd';
import { TREND_GALLERY } from '../mock/fanData';

// 流行元素板 Trend Gallery：跨品类流行元素（配色/花纹/形状/表情化），创意设计的视觉输入
export default function TrendGallery() {
  return (
    <div>
      <h2>流行元素板 · Trend Gallery</h2>
      <p style={{ color: '#888', fontSize: 13, marginTop: -8 }}>
        跨品类采集（服装 / 食品 / 美妆 / 潮玩），不绑定具体品类——企划生成时由创意设计模块调用融合
      </p>

      <Card title="配色趋势" size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          {TREND_GALLERY.colors.map(c => (
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
            {TREND_GALLERY.patterns.map(p => (
              <Card key={p.name} size="small" style={{ marginBottom: 8 }}>
                <b>{p.name}</b> <Tag style={{ marginLeft: 8 }}>{p.source}</Tag>
                <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{p.note}</div>
              </Card>
            ))}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="形态结构" size="small" style={{ marginBottom: 16 }}>
            {TREND_GALLERY.shapes.map(s => (
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
          {TREND_GALLERY.expressions.map(e => (
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

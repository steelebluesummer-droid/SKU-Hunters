import { Card, Row, Col, Tag, Progress } from 'antd';
import { INSIGHT_BASE } from '../mock/fanData';

const STATUS_COLOR = { '合作中': 'green', '洽谈中': 'orange' };

// 名创内部 Insight Base：历史爆品特征 / IP 资源库 / 设计语言资产（策展数据，非 Agent 现搜）
export default function InsightBase() {
  return (
    <div>
      <h2>名创内部 · Insight Base</h2>
      <Row gutter={[16, 16]}>
        <Col span={14}>
          <Card title="历史爆品特征库" size="small">
            {INSIGHT_BASE.hitProducts.map(p => (
              <Card key={p.name} size="small" style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b>{p.name}</b>
                  <span style={{ fontSize: 12 }}>爆品指数 <b style={{ color: '#e60012' }}>{p.index}</b></span>
                </div>
                <Progress percent={p.index} showInfo={false} strokeColor="#e60012" size="small" style={{ margin: '4px 0' }} />
                <div>{p.factors.map(f => <Tag key={f} color="purple">{f}</Tag>)}</div>
                <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{p.note}</div>
              </Card>
            ))}
          </Card>
        </Col>
        <Col span={10}>
          <Card title="IP 资源库" size="small">
            {INSIGHT_BASE.ipPool.map(ip => (
              <Card key={ip.name} size="small" style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <b>{ip.name}</b>
                  <span>
                    <Tag color={STATUS_COLOR[ip.status]}>{ip.status}</Tag>
                    <Tag color={ip.heat.includes('↑') ? 'red' : 'default'}>{ip.heat}</Tag>
                  </span>
                </div>
                <div style={{ fontSize: 12, color: '#666' }}>适配品类：{ip.fit.join(' / ')}</div>
              </Card>
            ))}
          </Card>
          <Card title="名创设计语言" size="small" style={{ marginTop: 16 }}>
            {INSIGHT_BASE.designLanguage.map(d => <Tag key={d} color="geekblue" style={{ marginBottom: 4 }}>{d}</Tag>)}
            <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>企划生成时作为品牌一致性约束注入创意设计模块</p>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

/* ============================================================
 * SKU Hunters · InsightBase（名创内部 · 洞察资产库）
 * 使用 api/dashboard.js 的 getInsightBase，接口失败不回退 fixture。
 * 三个语义区块：历史爆品特征库 / IP 资源库 / 名创设计语言。
 * 状态用文字标签表达（不依赖颜色）；长 IP 名与标签自动换行。
 * 响应式：375 单列，宽屏 14/10 布局。
 * ============================================================ */

import { useEffect, useState } from 'react';
import { Card, Row, Col, Tag, Progress, Empty } from 'antd';
import { getInsightBase } from '../../api/dashboard';
import StateCard from '../../shared/components/StateCard';
import PageHeader from '../plans/components/PageHeader';

// IP 合作状态 → 颜色（颜色仅辅助，状态含义由文字承载）
const STATUS_COLOR = { 合作中: 'green', 洽谈中: 'orange' };

export default function InsightBase() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getInsightBase();
      setData(d || {});
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <div>
        <PageHeader title="名创内部 · Insight Base" />
        <StateCard status="loading" />
      </div>
    );
  }
  if (error) {
    return (
      <div>
        <PageHeader title="名创内部 · Insight Base" />
        <StateCard status="error" onRetry={load} emptyText="Insight Base 加载失败" />
      </div>
    );
  }

  const hitProducts = data.hitProducts || [];
  const ipPool = data.ipPool || [];
  const designLanguage = data.designLanguage || [];

  return (
    <div>
      <PageHeader
        title="名创内部 · Insight Base"
        subtitle="历史爆品特征 / IP 资源库 / 设计语言资产（策展数据，非 Agent 现搜）"
      />

      <Row gutter={[16, 16]}>
        {/* 历史爆品特征库 */}
        <Col xs={24} lg={14}>
          <Card title="历史爆品特征库" size="small">
            {hitProducts.length === 0 ? (
              <Empty description="暂无历史爆品数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              hitProducts.map((p) => (
                <Card key={p.name} size="small" style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                    <b style={{ wordBreak: 'break-word' }}>{p.name}</b>
                    <span style={{ fontSize: 12 }}>爆品指数 <b style={{ color: '#e60012' }}>{p.index}</b></span>
                  </div>
                  <Progress percent={p.index} showInfo={false} strokeColor="#e60012" size="small" style={{ margin: '4px 0' }} />
                  <div>
                    {(p.factors || []).map((f) => (
                      <Tag key={f} color="purple" style={{ marginBottom: 4, wordBreak: 'break-word' }}>{f}</Tag>
                    ))}
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4, wordBreak: 'break-word' }}>{p.note}</div>
                </Card>
              ))
            )}
          </Card>
        </Col>

        {/* IP 资源库 + 设计语言 */}
        <Col xs={24} lg={10}>
          <Card title="IP 资源库" size="small">
            {ipPool.length === 0 ? (
              <Empty description="暂无 IP 资源数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              ipPool.map((ip) => (
                <Card key={ip.name} size="small" style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
                    <b style={{ wordBreak: 'break-word' }}>{ip.name}</b>
                    <span>
                      <Tag color={STATUS_COLOR[ip.status]}>{ip.status}</Tag>
                      <Tag color={ip.heat?.includes('↑') ? 'red' : 'default'}>{ip.heat}</Tag>
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: '#666', wordBreak: 'break-word' }}>
                    适配品类：{(ip.fit || []).join(' / ')}
                  </div>
                </Card>
              ))
            )}
          </Card>

          <Card title="名创设计语言" size="small" style={{ marginTop: 16 }}>
            {designLanguage.length === 0 ? (
              <Empty description="暂无设计语言数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <>
                <div>
                  {designLanguage.map((d) => (
                    <Tag key={d} color="geekblue" style={{ marginBottom: 4, wordBreak: 'break-word' }}>{d}</Tag>
                  ))}
                </div>
                <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
                  企划生成时作为品牌一致性约束注入创意设计模块
                </p>
              </>
            )}
          </Card>
        </Col>
      </Row>

      <p style={{ fontSize: 12, color: '#999', marginTop: 16 }}>
        数据来源：名创内部策展资产（冻结 fixture，可切换实时）
      </p>
    </div>
  );
}

import { useMemo, useState } from 'react';
import { Card, Row, Col, Tag, Segmented, Rate, Progress } from 'antd';
import ReactECharts from 'echarts-for-react';
import { INSIGHT_BASE } from '../mock/fanData';
import { IP_STATS, IP_RESOURCE, AUDIENCE_FILTERS, STYLE_FILTERS, ipAssetPath } from '../data/ipResource';

// 图片缺失降级：onError 时替换为色块占位（素材后补进 public/assets/ip/ 即自动生效）
function IpImage({ src, alt, className, fallback }) {
  const [err, setErr] = useState(false);
  if (err) return fallback;
  return <img src={src} alt={alt} className={className} onError={() => setErr(true)} />;
}

// IP 定位四象限（AI 基于历史商品特征的推演，仅作演示参考）
function IpMatrix() {
  const option = {
    grid: { left: 40, right: 40, top: 40, bottom: 40 },
    xAxis: { min: 0, max: 1, show: false },
    yAxis: { min: 0, max: 1, show: false },
    series: [{
      type: 'scatter',
      symbolSize: 14,
      itemStyle: { color: '#7A5FD0', opacity: 0.85 },
      label: { show: true, position: 'top', formatter: '{@[2]}', fontSize: 11, color: '#555' },
      data: IP_RESOURCE.map(ip => [ip.matrix.x, ip.matrix.y, ip.nameCn]),
    }],
    // 象限角标（分割线用下方 markLine 画，graphic 拿不到坐标系像素）
    graphic: [
      { type: 'text', left: 44, top: 44, style: { text: '女性向', fontSize: 12, fill: '#b7a8f5' }, silent: true },
      { type: 'text', right: 44, top: 44, style: { text: '男性 / ACG', fontSize: 12, fill: '#b7a8f5' }, silent: true },
      { type: 'text', left: '50%', top: 40, style: { text: '潮流个性', fontSize: 12, fill: '#b7a8f5', align: 'center' }, silent: true },
      { type: 'text', left: '50%', bottom: 40, style: { text: '可爱萌系', fontSize: 12, fill: '#b7a8f5', align: 'center' }, silent: true },
    ],
  };
  // 象限分割线用 markLine 画（graphic 拿不到坐标系中心像素）
  option.series[0].markLine = {
    silent: true, symbol: 'none',
    lineStyle: { color: '#e3ddf5', type: 'dashed' },
    data: [{ xAxis: 0.5 }, { yAxis: 0.5 }],
    label: { show: false },
  };
  return <ReactECharts option={option} style={{ height: 340 }} />;
}

function IpCard({ ip }) {
  return (
    <Card className="ip-card" size="small">
      <IpImage
        src={ipAssetPath(ip.slug, 'cover.jpg')} alt={ip.nameCn} className="ip-cover"
        fallback={<div className="ip-cover ip-cover-fallback">{ip.nameCn}</div>}
      />
      <div className="ip-card-body">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <IpImage
              src={ipAssetPath(ip.slug, 'logo.png')} alt="" className="ip-logo"
              fallback={null}
            />
            <div style={{ minWidth: 0 }}>
              <b>{ip.nameCn}</b>
              <span style={{ fontSize: 11, color: '#999', marginLeft: 6 }}>{ip.name}</span>
            </div>
          </div>
          <Rate value={ip.potential} disabled style={{ fontSize: 12, color: '#E60012', flexShrink: 0 }} />
        </div>
        <div style={{ margin: '8px 0 4px' }}>
          {ip.styleTags.map(t => <Tag key={t} color="purple">{t}</Tag>)}
          <Tag>{ip.audience}</Tag>
        </div>
        <div className="ip-field"><span>适合品类</span>{ip.categories.join(' / ')}</div>
        <div className="ip-field"><span>代表角色</span>{ip.characters.join(' / ')}</div>
        <div className="ip-field"><span>设计资产</span>{ip.designAssets.join(' / ')}</div>
        <div className="ip-history">{ip.minisoHistory}</div>
      </div>
    </Card>
  );
}

// 名创内部 Insight Base：IP 资源库（机会 Agent 弹药库）+ 历史爆品 / 设计语言资产
export default function InsightBase() {
  const [audience, setAudience] = useState('全部');
  const [style, setStyle] = useState('全部');

  const filtered = useMemo(() => IP_RESOURCE.filter(ip =>
    (audience === '全部' || ip.audienceGroup === audience) &&
    (style === '全部' || ip.styleGroup === style)
  ), [audience, style]);

  return (
    <div>
      <h2>名创内部 · IP 资源库</h2>

      {/* 官方披露数据带 */}
      <div className="ip-stats-band">
        {IP_STATS.map(s => (
          <div key={s.label} className="ip-stat">
            <div className="ip-stat-value">{s.value}</div>
            <div className="ip-stat-label">{s.label}</div>
          </div>
        ))}
        <div className="ip-stats-note">数据来源：名创官方披露</div>
      </div>

      {/* IP 定位四象限 */}
      <Card
        title="IP 定位矩阵"
        size="small"
        extra={<span style={{ fontSize: 11, color: '#999' }}>基于历史商品特征的 AI 定位，仅作演示参考</span>}
        style={{ marginBottom: 16 }}
      >
        <IpMatrix />
      </Card>

      {/* 筛选条 */}
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 16 }}>
        <Segmented options={AUDIENCE_FILTERS} value={audience} onChange={setAudience} />
        <Segmented options={STYLE_FILTERS} value={style} onChange={setStyle} />
      </div>

      {/* IP 卡片网格 */}
      <Row gutter={[16, 16]}>
        {filtered.map(ip => (
          <Col xs={24} sm={12} lg={8} xl={6} key={ip.slug}>
            <IpCard ip={ip} />
          </Col>
        ))}
      </Row>

      {/* 历史爆品 + 设计语言（策展数据，保留原模块） */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={14}>
          <Card title="历史爆品特征库" size="small">
            {INSIGHT_BASE.hitProducts.map(p => (
              <Card key={p.name} size="small" style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b>{p.name}</b>
                  <span style={{ fontSize: 12 }}>爆品指数 <b style={{ color: '#E60012' }}>{p.index}</b></span>
                </div>
                <Progress percent={p.index} showInfo={false} strokeColor="#7A5FD0" size="small" style={{ margin: '4px 0' }} />
                <div>{p.factors.map(f => <Tag key={f} color="purple">{f}</Tag>)}</div>
                <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{p.note}</div>
              </Card>
            ))}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="名创设计语言" size="small">
            {INSIGHT_BASE.designLanguage.map(d => <Tag key={d} color="geekblue" style={{ marginBottom: 4 }}>{d}</Tag>)}
            <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>企划生成时作为品牌一致性约束注入创意设计模块</p>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

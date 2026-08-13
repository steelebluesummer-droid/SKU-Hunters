import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, Row, Col, Tag, Progress, Button } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import ProcessLog from '../../shared/components/ProcessLog';

const MODULE_TAG = { fontSize: 11, color: 'var(--purple-400)', marginLeft: 8 };

// 洞察模块外壳：标题 + 过程日志 + 日志跑完后显现内容
function InsightModule({ title, log, children }) {
  const [done, setDone] = useState(false);
  return (
    <Card title={<span>{title}<span style={MODULE_TAG}>AI 分析 · 样本可溯</span></span>} style={{ marginBottom: 16 }}>
      <ProcessLog lines={log || []} onDone={() => setDone(true)} />
      <div style={{ opacity: done ? 1 : 0, transition: 'opacity 0.5s', pointerEvents: done ? 'auto' : 'none' }}>
        {children}
      </div>
    </Card>
  );
}

// 安全默认值：所有数组/曲线/颜色字段兜底，避免 ECharts 因空数据抛错
function TrendRadar({ trendRadar = {} }) {
  const weeks = trendRadar.heatCurve?.weeks || [];
  const series = (trendRadar.heatCurve?.series || []).map(s => ({ ...s, type: 'line', smooth: true, showSymbol: false }));
  const heatOption = {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 16, top: 16, bottom: 48 },
    xAxis: { type: 'category', data: weeks },
    yAxis: { type: 'value', name: '热度' },
    series,
  };
  return (
    <Row gutter={16}>
      <Col xs={24} md={14}>
        {(trendRadar.signals || []).map(s => (
          <Card key={s.name} size="small" style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <b>{s.name}</b>
              <Tag color="red">{s.metric}</Tag>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', margin: '6px 0' }}>
              {s.period} · 关联领域：{(s.domains || []).map(d => <Tag key={d} style={{ fontSize: 11 }}>{d}</Tag>)}
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-action-primary)' }}>→ 机会判断：{s.opportunity}</div>
          </Card>
        ))}
      </Col>
      <Col xs={24} md={10}>
        <ReactECharts option={heatOption} style={{ height: 240 }} />
        <div style={{ marginTop: 8 }}>
          {(trendRadar.hotWords || []).map(w => <Tag key={w} color="purple" style={{ marginBottom: 4 }}>{w}</Tag>)}
        </div>
      </Col>
    </Row>
  );
}

function ConsumerVoice({ consumerVoice = {} }) {
  const painPoints = consumerVoice.painPoints || [];
  const maxCount = Math.max(1, ...painPoints.map(p => p.count || 0));
  const sceneOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['40%', '65%'], center: ['50%', '44%'],
      label: { fontSize: 11 },
      data: (consumerVoice.scenes || []).map(s => ({ name: s.name, value: s.value || 0 })),
    }],
  };
  return (
    <Row gutter={16}>
      <Col xs={24} md={9}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>TOP 痛点</div>
        {painPoints.map((p, i) => (
          <div key={p.text} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 12 }}>{i + 1}. {p.text} <span style={{ color: 'var(--color-text-muted)' }}>({p.count} 条)</span></div>
            <Progress percent={Math.round((p.count || 0) / maxCount * 100)} showInfo={false} strokeColor="var(--color-action-primary)" size="small" />
          </div>
        ))}
        <div style={{ fontSize: 13, fontWeight: 600, margin: '12px 0 8px' }}>使用场景分布</div>
        <ReactECharts option={sceneOption} style={{ height: 200 }} />
      </Col>
      <Col xs={24} md={15}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>消费者原声</div>
        {(consumerVoice.quotes || []).map(q => (
          <div key={q.text} className="quote-card">
            <div style={{ fontSize: 13 }}>"{q.text}"</div>
            <div className="quote-source">{q.source}</div>
          </div>
        ))}
        <Card size="small" style={{ background: 'var(--color-surface-alt)', border: '1px solid var(--color-border-strong)' }}>
          <b style={{ color: 'var(--color-action-primary)' }}>洞察总结：</b>{consumerVoice.summary || ''}
        </Card>
      </Col>
    </Row>
  );
}

function CompetitiveMap({ competitiveMap = {} }) {
  const gapZone = competitiveMap.gapZone;
  const gapX = gapZone?.x?.length >= 2 ? gapZone.x : [30, 60];
  const gapY = gapZone?.y?.length >= 2 ? gapZone.y : [7, 10];
  const scatterOption = {
    tooltip: { formatter: p => `${p.data[2]}<br/>价格：${p.data[0]} 元 · 设计感：${p.data[1]}` },
    grid: { left: 44, right: 24, top: 30, bottom: 36 },
    xAxis: { name: '价格（元）', type: 'value', max: 150 },
    yAxis: { name: '设计感', type: 'value', max: 10 },
    series: [{
      type: 'scatter', symbolSize: 18,
      itemStyle: { color: 'var(--color-action-primary)', opacity: 0.8 },
      label: { show: true, position: 'top', formatter: p => p.data[2], fontSize: 11 },
      data: (competitiveMap.products || []).map(p => [p.price, p.design, p.name]),
      markArea: gapZone ? {
        itemStyle: { color: 'var(--chart-accent-fill)' },
        label: { show: true, position: 'insideTop', color: 'var(--color-brand-accent)', fontSize: 11 },
        data: [[{ name: gapZone.label, xAxis: gapX[0], yAxis: gapY[0] }, { xAxis: gapX[1], yAxis: gapY[1] }]],
      } : undefined,
    }],
  };
  const priceBands = competitiveMap.priceBands || [];
  return (<>
    <Row gutter={16}>
      <Col xs={24} md={14}>
        <ReactECharts option={scatterOption} style={{ height: 300 }} />
      </Col>
      <Col xs={24} md={10}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>价格带分布</div>
        {priceBands.map(b => (
          <div key={b.band} style={{ marginBottom: 6, fontSize: 12 }}>
            {b.band}
            <Progress percent={b.pct || 0} showInfo={false} strokeColor="var(--purple-400)" size="small"
              style={{ display: 'inline-block', width: '60%', margin: '0 8px' }} />
            <b>{b.pct}%</b>
          </div>
        ))}
        <div style={{ fontSize: 13, fontWeight: 600, margin: '12px 0 8px' }}>卖点关键词</div>
        {(competitiveMap.sellingPoints || []).map(s => (
          <Tag key={s.word} style={{ marginBottom: 4 }}>{s.word} ×{s.count}</Tag>
        ))}
        {gapZone?.label && (
          <Card size="small" style={{ background: 'var(--surface-danger)', border: '1px solid var(--border-danger)', marginTop: 12 }}>
            <b style={{ color: 'var(--color-brand-accent)' }}>机会空白：</b>{gapZone.label}
          </Card>
        )}
      </Col>
    </Row>
    <CompetitorGallery products={competitiveMap.products || []} />
  </>
  );
}

// 竞品图板：图片 + 价格 + 卖点卡片墙
function CompetitorGallery({ products = [] }) {
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>竞品图板（图片 / 价格 / 卖点）</div>
      <Row gutter={[12, 12]}>
        {products.map(p => (
          <Col key={p.name} xs={12} sm={8} md={6} lg={4}>
            <Card size="small" cover={
              p.imageUrl
                ? <img src={p.imageUrl} alt={p.name} style={{ height: 100, objectFit: 'cover' }} />
                : <div style={{ height: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--color-bg)', color: 'var(--color-text-muted)', fontSize: 12 }}>{p.name.slice(0, 2)}</div>
            }>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</div>
              <div style={{ fontSize: 12, color: 'var(--color-brand-accent)' }}>¥{p.price} · 设计 {p.design}</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>{p.sellingPoint || '—'}</div>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}

// 洞察驾驶舱：props 驱动（数据由 TaskFlow 拉取后传入，不再 import 全局 mock）
export default function InsightCockpit({ insights }) {
  const {
    trendRadar = {},
    consumerVoice = {},
    competitiveMap = {},
    insightBase = {},
    trendGallery = {},
  } = insights || {};

  return (
    <div>
      <InsightModule title="趋势机会雷达" log={trendRadar.processLog}><TrendRadar trendRadar={trendRadar} /></InsightModule>
      <InsightModule title="Consumer Voice · 用户需求" log={consumerVoice.processLog}><ConsumerVoice consumerVoice={consumerVoice} /></InsightModule>
      <InsightModule title="Competitive Map · 竞品分析" log={competitiveMap.processLog}><CompetitiveMap competitiveMap={competitiveMap} /></InsightModule>

      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Card title={<span>名创内部资产<span style={MODULE_TAG}>策展数据</span></span>} size="small">
            {(insightBase.hitProducts || []).slice(0, 2).map(p => (
              <div key={p.name} style={{ marginBottom: 8, fontSize: 13 }}>
                <b>{p.name}</b> <Tag color="red">指数 {p.index}</Tag>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{(p.factors || []).join(' · ')}</div>
              </div>
            ))}
            <Link to="/insight-base"><Button type="link" size="small" style={{ padding: 0 }}>查看完整 Insight Base <ArrowRightOutlined /></Button></Link>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title={<span>流行元素<span style={MODULE_TAG}>策展数据</span></span>} size="small">
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              {(trendGallery.colors || []).slice(0, 5).map(c => (
                <div key={c.name} title={`${c.name} · ${c.source}`}
                  style={{ width: 32, height: 32, borderRadius: 8, background: c.hex || 'var(--gray-200)', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.05)' }} />
              ))}
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
              {(trendGallery.patterns || []).map(p => p.name).join(' · ')} ｜ {(trendGallery.shapes || []).map(s => s.name).join(' · ')}
            </div>
            <Link to="/trend-gallery"><Button type="link" size="small" style={{ padding: 0 }}>查看完整 Trend Gallery <ArrowRightOutlined /></Button></Link>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

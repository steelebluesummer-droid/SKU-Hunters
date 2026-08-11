import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, Row, Col, Tag, Progress, Button } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import ProcessLog from './ProcessLog';
import { TREND_RADAR, CONSUMER_VOICE, COMPETITIVE_MAP, INSIGHT_BASE, TREND_GALLERY } from '../mock/fanData';

const MODULE_TAG = { fontSize: 11, color: '#b7a8f5', marginLeft: 8 };

// 洞察模块外壳：标题 + 过程日志 + 日志跑完后显现内容
function InsightModule({ title, log, children }) {
  const [done, setDone] = useState(false);
  return (
    <Card title={<span>{title}<span style={MODULE_TAG}>AI 分析 · 样本可溯</span></span>} style={{ marginBottom: 16 }}>
      <ProcessLog lines={log} onDone={() => setDone(true)} />
      <div style={{ opacity: done ? 1 : 0, transition: 'opacity 0.5s', pointerEvents: done ? 'auto' : 'none' }}>
        {children}
      </div>
    </Card>
  );
}

function TrendRadar() {
  const heatOption = {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 16, top: 16, bottom: 48 },
    xAxis: { type: 'category', data: TREND_RADAR.heatCurve.weeks },
    yAxis: { type: 'value', name: '热度' },
    series: TREND_RADAR.heatCurve.series.map(s => ({ ...s, type: 'line', smooth: true, showSymbol: false })),
  };
  return (
    <Row gutter={16}>
      <Col span={14}>
        {TREND_RADAR.signals.map(s => (
          <Card key={s.name} size="small" style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <b>{s.name}</b>
              <Tag color="red">{s.metric}</Tag>
            </div>
            <div style={{ fontSize: 12, color: '#666', margin: '6px 0' }}>
              {s.period} · 关联领域：{s.domains.map(d => <Tag key={d} style={{ fontSize: 11 }}>{d}</Tag>)}
            </div>
            <div style={{ fontSize: 12, color: '#7a5fd0' }}>→ 机会判断：{s.opportunity}</div>
          </Card>
        ))}
      </Col>
      <Col span={10}>
        <ReactECharts option={heatOption} style={{ height: 240 }} />
        <div style={{ marginTop: 8 }}>
          {TREND_RADAR.hotWords.map(w => <Tag key={w} color="purple" style={{ marginBottom: 4 }}>{w}</Tag>)}
        </div>
      </Col>
    </Row>
  );
}

function ConsumerVoice() {
  const maxCount = Math.max(...CONSUMER_VOICE.painPoints.map(p => p.count));
  const sceneOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['40%', '65%'], center: ['50%', '44%'],
      label: { fontSize: 11 },
      data: CONSUMER_VOICE.scenes.map(s => ({ name: s.name, value: s.value })),
    }],
  };
  return (
    <Row gutter={16}>
      <Col span={9}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>TOP 痛点（823 条社媒样本）</div>
        {CONSUMER_VOICE.painPoints.map((p, i) => (
          <div key={p.text} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 12 }}>{i + 1}. {p.text} <span style={{ color: '#999' }}>({p.count} 条)</span></div>
            <Progress percent={Math.round(p.count / maxCount * 100)} showInfo={false} strokeColor="#7a5fd0" size="small" />
          </div>
        ))}
        <div style={{ fontSize: 13, fontWeight: 600, margin: '12px 0 8px' }}>使用场景分布</div>
        <ReactECharts option={sceneOption} style={{ height: 200 }} />
      </Col>
      <Col span={15}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>消费者原声</div>
        {CONSUMER_VOICE.quotes.map(q => (
          <div key={q.text} className="quote-card">
            <div style={{ fontSize: 13 }}>"{q.text}"</div>
            <div className="quote-source">{q.source}</div>
          </div>
        ))}
        <Card size="small" style={{ background: '#f6f3ff', border: '1px solid #d9ccff' }}>
          <b style={{ color: '#7a5fd0' }}>洞察总结：</b>{CONSUMER_VOICE.summary}
        </Card>
      </Col>
    </Row>
  );
}

function CompetitiveMap() {
  const scatterOption = {
    tooltip: { formatter: p => `${p.data[2]}<br/>价格：${p.data[0]} 元 · 设计感：${p.data[1]}` },
    grid: { left: 44, right: 24, top: 30, bottom: 36 },
    xAxis: { name: '价格（元）', type: 'value', max: 150 },
    yAxis: { name: '设计感', type: 'value', max: 10 },
    series: [{
      type: 'scatter', symbolSize: 18,
      itemStyle: { color: '#7a5fd0', opacity: 0.8 },
      label: { show: true, position: 'top', formatter: p => p.data[2], fontSize: 11 },
      data: COMPETITIVE_MAP.products.map(p => [p.price, p.design, p.name]),
      markArea: {
        itemStyle: { color: 'rgba(230, 0, 18, 0.06)' },
        label: { show: true, position: 'insideTop', color: '#e60012', fontSize: 11 },
        data: [[{ name: COMPETITIVE_MAP.gapZone.label, xAxis: COMPETITIVE_MAP.gapZone.x[0], yAxis: COMPETITIVE_MAP.gapZone.y[0] },
                { xAxis: COMPETITIVE_MAP.gapZone.x[1], yAxis: COMPETITIVE_MAP.gapZone.y[1] }]],
      },
    }],
  };
  const maxPct = Math.max(...COMPETITIVE_MAP.priceBands.map(b => b.pct));
  return (
    <Row gutter={16}>
      <Col span={14}>
        <ReactECharts option={scatterOption} style={{ height: 300 }} />
      </Col>
      <Col span={10}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>价格带分布（217 个在售 SKU）</div>
        {COMPETITIVE_MAP.priceBands.map(b => (
          <div key={b.band} style={{ marginBottom: 6, fontSize: 12 }}>
            {b.band}
            <Progress percent={b.pct} showInfo={false} strokeColor="#b7a8f5" size="small"
              style={{ display: 'inline-block', width: '60%', margin: '0 8px' }} />
            <b>{b.pct}%</b>
          </div>
        ))}
        <div style={{ fontSize: 13, fontWeight: 600, margin: '12px 0 8px' }}>卖点关键词</div>
        {COMPETITIVE_MAP.sellingPoints.map(s => (
          <Tag key={s.word} style={{ marginBottom: 4 }}>{s.word} ×{s.count}</Tag>
        ))}
        <Card size="small" style={{ background: '#fff5f5', border: '1px solid #ffcdd2', marginTop: 12 }}>
          <b style={{ color: '#e60012' }}>机会空白：</b>50 元以内 × 高颜值 × IP 化——当前无竞品占据
        </Card>
      </Col>
    </Row>
  );
}

// 洞察驾驶舱：趋势洞察 / 用户洞察 / 竞品分析 + 名创内部、流行元素摘要
export default function InsightCockpit() {
  return (
    <div>
      <InsightModule title="趋势机会雷达" log={TREND_RADAR.processLog}><TrendRadar /></InsightModule>
      <InsightModule title="Consumer Voice · 用户需求" log={CONSUMER_VOICE.processLog}><ConsumerVoice /></InsightModule>
      <InsightModule title="Competitive Map · 竞品分析" log={COMPETITIVE_MAP.processLog}><CompetitiveMap /></InsightModule>

      <Row gutter={16}>
        <Col span={12}>
          <Card title={<span>名创内部资产<span style={MODULE_TAG}>策展数据</span></span>} size="small">
            {INSIGHT_BASE.hitProducts.slice(0, 2).map(p => (
              <div key={p.name} style={{ marginBottom: 8, fontSize: 13 }}>
                <b>{p.name}</b> <Tag color="red">指数 {p.index}</Tag>
                <div style={{ fontSize: 12, color: '#666' }}>{p.factors.join(' · ')}</div>
              </div>
            ))}
            <Link to="/insight-base"><Button type="link" size="small" style={{ padding: 0 }}>查看完整 Insight Base <ArrowRightOutlined /></Button></Link>
          </Card>
        </Col>
        <Col span={12}>
          <Card title={<span>流行元素<span style={MODULE_TAG}>策展数据</span></span>} size="small">
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              {TREND_GALLERY.colors.slice(0, 5).map(c => (
                <div key={c.name} title={`${c.name} · ${c.source}`}
                  style={{ width: 32, height: 32, borderRadius: 8, background: c.hex, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.05)' }} />
              ))}
            </div>
            <div style={{ fontSize: 12, color: '#666' }}>
              {TREND_GALLERY.patterns.map(p => p.name).join(' · ')} ｜ {TREND_GALLERY.shapes.map(s => s.name).join(' · ')}
            </div>
            <Link to="/trend-gallery"><Button type="link" size="small" style={{ padding: 0 }}>查看完整 Trend Gallery <ArrowRightOutlined /></Button></Link>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

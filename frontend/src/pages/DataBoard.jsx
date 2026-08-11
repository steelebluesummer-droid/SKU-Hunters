import { Card, Row, Col, Table, Tag, Progress } from 'antd';
import ReactECharts from 'echarts-for-react';
import { DATA_BOARD, COMPETITIVE_MAP } from '../mock/fanData';

// 数据看板：未经筛选的大盘全貌（对应任务中心里"按企划主题筛过的洞察"的上一层）
export default function DataBoard() {
  const rankOption = {
    tooltip: {},
    grid: { left: 70, right: 30, top: 16, bottom: 24 },
    xAxis: { type: 'value', name: '热度' },
    yAxis: { type: 'category', data: DATA_BOARD.categoryRank.map(c => c.name).reverse() },
    series: [{ type: 'bar', data: DATA_BOARD.categoryRank.map(c => c.heat).reverse(), itemStyle: { color: '#e60012', borderRadius: [0, 6, 6, 0] }, barWidth: 16 }],
  };
  const voiceOption = {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 44, right: 16, top: 16, bottom: 44 },
    xAxis: { type: 'category', data: DATA_BOARD.voiceTrend.weeks },
    yAxis: { type: 'value', name: '声量' },
    series: [
      { name: '小红书', type: 'line', smooth: true, data: DATA_BOARD.voiceTrend.xhs, itemStyle: { color: '#e60012' } },
      { name: '抖音', type: 'line', smooth: true, data: DATA_BOARD.voiceTrend.douyin, itemStyle: { color: '#7a5fd0' } },
    ],
  };
  const columns = [
    { title: '排名', dataIndex: 'rank', width: 60 },
    { title: '商品', dataIndex: 'name' },
    { title: '价格', dataIndex: 'price', render: v => `¥${v}`, width: 80 },
    { title: '核心卖点', dataIndex: 'point', render: v => <Tag>{v}</Tag> },
    { title: '月销指数', dataIndex: 'sales', width: 160, render: v => <Progress percent={v} showInfo={false} strokeColor="#e60012" size="small" /> },
  ];

  return (
    <div>
      <h2>数据看板 · 品类大盘</h2>
      <Row gutter={[16, 16]}>
        <Col span={10}>
          <Card title="品类热度排行" size="small">
            <ReactECharts option={rankOption} style={{ height: 260 }} />
          </Card>
        </Col>
        <Col span={14}>
          <Card title="社媒声量趋势（小风扇品类）" size="small">
            <ReactECharts option={voiceOption} style={{ height: 260 }} />
          </Card>
        </Col>
        <Col span={14}>
          <Card title="热销商品榜" size="small">
            <Table columns={columns} dataSource={DATA_BOARD.hotProducts} rowKey="rank" pagination={false} size="small" />
          </Card>
        </Col>
        <Col span={10}>
          <Card title="价格带分布（在售 SKU 217 个）" size="small">
            {COMPETITIVE_MAP.priceBands.map(b => (
              <div key={b.band} style={{ marginBottom: 10, fontSize: 13 }}>
                {b.band}
                <Progress percent={b.pct} showInfo={false} strokeColor="#7a5fd0" size="small"
                  style={{ display: 'inline-block', width: '62%', margin: '0 10px' }} />
                <b>{b.pct}%</b>
              </div>
            ))}
            <p style={{ fontSize: 12, color: '#999', marginTop: 12 }}>数据源：电商公开样本（冻结 fixture，可切换实时）</p>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

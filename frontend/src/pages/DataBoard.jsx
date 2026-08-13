import { useEffect, useState } from 'react';
import { Card, Row, Col, Table, Tag, Progress, Spin, Alert, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { getDataBoard } from '../api';

// 数据看板：未经筛选的大盘全貌（对应任务中心里"按企划主题筛过的洞察"的上一层）
// 只读真实后端 /data-board 数据，失败显式报错并提供重试，不静默回退 mock。
export default function DataBoard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getDataBoard()
      .then(d => setData(d || {}))
      .catch(e => setError(e?.message || '数据看板加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '60px 0' }}><Spin tip="正在加载大盘数据…" /></div>;
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

  // 安全默认值：所有数组字段在缺失时退化为空数组，图表不因 None 崩溃
  const categoryRank = data.categoryRank || [];
  const hotProducts = data.hotProducts || [];
  const priceBands = data.priceBands || [];
  const voiceTrend = data.voiceTrend || { weeks: [], xhs: [], douyin: [] };

  const rankOption = {
    tooltip: {},
    grid: { left: 70, right: 30, top: 16, bottom: 24 },
    xAxis: { type: 'value', name: '热度' },
    yAxis: { type: 'category', data: categoryRank.map(c => c.name).reverse() },
    series: [{ type: 'bar', data: categoryRank.map(c => c.heat).reverse(), itemStyle: { color: '#e60012', borderRadius: [0, 6, 6, 0] }, barWidth: 16 }],
  };
  const voiceOption = {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 44, right: 16, top: 16, bottom: 44 },
    xAxis: { type: 'category', data: voiceTrend.weeks },
    yAxis: { type: 'value', name: '声量' },
    series: [
      { name: '小红书', type: 'line', smooth: true, data: voiceTrend.xhs, itemStyle: { color: '#e60012' } },
      { name: '抖音', type: 'line', smooth: true, data: voiceTrend.douyin, itemStyle: { color: '#7a5fd0' } },
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
            <Table columns={columns} dataSource={hotProducts} rowKey="rank" pagination={false} size="small" />
          </Card>
        </Col>
        <Col span={10}>
          <Card title="价格带分布" size="small">
            {priceBands.length === 0 ? (
              <p style={{ fontSize: 12, color: '#999' }}>暂无价格带数据</p>
            ) : (
              priceBands.map(b => (
                <div key={b.band} style={{ marginBottom: 10, fontSize: 13 }}>
                  {b.band}
                  <Progress percent={b.pct} showInfo={false} strokeColor="#7a5fd0" size="small"
                    style={{ display: 'inline-block', width: '62%', margin: '0 10px' }} />
                  <b>{b.pct}%</b>
                </div>
              ))
            )}
            <p style={{ fontSize: 12, color: '#999', marginTop: 12 }}>数据源：电商公开样本（冻结 fixture，可切换实时）</p>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

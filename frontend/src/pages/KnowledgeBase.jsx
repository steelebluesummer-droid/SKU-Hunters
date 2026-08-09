import { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Tag, Table } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ExperimentOutlined } from '@ant-design/icons';
import { api } from '../api';

export default function KnowledgeBase() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.listReviews().then(r => {
      const rs = r.reviews.filter(x => x.status === 'approved' || x.status === 'rejected');
      const approved = rs.filter(x => x.status === 'approved');
      setData({
        total: rs.length,
        approved: approved.length,
        rejected: rs.filter(x => x.status === 'rejected').length,
        rate: rs.length ? Math.round(approved.length / rs.length * 100) : 0,
        retroAvg: Math.round(rs.reduce((s, x) => s + x.retro_turns, 0) / Math.max(rs.length, 1)),
        badCases: rs.filter(x => x.archive?.status === 'rejected'),
      });
    }).catch(() => {});
  }, []);

  if (!data) return null;

  return (
    <div>
      <h2>知识库看板（学习官叙事）</h2>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card><Statistic title="评审总数" value={data.total} prefix={<ExperimentOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title="AI 采纳率" value={data.rate} suffix="%" prefix={<CheckCircleOutlined />} valueStyle={{ color: data.rate >= 60 ? '#3f8600' : '#cf1322' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="平均复盘轮数" value={data.retroAvg} suffix="轮/会" /></Card></Col>
        <Col span={6}><Card><Statistic title="Bad Case" value={data.rejected} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#cf1322' }} /></Card></Col>
      </Row>
      {data.badCases.length > 0 && (
        <Card title={`Bad Case 负样本 (${data.badCases.length})`} style={{ marginTop: 16 }}>
          <Table rowKey="session_id" dataSource={data.badCases} columns={[
            { title: '品类', dataIndex: 'category' }, { title: '市场', dataIndex: 'market' },
            { title: '复盘轮数', dataIndex: 'retro_turns' },
            { title: '创建时间', dataIndex: 'created_at', render: v => v?.slice(0, 19).replace('T', ' ') },
          ]} pagination={false} size="small" />
        </Card>
      )}
    </div>
  );
}

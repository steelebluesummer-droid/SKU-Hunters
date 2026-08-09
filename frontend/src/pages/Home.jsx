import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Tag, Button, Spin, Empty } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { api } from '../api';

const STATUS = { running: '处理中', awaiting_human: '⚠️ 等你决策', approved: '✅ 已通过', rejected: '❌ 已否决', failed: '💥 失败', completed: '已归档' };
const STATUS_COLOR = { approved: 'green', rejected: 'red', running: 'blue', awaiting_human: 'orange', failed: 'red', completed: 'default' };

export default function Home() {
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    api.listReviews().then(r => setReviews(r.reviews)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;
  if (!reviews.length) return (
    <Empty description="还没有评审记录">
      <Button type="primary" icon={<PlusOutlined />} onClick={() => nav('/new')}>发起第一次评审</Button>
    </Empty>
  );

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>评审历史</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => nav('/new')}>新建评审</Button>
      </div>
      <Row gutter={[16, 16]}>
        {reviews.map(r => (
          <Col span={8} key={r.session_id}>
            <Card hoverable onClick={() => nav(`/reviews/${r.session_id}`)}
              title={<><Tag color={STATUS_COLOR[r.status]}>{STATUS[r.status]}</Tag> {r.category}</>}
              size="small">
              <p>市场：{r.market} &nbsp;|&nbsp; 复盘 {r.retro_turns} 轮</p>
              {r.archive?.status === 'rejected' && <Tag color="red">bad case</Tag>}
              <p style={{ color: '#999', fontSize: 12, marginTop: 8 }}>{r.created_at?.slice(0, 19).replace('T', ' ')}</p>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}

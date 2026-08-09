import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { HomeOutlined, PlusOutlined, BarChartOutlined } from '@ant-design/icons';
import Home from './pages/Home';
import NewReview from './pages/NewReview';
import ReviewDetail from './pages/ReviewDetail';
import KnowledgeBase from './pages/KnowledgeBase';

const { Sider, Content } = Layout;

const NAV = [
  { key: '/', icon: <HomeOutlined />, label: <Link to="/">任务中心</Link> },
  { key: '/new', icon: <PlusOutlined />, label: <Link to="/new">新建评审</Link> },
  { key: '/kb', icon: <BarChartOutlined />, label: <Link to="/kb">知识库</Link> },
];

export default function App() {
  const { pathname } = useLocation();
  const selected = '/' + (pathname.split('/')[1] || '');
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={200} style={{ background: '#fff' }}>
        <div style={{ height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 16 }}>
          SKU Hunters
        </div>
        <Menu mode="inline" selectedKeys={[selected]} items={NAV} />
      </Sider>
      <Content style={{ padding: 24, background: '#f5f5f5' }}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/new" element={<NewReview />} />
          <Route path="/reviews/:id" element={<ReviewDetail />} />
          <Route path="/kb" element={<KnowledgeBase />} />
        </Routes>
      </Content>
    </Layout>
  );
}

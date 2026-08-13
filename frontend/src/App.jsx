import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { HomeOutlined, BarChartOutlined, ShopOutlined, BgColorsOutlined } from '@ant-design/icons';
import TaskCenter from './features/plans/pages/TaskCenter';
import NewPlan from './features/plans/pages/NewPlan';
import TaskFlow from './features/plans/pages/TaskFlow';
import DataBoard from './pages/DataBoard';
import InsightBase from './pages/InsightBase';
import TrendGallery from './pages/TrendGallery';

const { Sider, Content } = Layout;

const NAV = [
  { key: '/', icon: <HomeOutlined />, label: <Link to="/">任务中心</Link> },
  { key: '/dashboard', icon: <BarChartOutlined />, label: <Link to="/dashboard">数据看板</Link> },
  { key: '/insight-base', icon: <ShopOutlined />, label: <Link to="/insight-base">名创内部</Link> },
  { key: '/trend-gallery', icon: <BgColorsOutlined />, label: <Link to="/trend-gallery">流行元素板</Link> },
];

export default function App() {
  const { pathname } = useLocation();
  const selected = pathname.startsWith('/tasks') || pathname.startsWith('/new') ? '/' : '/' + (pathname.split('/')[1] || '');
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={200} breakpoint="lg" collapsedWidth={0} style={{ background: '#fff' }}>
        <div style={{ height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 15 }}>
          SKU Hunters · 企划工作室
        </div>
        <Menu mode="inline" selectedKeys={[selected]} items={NAV} />
      </Sider>
      <Content style={{ padding: 24, background: '#f5f5f5' }}>
        <Routes>
          <Route path="/" element={<TaskCenter />} />
          <Route path="/new" element={<NewPlan />} />
          <Route path="/tasks/:id" element={<TaskFlow />} />
          <Route path="/dashboard" element={<DataBoard />} />
          <Route path="/insight-base" element={<InsightBase />} />
          <Route path="/trend-gallery" element={<TrendGallery />} />
        </Routes>
      </Content>
    </Layout>
  );
}

import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { router } from './app/router';
import './styles.css';

// main 只挂 ConfigProvider + RouterProvider；路由与外壳收敛在 app/router.jsx + app/AppShell.jsx。
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#7a5fd0' } }}>
      <RouterProvider router={router} />
    </ConfigProvider>
  </React.StrictMode>
);

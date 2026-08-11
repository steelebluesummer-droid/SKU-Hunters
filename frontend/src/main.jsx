import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import { bootstrapRemoteFixtures } from './api';
import './styles.css';

// 先尝试从后端拉取冻结数据覆盖本地 mock（1.5s 超时兜底），再渲染
bootstrapRemoteFixtures().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#e60012' } }}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ConfigProvider>
    </React.StrictMode>
  );
});

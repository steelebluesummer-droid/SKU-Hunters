import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发模式：前端 5173，/api 代理到后端 8000（uvicorn app.main:app --reload）
// 生产模式：npm run build 后由后端 StaticFiles 托管，同源无跨域
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})

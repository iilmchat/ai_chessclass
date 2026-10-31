import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В compose API_PROXY=http://api:8020; локально — дефолт на api-порт хоста (ADR-013).
const apiProxy = process.env.API_PROXY ?? 'http://localhost:8020';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: Number(process.env.WEB_PORT ?? 3200),
    strictPort: true,
    proxy: {
      '/api': { target: apiProxy, changeOrigin: true },
    },
  },
});

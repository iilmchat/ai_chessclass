import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В compose API_PROXY=http://api:8020; локально — дефолт на api-порт хоста (ADR-013).
const apiProxy = process.env.API_PROXY ?? 'http://localhost:8020';

// Бренд: версия из package.json (npm выставляет npm_package_version при start/build),
// стадия — APP_STAGE (Docker build-arg, S-58) или mode (production -> prod, development -> dev).
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? '0.3.0'),
    __APP_STAGE__: JSON.stringify(
      process.env.APP_STAGE ||
        (mode === 'production' ? 'prod' : mode === 'development' ? 'dev' : mode),
    ),
  },
  server: {
    host: '0.0.0.0',
    port: Number(process.env.WEB_PORT ?? 3200),
    strictPort: true,
    proxy: {
      '/api': { target: apiProxy, changeOrigin: true },
    },
  },
}));

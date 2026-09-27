import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// En desarrollo, Vite sirve el front en :5173 y reenvía /api (HTTP y WebSocket) al
// backend FastAPI en :8765. En producción el backend sirve frontend/dist él mismo.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', ws: true, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    restoreMocks: true,
  },
});

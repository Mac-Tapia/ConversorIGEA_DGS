import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { rutasFrontend } from './scripts/runtime-paths.mjs';

// En desarrollo, Vite sirve el front en :5173 y reenvía /api (HTTP y WebSocket) al
// backend FastAPI en :8765. En producción el backend sirve frontend/dist él mismo.
export default defineConfig({
  cacheDir: rutasFrontend(fileURLToPath(new URL('.', import.meta.url))).cache,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', ws: true, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});

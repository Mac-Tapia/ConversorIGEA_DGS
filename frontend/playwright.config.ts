import { defineConfig } from '@playwright/test';

const port = Number(process.env.IGEA_E2E_PORT ?? 8876);

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: 'msedge',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `..\\..\\.venv\\Scripts\\python.exe tests\\web_fixture_server.py --port ${port}`,
    cwd: '..',
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});

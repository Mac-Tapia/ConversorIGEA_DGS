/**
 * 111:RF-16 — configuración de los recorridos en navegador real.
 *
 * Se corre desde `frontend/`, con la dependencia de desarrollo de la web (sin paquete aparte) y la web ya compilada:
 *   npm run build
 *   npx playwright test -c e2e/playwright.config.ts linea_base.spec.ts
 * `preparar.mjs` arranca una web de prueba aislada con un espacio sintético sorteado y dice la semilla.
 * Una sola web para todos: los recorridos van en serie. Cada uno corre en claro y en oscuro.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  globalSetup: './preparar.mjs',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  outputDir: 'resultados/artefactos',
  reporter: [['list'], ['json', { outputFile: 'resultados/informe.json' }]],
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 1000 },
    locale: 'es-PE',
    // Sin «serviceWorkers: 'block'»: Playwright toca navigator.serviceWorker en cada marco y en el del plano
    // (sandbox sin allow-same-origin) eso lanza un SecurityError que no es de la web. La web no registra ninguno y
    // sin_red.ts ya corta toda salida.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'claro', use: { colorScheme: 'light' } },
    { name: 'oscuro', use: { colorScheme: 'dark' } },
  ],
});

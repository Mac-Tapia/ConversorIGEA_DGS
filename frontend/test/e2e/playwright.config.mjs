/**
 * Plan Maestro V1, F-12 (spec 086): recorridos F01–F06 en un navegador real, con axe-core y sin red.
 *
 * Levanta su propia web, aislada: otro puerto (8799 por defecto, nunca el 8765 del operador), su carpeta de
 * espacios y de sesiones en un temporal, y la compilación de este checkout (`npm run build` antes). No reutiliza
 * ninguna web que ya esté escuchando. Uso, desde frontend/:
 *
 *   npm run build
 *   npx playwright test -c test/e2e/playwright.config.mjs
 *
 * Variables: CSG_E2E_PUERTO, CSG_E2E_PYTHON (el python con las dependencias del servidor), CSG_E2E_CANAL (navegador
 * instalado en el sistema: msedge por defecto, chrome o «chromium» para el de Playwright), CSG_E2E_DIR (carpeta
 * temporal) y CSG_E2E_EVIDENCIA (dónde quedan capturas y resultados de axe, por SHA; por defecto output/e2e).
 */
import { defineConfig } from '@playwright/test';
import { existsSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { carpetaLibrosE2E, carpetaNubeE2E, evidenciaDe, puertoE2E, puertoLibrosE2E, puertoNubeE2E,
  pythonServidor } from './entorno.mjs';

const FRONT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const RAIZ = resolve(FRONT, '..');
const puerto = puertoE2E();
const carpeta = process.env.CSG_E2E_DIR || join(tmpdir(), `csg-e2e-${puerto}`);
mkdirSync(join(carpeta, 'sesiones'), { recursive: true });
const puertoNube = puertoNubeE2E();
const carpetaNube = carpetaNubeE2E();
mkdirSync(join(carpetaNube, 'sesiones'), { recursive: true });
const puertoLibros = puertoLibrosE2E();
const carpetaLibros = carpetaLibrosE2E();
mkdirSync(join(carpetaLibros, 'sesiones'), { recursive: true });

/** El python del servidor (entorno.mjs): el del checkout o, en un worktree sin .venv, el del checkout primario. */
const python = () => pythonServidor(RAIZ);

if (!existsSync(join(FRONT, 'dist', 'index.html'))) {
  throw new Error('Falta frontend/dist: ejecute «npm run build» antes de los recorridos.');
}

const canal = process.env.CSG_E2E_CANAL || 'msedge';

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.e2e\.mjs$/,
  // F02 (simulación sobre el plano) vive en el arnés de la 111: frontend/e2e/plano.spec.ts (111 T16). Un recorrido que
  // aún no pueda correr iría aquí, en «testIgnore», con su motivo encima; nunca omitido (sin_omitidas.mjs).
  // Una sola web y un solo carril del motor: los recorridos van en serie.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 30_000 },
  forbidOnly: true,
  outputDir: join(evidenciaDe(FRONT), 'playwright'),
  // sin_omitidas.mjs: un recorrido omitido, en «fixme», inestable o sin correr deja la corrida en fallo.
  reporter: [['list'], ['json', { outputFile: join(evidenciaDe(FRONT), 'resultado.json') }], ['./sin_omitidas.mjs']],
  use: {
    baseURL: `http://127.0.0.1:${puerto}`,
    ...(canal === 'chromium' ? {} : { channel: canal }),
    locale: 'es-PE',
    viewport: { width: 1366, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    // Sin «serviceWorkers: 'block'»: Playwright toca navigator.serviceWorker en cada marco y en el de la vista
    // previa (sandbox sin allow-same-origin) eso lanza un SecurityError que no es de la web. La web no registra
    // ninguno y la red ya va cortada.
  },
  // 109 T16 (f07): la web de los recorridos nunca lee un config/nube.json del equipo (heredado del checkout primario):
  // apunta a uno que no existe, así siempre dice «Sin cuenta conectada…» y ningún recorrido llega a una cuenta real.
  webServer: [servidor(`-m convertersmartgrid.presentacion.web`, puerto, carpeta,
    { CSG_NUBE_CONFIG: join(carpeta, 'sin_nube', 'nube.json') }),
    // 109 T19: la misma web con la nube simulada (tests/e2e_web_nube_simulada.py), en el puerto siguiente y con sus
    // propias carpetas, para el recorrido del selector único (f05) y el de Nube y Correo (f07, 109 T16). Los demás
    // recorridos no la usan.
    servidor(`"${join(RAIZ, 'tests', 'e2e_web_nube_simulada.py')}"`, puertoNube, carpetaNube),
    // 104 T6: la misma web con la vigilancia de libros nuevos encendida y un intervalo corto, para el recorrido F10.
    servidor(`-m convertersmartgrid.presentacion.web`, puertoLibros, carpetaLibros,
      { CSG_LIBROS_NUEVOS: '1', CSG_LIBROS_INTERVALO_MIN: '0.05', CSG_DATASET_REPOSO_MIN: '0' })],
});

function servidor(programa, puertoDe, carpetaDe, extra = {}) {
  return {
    command: `"${python()}" ${programa} --host 127.0.0.1 --port ${puertoDe} --no-browser`,
    cwd: RAIZ,
    url: `http://127.0.0.1:${puertoDe}/`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
    env: {
      ...process.env,
      PYTHONPATH: join(RAIZ, 'src'),
      PYTHONUTF8: '1',
      CSG_WEB_FRONTEND: join(FRONT, 'dist'),
      CSG_WEB_SESIONES: join(carpetaDe, 'sesiones'),
      // Espacios, registro y trabajos en el temporal: nada del operador se toca. LOCALAPPDATA solo lleva las sesiones,
      // la caché y los trabajos; los espacios iban a <checkout>/../.convertersmartgrid-runtime (runtime_paths), así que
      // la raíz de ejecución y la de los espacios se fijan también aquí.
      LOCALAPPDATA: carpetaDe,
      CSG_RUNTIME_HOME: join(carpetaDe, 'runtime'),
      CSG_WEB_DATA: join(carpetaDe, 'web'),
      // 086 T79: el perfil activo también en el temporal. Lanzada desde el checkout primario, la web leía el
      // config/perfil_empresa.json real del equipo y F06 («empieza sin perfil de empresa») fallaba el 25-11; y el perfil
      // sintético que F06 carga y quita al terminar habría caído encima del del operador.
      CSG_PERFIL_EMPRESA: join(carpetaDe, 'config', 'perfil_empresa.json'),
      // 086:RF-22: sin red. En la edición de desarrollo las teselas salen encendidas por defecto y el mapa de cargas del
      // PIDE pedía su fondo a openstreetmap.org (la guardia lo cazó en F03); como el plano, la web de prueba las apaga.
      CSG_SALIDA_TESELAS: '0',
      // Sin vigilancias de fondo: el recorrido ve solo lo que pide.
      CSG_ASISTENTE_VIGILANCIA: '0',
      CSG_WEB_RELANZAR: '0',
      CSG_LIBROS_NUEVOS: '0',
      CSG_ASISTENTE_VECTORES: '0',
      // Sin modelo (CSG_E2E_SIN_MODELO=1), tampoco el servidor habla con Ollama: el intérprete preguntaba en cada orden
      // de F04 y cargaba el modelo en la máquina (18-11, 0,7 GB en medio de una e2e).
      ...(process.env.CSG_E2E_SIN_MODELO === '1' ? { CSG_ASISTENTE_OLLAMA: '0' } : {}),
      ...extra,
    },
  };
}

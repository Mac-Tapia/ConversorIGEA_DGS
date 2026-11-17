import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Spec 107 T13 (P10d): la pestaña «Estudio PIT». Sin navegador: el panel pintado con su contexto, la matriz de cobertura
// de las rutas del PIT (cada ruta con su llamada, su control en la pantalla y su prueba del servidor) y los años.
const RAIZ = fileURLToPath(new URL('../', import.meta.url));
const SRC = join(RAIZ, 'src');
const PANEL = join(SRC, 'features', 'pit', 'EstudioPit.tsx');
const API = join(SRC, 'api', 'pit.ts');

/** 107 T13: la matriz de cobertura. Ruta → función de api/pit.ts → lo que la pide en la pantalla → prueba del servidor. */
const MATRIZ = {
  '/api/pit/areas': { llamada: 'areas', pantalla: 'Área de demanda', prueba: 'test_rutas_propias_capacidades_y_areas' },
  '/api/pit/capacidades': { llamada: 'capacidades', pantalla: 'Motor', prueba: 'test_rutas_propias_capacidades_y_areas' },
  '/api/pit/entradas': { llamada: 'entradas', pantalla: 'Libro de la red',
    prueba: 'test_107_t13_entradas_admite_los_cuatro_formatos_de_excel' },
  '/api/pit/diagnostico': { llamada: 'diagnostico', pantalla: 'Diagnosticar', prueba: 'test_diagnostico_en_cola_con_progreso' },
  '/api/pit/expediente': { llamada: 'expediente', pantalla: 'Armar el expediente',
    prueba: 'test_expediente_en_cola_de_punta_a_punta' },
  '/api/pit/observaciones': { llamada: 'observaciones', pantalla: 'Registrar observaciones',
    prueba: 'test_fuera_del_espacio_y_observaciones' },
};

let modulo;
async function cargar() {
  if (modulo) return modulo;
  assert.ok(existsSync(PANEL), 'falta src/features/pit/EstudioPit.tsx (107 T13)');
  assert.ok(existsSync(API), 'falta src/api/pit.ts (107 T13)');
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { EstudioPit } from './src/features/pit/EstudioPit';
        export { leerAnios, pit, LIBROS_RED } from './src/api/pit';
        export * from './src/shared/pasoDeTrabajo';
        export const pintar = (jobs = {}, active = {}) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
          ws: { id: 'W', loaded: false, missing_inputs: [], no_disponibles: [], avisos_datos: [], options: {}, inputs: {} },
          health: { copia_datos: { vencida: false }, capabilities: {}, edicion: { producto: true, beta: [] } },
          feeders: [], outputs: [], selected: [], setSelected: () => {}, active, pf: null, jobs,
          run: async () => undefined, setWs: () => {}, startJob: async () => undefined,
          refresh: async () => undefined, refreshHealth: () => {},
        } }, createElement(EstudioPit)));`,
      resolveDir: RAIZ, loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  globalThis.localStorage ??= { getItem: () => null, setItem: () => {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

const expediente = {
  id: 'j2', kind: 'pit_expediente', status: 'done', workspace_id: 'W', lane: 'engine', title: 'Expediente PIT',
  result: { tipo: 'DE DIAGNÓSTICO, no presentable a Osinergmin', estado: 'incompleto',
    carpeta_relativa: 'expedientes_pit/AD-X/2025-2029',
    salidas_relativas: { resumen: 'expedientes_pit/AD-X/2025-2029/resumen.json' },
    pendientes: [{ causa: 'sin alternativas: no hay comparación ni programa' }],
    libro_f000: { motivo: 'sin CSG_FUENTES_NORMATIVAS' } },
};

test('107 T13 la matriz de cobertura: cada ruta del PIT del contrato tiene su llamada, su control y su prueba', async () => {
  const esquema = readFileSync(join(SRC, 'api', 'esquema.ts'), 'utf-8');
  const rutas = [...esquema.matchAll(/^ {2}"(\/api\/pit\/[^"]+)": \{/gm)].map((m) => m[1]).sort();
  assert.deepEqual(rutas, Object.keys(MATRIZ).sort(), 'una ruta del PIT sin fila en la matriz, o una fila que sobra');
  const { pit, pintar } = await cargar();
  const api = readFileSync(API, 'utf-8');
  const html = pintar({ j2: expediente });
  // 065:RF-9: test_frontend_rutas prueba una copia del frontend sola; allí no están las pruebas del servidor.
  const pruebas = join(RAIZ, '..', 'tests', 'test_pit_web.py');
  const servidor = existsSync(pruebas) ? readFileSync(pruebas, 'utf-8') : null;
  for (const [ruta, fila] of Object.entries(MATRIZ)) {
    assert.equal(typeof pit[fila.llamada], 'function', `${ruta}: falta pit.${fila.llamada}`);
    assert.ok(api.includes(`'${ruta}'`), `${ruta}: api/pit.ts no la llama`);
    assert.ok(html.includes(fila.pantalla), `${ruta}: la pantalla no tiene «${fila.pantalla}»`);
    if (servidor) assert.ok(servidor.includes(`def ${fila.prueba}(`), `${ruta}: falta su prueba ${fila.prueba}`);
  }
});

test('107 T13 el libro de la red en los cuatro formatos, y los botones apagados hasta tener lo que piden', async () => {
  const { pintar, LIBROS_RED } = await cargar();
  assert.equal(LIBROS_RED, '.xlsx,.xlsm,.xls,.xlsb');
  const html = pintar();
  assert.ok(html.includes('accept=".xlsx,.xlsm,.xls,.xlsb"'), html);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Diagnosticar<\/button>/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Armar el expediente<\/button>/);
  assert.ok(!html.includes('Registrar observaciones'), 'sin expediente no se registran observaciones');
  const ocupado = pintar({}, { engine: { id: 'otro' } });
  assert.ok(ocupado.includes('Hay otro trabajo del motor en curso.'));
});

test('107 T13 el expediente terminado: su tipo, sus salidas para guardar, sus pendientes y sus observaciones', async () => {
  const { pintar } = await cargar();
  const html = pintar({ j2: expediente });
  assert.ok(html.includes('DE DIAGNÓSTICO, no presentable a Osinergmin'));
  assert.ok(html.includes('resumen.json'), 'la salida se ofrece para guardar');
  assert.ok(html.includes('Pendientes (1)') && html.includes('sin alternativas: no hay comparación ni programa'));
  assert.ok(html.includes('F-000: sin CSG_FUENTES_NORMATIVAS'));
  assert.ok(html.includes('Registrar observaciones'));
});

test('107 T13 sus trabajos avisan en su pestaña', async () => {
  const { PASOS, pasoDeTrabajo } = await cargar();
  assert.equal(PASOS.pit.pestana, 'pit');
  assert.equal(pasoDeTrabajo('pit_diagnostico'), 'pit');
  assert.equal(pasoDeTrabajo('pit_expediente'), 'pit');
  const app = readFileSync(join(SRC, 'app', 'App.tsx'), 'utf-8');
  assert.match(app, /\{ id: 'pit', label: 'Estudio PIT', el: <EstudioPit \/>, entradas: false \}/);
});

test('107 T13 los años: sueltos, por tramos y sin repetir; lo que no es un año no pasa', async () => {
  const { leerAnios } = await cargar();
  assert.deepEqual(leerAnios('2027-2029, 2026 2027'), [2026, 2027, 2028, 2029]);
  assert.equal(leerAnios(''), null);
  assert.equal(leerAnios('2029-2027'), null);
  assert.equal(leerAnios('dos mil'), null);
});

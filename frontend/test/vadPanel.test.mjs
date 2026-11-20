import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Spec 108 T29: la pestaña «Estudio VAD». Sin navegador: la matriz de cobertura de las rutas del VAD (cada ruta del
// contrato con su llamada, su control en la pantalla y su prueba del servidor) y el panel pintado con un estudio.
const RAIZ = fileURLToPath(new URL('../', import.meta.url));
const SRC = join(RAIZ, 'src');
const PANEL = join(SRC, 'features', 'vad', 'EstudioVad.tsx');
const API = join(SRC, 'api', 'vad.ts');

/** 108 T29: ruta del contrato → función de api/vad.ts → su tramo en la URL → lo que la pide en la pantalla → prueba. */
const MATRIZ = {
  '/api/workspaces/{wid}/vad/estudios': { llamada: ['estudios', 'crear'], tramo: '/estudios', pantalla: 'Crear estudio',
    prueba: 'test_070_rf86_vad_el_caso_se_comprueba_antes_de_encolar' },
  '/api/workspaces/{wid}/vad/{estudio}': { llamada: ['detalle'], tramo: '/${encodeURIComponent(estudio)}`',
    pantalla: 'Observaciones (', prueba: 'test_108_rf26_el_detalle_dice_el_estudio_su_armado_sus_destinos_y_sus_salidas' },
  '/api/workspaces/{wid}/vad/{estudio}/armar': { llamada: ['armar'], tramo: '/armar', pantalla: 'Armar la empresa modelo',
    prueba: 'test_070_rf86_vad_crear_el_estudio_y_armar_la_empresa_modelo_por_la_web' },
  '/api/workspaces/{wid}/vad/{estudio}/observaciones': { llamada: ['observar'], tramo: '/observaciones',
    pantalla: 'Registrar observación', prueba: 'test_108_rf26_las_observaciones_se_registran_y_se_responden_por_la_web' },
  '/api/workspaces/{wid}/vad/{estudio}/observaciones/{numero}/respuesta': { llamada: ['responder'], tramo: '/respuesta',
    pantalla: 'Responder', prueba: 'test_108_rf26_las_observaciones_se_registran_y_se_responden_por_la_web' },
  '/api/workspaces/{wid}/vad/{estudio}/informe-definitivo': { llamada: ['informeDefinitivo'], tramo: '/informe-definitivo',
    pantalla: 'Armar el Informe Definitivo', prueba: 'test_108_rf26_el_informe_definitivo_es_un_trabajo_con_sus_huecos_nombrados' },
};

const DETALLE = {
  estudio: { id: 'e1', empresa: 'Distribuidora Sintética', grupo: 1, periodo: '2041-2045', version_tdr: 'tdr', estado: 'conforme' },
  armado: { terminado: true, sistemas: { S1: { estado: 'OK', pasos: { anexo2: { huecos: ['A-1: falta x'] } } } } },
  observaciones: [{ numero: '1', fecha: '2041-03-01', texto: 'Sustente.', estado: 'pendiente', afecta: [{ tipo: 'tabla', id: '1' }],
    respuesta: '', sustento: '', cambios: {} }],
  pendientes: ['1'], destinos: [{ tipo: 'tabla', id: '1' }], aviso_destinos: '',
  informe_definitivo: { documentos: [
    { documento: 'Respuestas', ruta: 'x', ruta_relativa: 'vad/e1/informe_definitivo/03_Respuestas.docx', motivo: '' },
    { documento: 'Tablas', ruta: null, ruta_relativa: null, motivo: 'sin el libro de las tablas de resultados del estudio' }],
  huecos: ['Tablas: sin el libro de las tablas de resultados del estudio'] },
  salidas: ['vad/e1/manifiesto.json'],
  linea: { terminada: true, pasos: { resultados: { estado: 'OK' }, pide: { estado: 'SIN_ENTRADA', motivo: 'el caso no trae el PIDE aprobado' } } },
};

let modulo;
async function cargar() {
  if (modulo) return modulo;
  assert.ok(existsSync(PANEL), 'falta src/features/vad/EstudioVad.tsx (108 T29)');
  assert.ok(existsSync(API), 'falta src/api/vad.ts (108 T29)');
  const salida = await build({
    stdin: {
      contents: `
        import { createElement, useState } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { EstudioVad } from './src/features/vad/EstudioVad';
        export { vad } from './src/api/vad';
        export * from './src/shared/pasoDeTrabajo';
        export const pintar = (react, jobs = {}, active = {}) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
          ws: { id: 'W', loaded: false, missing_inputs: [], no_disponibles: [], avisos_datos: [], options: {}, inputs: {} },
          health: { copia_datos: { vencida: false }, capabilities: {}, edicion: { producto: true, beta: [] } },
          feeders: [], outputs: [], selected: [], setSelected: () => {}, active, pf: null, jobs,
          run: async () => undefined, setWs: () => {}, startJob: async () => undefined,
          refresh: async () => undefined, refreshHealth: () => {},
        } }, createElement(EstudioVad)));`,
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

/** El panel con un estudio elegido y su detalle: React se sustituye por uno cuyos estados nacen con esos valores. */
async function pintarConDetalle() {
  const react = createRequire(import.meta.url)('react');
  const original = react.useState;
  const iniciales = [[DETALLE.estudio], 'e1', DETALLE];
  let i = 0;
  react.useState = (v) => (i < iniciales.length ? original(iniciales[i++]) : original(v));
  try {
    const { pintar } = await cargar();
    return pintar();
  } finally {
    react.useState = original;
  }
}

test('108 T29 la matriz de cobertura: cada ruta del VAD del contrato tiene su llamada, su control y su prueba', async () => {
  const esquema = readFileSync(join(SRC, 'api', 'esquema.ts'), 'utf-8');
  const rutas = [...esquema.matchAll(/^ {2}"(\/api\/workspaces\/\{wid\}\/vad\/[^"]*)": \{/gm)].map((m) => m[1]).sort();
  assert.deepEqual(rutas, Object.keys(MATRIZ).sort(), 'una ruta del VAD sin fila en la matriz, o una fila que sobra');
  const { vad } = await cargar();
  const api = readFileSync(API, 'utf-8');
  const html = await pintarConDetalle();
  // 065:RF-9: test_frontend_rutas prueba una copia del frontend sola; allí no están las pruebas del servidor.
  const dir = join(RAIZ, '..', 'tests');
  const servidor = existsSync(dir)
    ? ['test_vad_web.py', 'test_asistente_107_112.py'].map((f) => readFileSync(join(dir, f), 'utf-8')).join('\n') : null;
  for (const [ruta, fila] of Object.entries(MATRIZ)) {
    for (const f of fila.llamada) assert.equal(typeof vad[f], 'function', `${ruta}: falta vad.${f}`);
    assert.ok(api.includes(fila.tramo), `${ruta}: api/vad.ts no la llama`);
    assert.ok(html.includes(fila.pantalla), `${ruta}: la pantalla no tiene «${fila.pantalla}»`);
    if (servidor) assert.ok(servidor.includes(`def ${fila.prueba}(`), `${ruta}: falta su prueba ${fila.prueba}`);
  }
});

test('108 T29 con un estudio: el estado por sistema, las observaciones, el informe con sus huecos y las salidas', async () => {
  const html = await pintarConDetalle();
  assert.ok(html.includes('S1') && html.includes('1 huecos'), html.slice(0, 400));
  assert.ok(html.includes('Observaciones (1 pendientes)'));
  assert.match(html, /<button[^>]*disabled=""[^>]*>Armar el Informe Definitivo<\/button>/, 'con pendientes no se arma');
  assert.ok(html.includes('Antes, responda las observaciones.'));
  assert.ok(html.includes('03_Respuestas.docx'), 'el documento escrito se ofrece para guardar');
  assert.ok(html.includes('sin el libro de las tablas de resultados del estudio'), 'el documento sin fuente dice por qué');
  assert.ok(html.includes('Huecos (1)') && html.includes('Salidas (1)'));
  assert.ok(html.includes('Línea del VAD') && html.includes('SIN_ENTRADA · el caso no trae el PIDE aprobado'), '108 T30: el estado de cada paso');
  assert.ok(html.includes('Caso (zip con sistemas.json y sus tablas)'), 'el caso se elige de la empresa o se sube en zip (109:RF-25)');
});

test('108 T29 sin estudios lo dice, y sus trabajos avisan en su pestaña', async () => {
  const { pintar, PASOS, pasoDeTrabajo } = await cargar();
  assert.ok(pintar().includes('Aún no hay un estudio del VAD en este espacio.'));
  assert.equal(PASOS.vad.pestana, 'vad');
  assert.equal(pasoDeTrabajo('vad_empresa_modelo'), 'vad');
  assert.equal(pasoDeTrabajo('vad_informe_definitivo'), 'vad');
  const app = readFileSync(join(SRC, 'app', 'App.tsx'), 'utf-8');
  assert.match(app, /\{ id: 'vad', label: 'Estudio VAD', el: <EstudioVad \/>, entradas: false \}/);
});

test('108 T32 sin estudios no enseña una lista vacía y dice qué falta para crearlo (108:RF-26)', async () => {
  const { pintar } = await cargar();
  const html = pintar();
  assert.ok(!html.includes('<span>Estudio</span>'), 'la lista de estudios vacía no se enseña');
  assert.match(html, /<button[^>]*disabled=""[^>]*>\s*Crear estudio<\/button>/);
  assert.ok(html.includes('Para crearlo: periodo (2027-2031) y versión del TdR.'), 'el botón apagado dice qué falta');
});

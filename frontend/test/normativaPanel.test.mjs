import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 107:RF-21: la pestaña «Biblioteca normativa». Sin navegador: cada ruta /api/normativa del contrato con su llamada en
// api/normativa.ts y su prueba del servidor, el filtro de normas y el panel pintado con una biblioteca.
const RAIZ = fileURLToPath(new URL('../', import.meta.url));
const SRC = join(RAIZ, 'src');

const MATRIZ = {
  '/api/normativa': { llamada: ['listar', 'agregar'], prueba: 'test_107_rf21_la_web_sube_una_norma_y_rechaza_la_que_no_valida' },
  '/api/normativa/reglas': { llamada: ['reglas'], prueba: 'test_107_rf21_la_web_da_las_reglas_con_su_cita' },
};

let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { BibliotecaNormativa } from './src/features/normativa/BibliotecaNormativa';
        export { normativa, filtrarNormas } from './src/api/normativa';
        export const pintar = () => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
          ws: { id: 'W', loaded: false, missing_inputs: [], no_disponibles: [], avisos_datos: [], options: {}, inputs: {} },
          health: { copia_datos: { vencida: false }, capabilities: {}, edicion: { producto: true, beta: [] } },
          feeders: [], outputs: [], selected: [], setSelected: () => {}, active: {}, pf: null, jobs: {},
          run: async () => undefined, setWs: () => {}, startJob: async () => undefined,
          refresh: async () => undefined, refreshHealth: () => {},
        } }, createElement(BibliotecaNormativa)));`,
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

test('107:RF-21 cada ruta /api/normativa del contrato tiene su llamada y su prueba del servidor', async () => {
  const esquema = readFileSync(join(SRC, 'api', 'esquema.ts'), 'utf-8');
  const rutas = [...esquema.matchAll(/^ {2}"(\/api\/normativa[^"]*)": \{/gm)].map((m) => m[1]).sort();
  assert.deepEqual(rutas, Object.keys(MATRIZ).sort());
  const { normativa } = await cargar();
  const dir = join(RAIZ, '..', 'tests');
  const pruebas = existsSync(join(dir, 'test_normativa_web.py')) ? readFileSync(join(dir, 'test_normativa_web.py'), 'utf-8') : null;
  for (const [ruta, fila] of Object.entries(MATRIZ)) {
    for (const f of fila.llamada) assert.equal(typeof normativa[f], 'function', `${ruta}: falta normativa.${f}`);
    if (pruebas !== null) assert.ok(pruebas.includes(`def ${fila.prueba}(`), `${ruta}: falta ${fila.prueba}`);
  }
});

test('107:RF-21 el filtro encuentra por acto o título sin distinguir tildes ni mayúsculas', async () => {
  const { filtrarNormas } = await cargar();
  const normas = [{ acto: 'RCD 232-2017-OS/CD', titulo: 'Guía del VNR' }, { acto: 'DS 028-2021-EM', titulo: 'Criterios del PIDE' }];
  assert.deepEqual(filtrarNormas(normas, 'guia').map((n) => n.acto), ['RCD 232-2017-OS/CD']);
  assert.deepEqual(filtrarNormas(normas, ' 028 ').map((n) => n.acto), ['DS 028-2021-EM']);
  assert.equal(filtrarNormas(normas, '').length, 2);
});

test('107:RF-21 la pestaña ofrece la fecha, la búsqueda y la subida de una norma', async () => {
  const { pintar } = await cargar();
  const html = pintar();
  assert.match(html, /type="date"/);
  assert.match(html, /type="search"/);
  assert.match(html, /Añadir o actualizar una norma/);
});

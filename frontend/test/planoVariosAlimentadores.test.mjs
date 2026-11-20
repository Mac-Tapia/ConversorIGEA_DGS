import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Spec 111, T24 y T25 (RF-24, RF-25): el plano con varios alimentadores a la vez, sin navegador. El principal (el de la
// variación y el unifilar) va siempre primero, los añadidos en el orden de la lista y sin repetir; la pestaña pide el
// plano y su página con todos, y enseña los puntos de transferencia que da el servidor. El recorrido en navegador real
// está en e2e/plano_varios.spec.ts.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const PLANO = join(FRONT, 'src', 'features', 'plano');

let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: { contents: `export * as logica from './src/features/plano/logicaPlano';`, resolveDir: FRONT, loader: 'ts' },
    bundle: true, format: 'cjs', platform: 'node', write: false,
  });
  const require = createRequire(import.meta.url);
  const m = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(m, m.exports, require);
  modulo = m.exports;
  return modulo;
}

test('111:RF-24 el principal va primero y los añadidos en el orden de la lista, sin repetir', async () => {
  const { logica } = await cargar();
  assert.equal(typeof logica.alimentadoresDelPlano, 'function', 'falta alimentadoresDelPlano');
  const opciones = ['A1', 'B2', 'C3', 'D4'];
  assert.deepEqual(logica.alimentadoresDelPlano('C3', ['D4', 'A1', 'C3', 'X9'], opciones), ['C3', 'A1', 'D4']);
  assert.deepEqual(logica.alimentadoresDelPlano('B2', [], opciones), ['B2']);
  assert.deepEqual(logica.alimentadoresDelPlano('', ['A1'], opciones), []);
});

test('111:RF-24 una casilla pone o quita el alimentador y el filtro no ofrece el principal', async () => {
  const { logica } = await cargar();
  assert.deepEqual(logica.alternarAlimentador(['A1'], 'B2'), ['A1', 'B2']);
  assert.deepEqual(logica.alternarAlimentador(['A1', 'B2'], 'A1'), ['B2']);
  assert.deepEqual(logica.alimentadoresAnadibles(['QX143', 'QX144', 'ZR102'], 'QX144', 'qx'), ['QX143']);
  assert.deepEqual(logica.alimentadoresAnadibles(['QX143', 'QX144', 'ZR102'], 'QX144', ''), ['QX143', 'ZR102']);
});

test('111:RF-24, RF-25 la pestaña pide el plano y su página con todos los elegidos y lista las transferencias', () => {
  const fuente = readFileSync(join(PLANO, 'PlanoRed.tsx'), 'utf8');
  assert.match(fuente, /plano\.datos\(ws\.id, elegidos,/, 'el plano se pide solo con el principal');
  assert.match(fuente, /plano\.paginaUrl\(ws\.id, elegidos,/, 'la página se pide solo con el principal');
  assert.match(fuente, /type="checkbox"/, 'sin casillas para añadir alimentadores');
  // La lista flota sobre el plano: se cierra al pulsar fuera, al entrar en el marco del plano o con Escape.
  assert.match(fuente, /window\.addEventListener\('blur', cerrar\)/, 'la lista de «Ver también» tapa el plano');
  assert.match(fuente, /document\.addEventListener\('pointerdown', fuera\)/);
  assert.match(fuente, /datos\?\.transferencias/, 'la pestaña no enseña los puntos de transferencia');
  assert.match(fuente, /onClick=\{\(\) => elegir\(t\.barra\)\}/, 'un punto de transferencia no lleva a su barra');
  // El desplegable del principal sigue con su nombre: las e2e lo buscan por su rol.
  assert.match(fuente, /<label>\{TEXTOS\.alimentador\}\{' '\}\s*<select value=\{actual\}/);
});

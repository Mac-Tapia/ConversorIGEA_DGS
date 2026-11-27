import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 006:RF-48: el eje de tiempo de la curva de cabecera llega hasta el último registro. El 2026-11-27 el usuario vio la
// medición del 01/01/26 al 27/10/26 con el último rótulo en «09/09/26»: octubre, recién cargado, no tenía marca.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const CURVA = join(FRONT, 'src/features/powerfactory/CurvaCabecera.tsx');

async function eje() {
  const salida = await build({
    stdin: { contents: `export * from './src/shared/ejeTiempo';`, resolveDir: FRONT, loader: 'ts' },
    bundle: true, format: 'cjs', platform: 'node', write: false,
  });
  const require = createRequire(import.meta.url);
  const m = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(m, m.exports, require);
  return m.exports;
}

test('006:RF-48 la curva usa las marcas comunes del eje de tiempo', () => {
  const fuente = readFileSync(CURVA, 'utf-8');
  assert.match(fuente, /marcasDeDias\(t0, t1\)/, 'la curva no usa las marcas que llegan al último registro');
});

test('006:RF-48 diez meses: una marca por mes y el último día con registros', async () => {
  const { marcasDeDias } = await eje();
  const t0 = new Date(2026, 0, 1, 0, 15).getTime();
  const t1 = new Date(2026, 9, 27, 23, 45).getTime();
  const textos = marcasDeDias(t0, t1).map((m) => m.texto);
  assert.deepEqual(textos, ['01/01/26', '01/02/26', '01/03/26', '01/04/26', '01/05/26', '01/06/26', '01/07/26',
    '01/08/26', '01/09/26', '01/10/26', '27/10/26']);
  // Con un mes más cargado, el eje llega a él sin tocar nada.
  const nov = marcasDeDias(t0, new Date(2026, 10, 30, 23, 45).getTime()).map((m) => m.texto);
  assert.equal(nov.at(-1), '30/11/26');
  assert.ok(nov.includes('01/11/26'));
});

test('006:RF-48 años de medición: cada pocos meses, sin pasar de unas diez marcas', async () => {
  const { marcasDeDias } = await eje();
  const marcas = marcasDeDias(new Date(2023, 0, 1).getTime(), new Date(2026, 9, 27).getTime());
  assert.ok(marcas.length <= 12, `${marcas.length} marcas`);
  assert.equal(marcas[0].texto, '01/01/23');
  assert.equal(marcas.at(-1).texto, '27/10/26');
});

test('006:RF-48 un mes: días a medianoche y el último día, sin rótulos pegados', async () => {
  const { marcasDeDias } = await eje();
  const marcas = marcasDeDias(new Date(2026, 1, 1, 0, 15).getTime(), new Date(2026, 1, 28, 23, 45).getTime());
  assert.equal(marcas.at(-1).texto, '28/02/26');
  for (let i = 1; i < marcas.length; i++) assert.ok(marcas[i].t - marcas[i - 1].t >= 2 * 24 * 3600 * 1000);
});

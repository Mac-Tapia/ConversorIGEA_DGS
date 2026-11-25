import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 086:RF-126: la «Máxima de cada alimentador (no coincidente)» se elige en «Ámbito de la máxima», antes de buscar, con
// varios alimentadores, por SET y por sistema eléctrico. El 2026-11-24 el usuario no la encontró: solo estaba en «Instante
// de la calibración», que aparece después de buscar la coincidente.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const PANTALLA = join(FRONT, 'src/features/powerfactory/DemandaMedida.tsx');
const MODULO = join(FRONT, 'src/features/powerfactory/ambitoMaxima.ts');

async function ambito() {
  const salida = await build({
    stdin: { contents: `export * from './src/features/powerfactory/ambitoMaxima';`, resolveDir: FRONT, loader: 'ts' },
    bundle: true, format: 'cjs', platform: 'node', write: false,
  });
  const require = createRequire(import.meta.url);
  const m = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(m, m.exports, require);
  return m.exports;
}

test('086:RF-126 «Ámbito de la máxima» ofrece la no coincidente de cada ámbito y la búsqueda la pide', () => {
  assert.ok(existsSync(MODULO), 'falta ambitoMaxima.ts');
  const fuente = readFileSync(PANTALLA, 'utf-8');
  const desde = fuente.indexOf('Ámbito de la máxima');
  assert.ok(desde > 0, 'no está el desplegable «Ámbito de la máxima»');
  const desplegable = fuente.slice(desde, fuente.indexOf('</select>', desde));
  assert.match(desplegable, /OPCIONES_AMBITO\.map/, 'el desplegable no lista las opciones del ámbito');
  assert.match(fuente, /onClick=\{\(\) => maxima\('', ambito\.noCoincidente\)\}/, 'buscar no pide la no coincidente');
});

test('086:RF-126 cada ámbito con su coincidente por defecto y su no coincidente', async () => {
  const { OPCIONES_AMBITO, leerAmbito, valorDelAmbito, demasiadosParaLaCoincidente } = await ambito();
  const valores = OPCIONES_AMBITO.map((o) => o.valor);
  assert.deepEqual(valores, ['alimentadores', 'alimentadores:propia', 'set', 'set:propia', 'sistema', 'sistema:propia']);
  for (const o of OPCIONES_AMBITO) {
    const a = leerAmbito(o.valor);
    assert.equal(valorDelAmbito(a), o.valor);
    assert.equal(a.noCoincidente, o.valor.endsWith(':propia'));
    assert.equal(/no coincidente/.test(o.rotulo), a.noCoincidente, o.rotulo);
  }
  assert.throws(() => leerAmbito('barra'));
  // Con 4 alimentadores la coincidente pide SET o sistema; la de cada uno, no.
  assert.equal(demasiadosParaLaCoincidente(leerAmbito('alimentadores'), 4), true);
  assert.equal(demasiadosParaLaCoincidente(leerAmbito('alimentadores:propia'), 4), false);
  assert.equal(demasiadosParaLaCoincidente(leerAmbito('set'), 40), false);
});

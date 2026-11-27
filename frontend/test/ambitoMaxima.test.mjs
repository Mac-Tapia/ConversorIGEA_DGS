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

// 086:RF-140: el 2026-11-27 el usuario vio dos desplegables casi iguales: «Ámbito de la máxima» con «Alimentadores: la
// máxima de cada uno (no coincidente)» e «Instante de la calibración» con «Máxima de cada alimentador (no coincidente)».
// La no coincidente se elige solo en el ámbito; el instante ofrece lo del ámbito o calibrar todos en la de una cabecera.
test('086:RF-140 «Instante de la calibración» no repite la no coincidente del ámbito', async () => {
  const fuente = readFileSync(PANTALLA, 'utf-8');
  const desde = fuente.indexOf('Instante de la calibración');
  const desplegable = fuente.slice(desde, fuente.indexOf('</select>', desde));
  assert.doesNotMatch(desplegable, /value="propia"/, 'el instante vuelve a ofrecer la no coincidente');
  assert.match(desplegable, /opcionesDelInstante\(/);
  const { opcionesDelInstante, leerAmbito } = await ambito();
  const instantes = [{ alimentador: 'A1', fecha: '2026-02-26 21:00:00', kw: 4348.56 },
    { alimentador: 'A2', fecha: '2026-01-09 13:00:00', kw: 9375.33 }];
  const kw = (n) => n.toFixed(0);
  const propia = opcionesDelInstante(leerAmbito('alimentadores:propia'), instantes, '', kw);
  assert.deepEqual(propia.map((o) => o.valor), ['', '2026-02-26 21:00:00', '2026-01-09 13:00:00']);
  assert.match(propia[0].rotulo, /^La del ámbito/);
  assert.ok(propia.every((o) => !/no coincidente/.test(o.rotulo)), 'repite la no coincidente del ámbito');
  assert.match(propia[1].rotulo, /^Todos en la máxima de A1 · 2026-02-26 21:00:00/);
  const coincidente = opcionesDelInstante(leerAmbito('alimentadores'), instantes, 'enero de 2026', kw);
  assert.equal(coincidente[0].rotulo, 'Máxima coincidente de los seleccionados en enero de 2026 (por defecto)');
  assert.equal(opcionesDelInstante(leerAmbito('set'), [], '', kw)[0].rotulo, 'Máxima de la barra de su SET (por defecto)');
});

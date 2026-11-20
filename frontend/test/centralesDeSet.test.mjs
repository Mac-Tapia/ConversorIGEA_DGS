import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 086:RF-122 (amplía 022:RF-88): la SET de cada central térmica del libro, elegida entre todas; primero las de los
// alimentadores analizados, y la central cuya SET no tiene ninguno dice que no entra.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const PF = join(FRONT, 'src', 'features', 'powerfactory');

async function cargar() {
  assert.ok(existsSync(join(PF, 'centralesDeSet.ts')), 'falta centralesDeSet.ts');
  const salida = await build({
    stdin: { contents: `export * from './src/features/powerfactory/centralesDeSet';`, resolveDir: FRONT, loader: 'ts' },
    bundle: true, format: 'cjs', platform: 'node', write: false,
  });
  const require = createRequire(import.meta.url);
  const m = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(m, m.exports, require);
  return m.exports;
}

const SETS = [
  { codigo: 'SET 2', rotulo: 'SET 2 Dos', zonal: 'Z', alimentadores: ['AA101', 'AA102'] },
  { codigo: 'SET 5', rotulo: 'SET 5 Cinco', zonal: 'Z', alimentadores: ['BB201'] },
  { codigo: 'SET 9', rotulo: 'SET 9 Nueve', zonal: 'Z', alimentadores: [] },
];
const CT = { medidor: 'CT_X', kv: 10, rotulo: '', set: 'SET 9', set_rotulo: 'SET 9 Nueve', alimentadores: [], tramo: '' };

test('086:RF-122 primero las SET de los alimentadores analizados, en el orden del servidor', async () => {
  const m = await cargar();
  const { analizadas, otras } = m.setsPorAnalisis(SETS, ['bb201']);
  assert.deepEqual(analizadas.map((s) => s.codigo), ['SET 5']);
  assert.deepEqual(otras.map((s) => s.codigo), ['SET 2', 'SET 9']);
});

test('086:RF-122 la SET elegida manda y da los alimentadores del tramo; sin analizados, no entra', async () => {
  const m = await cargar();
  assert.equal(m.setDeLaCentral(CT, {}), 'SET 9');
  assert.equal(m.setDeLaCentral(CT, { CT_X: 'SET 2' }), 'SET 2');
  assert.deepEqual(m.alimentadoresDeSet('SET 2', SETS, CT), ['AA101', 'AA102']);
  assert.equal(m.motivoNoEntra('SET 9', SETS, ['AA101']), 'SET 9 Nueve no tiene ninguno de los alimentadores analizados: no entra.');
  assert.equal(m.motivoNoEntra('SET 2', SETS, ['AA101']), null);
  assert.match(m.motivoNoEntra('', SETS, ['AA101']), /no entra/);
  for (const t of [m.motivoNoEntra('SET 9', SETS, []), m.motivoNoEntra('', SETS, [])]) assert.doesNotMatch(t, /\(s\)|\(es\)/);
});

test('086:RF-122 la tabla de centrales elige la SET con grupos y manda la elegida al buscar la máxima', () => {
  const fuente = readFileSync(join(PF, 'DemandaMedida.tsx'), 'utf8');
  assert.match(fuente, /aria-label=\{`SET de \$\{c\.medidor\}`\}/, 'la SET de la central no se elige');
  assert.match(fuente, /<optgroup label="SET de los alimentadores analizados">/);
  assert.match(fuente, /<optgroup label="Otras SET">/);
  assert.match(fuente, /centrales_set: centralSet/, 'la SET elegida no llega al servidor');
  assert.match(fuente, /alimentadoresDeSet\(suSet, setsCentrales, c\)/, 'el tramo no sigue a la SET elegida');
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

// Electro Oriente NJA202 (T32, 2026-11-12): calibrado a 0,568 p.u. y sin cargas nuevas, la web no ofrecía ninguna obra.
const entry = fileURLToPath(new URL('../src/features/powerfactory/obrasEstadoActual.ts', import.meta.url));

async function cargar() {
  const salida = await build({ entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node' });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

const BASE = { proyecto: 'NJA202', alimentadores: ['NJA202'], calibrado: true, proyectoDeCargas: null };

test('086:RF-77: calibrado, con alimentadores y sin cargas nuevas integradas, se ofrecen las obras del estado actual', async () => {
  const { ofrecerObrasEstadoActual } = await cargar();
  assert.equal(ofrecerObrasEstadoActual(BASE), true);
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, proyectoDeCargas: 'OTRO' }), true);
});

test('086:RF-77: sin proyecto, sin alimentadores, sin calibrar o con cargas integradas, no', async () => {
  const { ofrecerObrasEstadoActual } = await cargar();
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, proyecto: null }), false);
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, alimentadores: [] }), false);
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, calibrado: false }), false);
  // Con cargas integradas, la escalera va en su informe, como siempre (042:RF-81).
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, proyectoDeCargas: 'NJA202' }), false);
});

test('086:RF-77: el resultado dice que lo medido es el estado actual', async () => {
  const { RESUMEN_SIN_CARGAS } = await cargar();
  assert.match(RESUMEN_SIN_CARGAS, /estado actual/);
  assert.match(RESUMEN_SIN_CARGAS, /violan límites/);
});

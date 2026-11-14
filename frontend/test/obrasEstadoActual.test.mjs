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

test('086:RF-77: con cargas nuevas aplicadas en disco, el bloque las nombra y propone las obras automáticamente', async () => {
  const { textosObras } = await cargar();
  const cargas = [{ sed: 'SECA001', alimentador: 'CA101', sola: true }, { sed: 'B1', alimentador: 'CHN102', sola: false }];
  const t = textosObras(cargas, ['CA101', 'CHN102']);
  assert.equal(t.titulo, 'Obras en «Con proyecto» con las cargas nuevas');
  assert.equal(t.boton, 'Proponer obras automáticamente');
  assert.match(t.ayuda, /SECA001 \(CA101\), B1 \(CHN102, en bloque\)/);
  assert.match(t.ayuda, /hasta 3 alternativas/);
  // Solo cuentan las de los alimentadores marcados; sin ninguna, es el estado actual, como antes.
  const sin = textosObras(cargas, ['PA217']);
  assert.equal(sin.titulo, 'Obras para el estado actual');
  assert.equal(sin.boton, 'Corregir el estado actual en «Con proyecto»');
});

test('018:RF-19: 4 y 5 trabajan con el proyecto elegido en su desplegable, o con el del paso 1', async () => {
  const { proyectoDeEstudio } = await cargar();
  assert.deepEqual(proyectoDeEstudio('', [], 'P1', ['A']), { proyecto: 'P1', feeders: ['A'], propio: false });
  assert.deepEqual(proyectoDeEstudio('P1', ['X'], 'P1', ['A']), { proyecto: 'P1', feeders: ['A'], propio: false });
  assert.deepEqual(proyectoDeEstudio('OTRO', ['B', 'C'], 'P1', ['A']), { proyecto: 'OTRO', feeders: ['B', 'C'], propio: true });
  assert.deepEqual(proyectoDeEstudio('OTRO', [], '', []), { proyecto: 'OTRO', feeders: [], propio: true });
});

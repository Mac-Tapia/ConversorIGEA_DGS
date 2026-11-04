import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const entry = fileURLToPath(new URL('../src/alternativas.ts', import.meta.url));

async function cargar() {
  const salida = await build({
    entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

test('042:RF-77: el alcance con las mismas palabras que el informe', async () => {
  const { alcanceDe } = await cargar();
  assert.equal(alcanceDe({ definitiva: true, aguanta_anios: 20 }), 'definitiva, 20 años');
  assert.equal(alcanceDe({ definitiva: false, aguanta_anios: 5 }), 'temporal, aguanta 5 años');
  assert.equal(alcanceDe({ definitiva: false, aguanta_anios: 0 }), 'temporal');
  assert.equal(alcanceDe({}), 'sin medir');
});

test('042:RF-77: sorteos y valle dicen lo que no se midió', async () => {
  const { sorteosDe, valleDe } = await cargar();
  assert.equal(sorteosDe({ fraccion: 0.96 }), '96 %');
  assert.equal(sorteosDe({ fraccion: null }), 'sin sortear');
  assert.equal(valleDe({ valle: true }), 'cumple');
  assert.equal(valleDe({}), 'no comprobado');
});

test('042:RF-77: de menor a mayor costo, y sin costo al final', async () => {
  const { porCosto } = await cargar();
  const orden = porCosto([{ nombre: 'b', costo_anual: 200 }, { nombre: 'x', costo_anual: null }, { nombre: 'a', costo_anual: 100 }]);
  assert.deepEqual(orden.map((a) => a.nombre), ['a', 'b', 'x']);
});

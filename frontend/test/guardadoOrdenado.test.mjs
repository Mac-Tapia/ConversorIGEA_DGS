import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 072:RF-45 (revisión de 1d, 18-11): el guardado del proyecto y los alimentadores del espacio. Solo la respuesta o el
// fallo del ÚLTIMO envío tocan la pantalla, y solo si el espacio sigue siendo el mismo; las promesas se resuelven aquí
// en el orden que haga falta.
const raiz = fileURLToPath(new URL('..', import.meta.url));
const MODULO = join(raiz, 'src', 'features', 'powerfactory', 'guardadoOrdenado.ts');

async function cargar() {
  assert.ok(existsSync(MODULO), '072:RF-45: el guardado del espacio aplica cualquier respuesta, también la de un envío viejo');
  const r = await build({ stdin: { contents: `export * from './src/features/powerfactory/guardadoOrdenado';`,
    resolveDir: raiz, loader: 'ts' }, bundle: true, write: false, format: 'cjs', platform: 'node' });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', r.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
  return mod.exports;
}

function pendiente() {
  let resolver, rechazar;
  const promesa = new Promise((res, rej) => { resolver = res; rechazar = rej; });
  return { promesa, resolver, rechazar };
}

/** Una pantalla de prueba: el espacio vigente y los envíos al servidor, cada uno con su promesa a mano. */
function escenario(crearGuardado) {
  const estado = { ws: { id: 'E1', options: { pf_alimentadores_elegidos: [] } } };
  const envios = [];
  const guardar = crearGuardado(() => estado.ws, (w) => { estado.ws = w; },
    (id, cambio) => { const p = pendiente(); envios.push({ id, cambio, ...p }); return p.promesa; }, { current: 0 });
  return { estado, envios, guardar };
}

const del = (lista) => ({ id: 'E1', options: { pf_alimentadores_elegidos: lista } });

test('072:RF-45 la respuesta de un envío viejo no deshace uno más nuevo (A, B, llega A)', async () => {
  const { crearGuardado } = await cargar();
  const { estado, envios, guardar } = escenario(crearGuardado);
  const a = guardar({ pf_alimentadores_elegidos: ['A'] });
  const b = guardar({ pf_alimentadores_elegidos: ['A', 'B'] });
  envios[0].resolver(del(['A']));
  await a;
  assert.deepEqual(estado.ws.options.pf_alimentadores_elegidos, ['A', 'B'], 'la respuesta de A borró B');
  envios[1].resolver(del(['A', 'B']));
  await b;
  assert.deepEqual(estado.ws.options.pf_alimentadores_elegidos, ['A', 'B']);
});

test('072:RF-45 en orden inverso (llega B y después A) manda B', async () => {
  const { crearGuardado } = await cargar();
  const { estado, envios, guardar } = escenario(crearGuardado);
  const a = guardar({ pf_alimentadores_elegidos: ['A'] });
  const b = guardar({ pf_alimentadores_elegidos: ['A', 'B'] });
  envios[1].resolver(del(['A', 'B']));
  await b;
  envios[0].resolver(del(['A']));
  await a;
  assert.deepEqual(estado.ws.options.pf_alimentadores_elegidos, ['A', 'B']);
});

test('072:RF-45 solo el fallo del último envío restaura, y lo restaura a lo de antes de ese envío', async () => {
  const { crearGuardado } = await cargar();
  const { estado, envios, guardar } = escenario(crearGuardado);
  const a = guardar({ pf_alimentadores_elegidos: ['A'] });
  const b = guardar({ pf_alimentadores_elegidos: ['A', 'B'] });
  envios[0].rechazar(new Error('red'));
  await a;
  assert.deepEqual(estado.ws.options.pf_alimentadores_elegidos, ['A', 'B'], 'el fallo de A deshizo B');
  envios[1].rechazar(new Error('red'));
  await b;
  assert.deepEqual(estado.ws.options.pf_alimentadores_elegidos, ['A']);
});

test('072:RF-45 una respuesta que llega con otro espacio abierto no lo pinta', async () => {
  const { crearGuardado } = await cargar();
  const { estado, envios, guardar } = escenario(crearGuardado);
  const a = guardar({ pf_alimentadores_elegidos: ['A'] });
  estado.ws = { id: 'E2', options: {} };
  envios[0].resolver(del(['A']));
  await a;
  assert.equal(estado.ws.id, 'E2');
});

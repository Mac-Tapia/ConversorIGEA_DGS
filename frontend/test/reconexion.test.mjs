import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

async function cargar(fichero) {
  const salida = await build({
    entryPoints: [fileURLToPath(new URL(`../src/${fichero}`, import.meta.url))],
    bundle: true, write: false, format: 'esm', platform: 'node',
  });
  return import(`data:text/javascript;base64,${Buffer.from(salida.outputFiles[0].contents).toString('base64')}`);
}

const trabajo = (id, status, extra = {}) => ({ id, status, workspace_id: 'W', title: id, finished_at: null, error: null, ...extra });

test('086:RF-9 lo que el servidor nuevo no conoce murió con el anterior y deja libre su carril', async () => {
  const { fusionarTrabajos } = await cargar('reconexion.ts');
  const previos = { a: trabajo('a', 'running'), b: trabajo('b', 'done'), c: trabajo('c', 'queued', { workspace_id: 'OTRO' }) };
  const r = fusionarTrabajos(previos, [], 'W', 1000);
  assert.equal(r.a.status, 'interrumpido');
  assert.equal(r.a.finished_at, 1000);
  assert.match(r.a.error, /reinició/);
  assert.equal(r.b.status, 'done', 'lo terminado no se toca');
  assert.equal(r.c.status, 'queued', 'lo de otro espacio no es de esta pestaña');
});

test('086:RF-9 lo que el servidor sí conoce manda sobre lo que veía la pestaña', async () => {
  const { fusionarTrabajos } = await cargar('reconexion.ts');
  const r = fusionarTrabajos({ a: trabajo('a', 'running') },
    [trabajo('a', 'interrumpido', { error: 'del servidor' }), trabajo('z', 'done')], 'W', 1000);
  assert.equal(r.a.error, 'del servidor');
  assert.equal(r.z.status, 'done');
});

test('086:RF-9 los interrumpidos sin ver, el último primero', async () => {
  const { interrumpidosPendientes } = await cargar('reconexion.ts');
  const jobs = {
    a: trabajo('a', 'interrumpido', { finished_at: 1 }), b: trabajo('b', 'interrumpido', { finished_at: 2 }),
    c: trabajo('c', 'interrumpido', { finished_at: 3 }), d: trabajo('d', 'done'),
    e: trabajo('e', 'interrumpido', { workspace_id: 'OTRO', finished_at: 9 }),
  };
  assert.deepEqual(interrumpidosPendientes(jobs, 'W', ['c']).map((j) => j.id), ['b', 'a']);
});

test('086:RF-16 en desarrollo no hay betas y todo se ofrece', async () => {
  const { avisoBeta, betaActiva, esProducto } = await cargar('edicion.ts');
  const h = { edicion: { producto: false, beta: [] } };
  assert.equal(esProducto(h), false);
  assert.equal(betaActiva(h, 'pide'), true);
  assert.equal(avisoBeta(h, 'pide'), null);
});

test('086:RF-16 en producto una beta dice su aviso y, apagada, no se ofrece', async () => {
  const { avisoBeta, betaActiva, esProducto } = await cargar('edicion.ts');
  const h = { edicion: { producto: true, beta: [
    { clave: 'pide', nombre: 'P', aviso: 'En beta', activa: false }, { clave: 'asistente', nombre: 'A', aviso: 'x', activa: true },
  ] } };
  assert.equal(esProducto(h), true);
  assert.equal(betaActiva(h, 'pide'), false);
  assert.equal(betaActiva(h, 'asistente'), true);
  assert.equal(avisoBeta(h, 'pide'), 'En beta');
});

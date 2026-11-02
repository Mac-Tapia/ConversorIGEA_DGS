import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

async function cargar() {
  const salida = await build({ entryPoints: [fileURLToPath(new URL('../src/equipoAsistente.ts', import.meta.url))],
    bundle: true, write: false, format: 'esm', platform: 'node' });
  return import(`data:text/javascript;base64,${Buffer.from(salida.outputFiles[0].contents).toString('base64')}`);
}

test('065:RF-22/23 equipo consulta el espacio y revisa solo el plan seleccionado', async () => {
  const { equipoApi } = await cargar();
  const solicitudes = [];
  const anterior = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    solicitudes.push({ url, init });
    return new Response(JSON.stringify({ id: 'trabajo', status: 'queued' }), { status: 202 });
  };
  try {
    await equipoApi.estado('espacio /a');
    await equipoApi.revisar('espacio /a', 'plan /a');
    assert.equal(solicitudes[0].url, '/api/workspaces/espacio%20%2Fa/asistente/equipo');
    assert.equal(solicitudes[1].url, '/api/workspaces/espacio%20%2Fa/asistente/plan%20%2Fa/revision');
    assert.equal(solicitudes[1].init.method, 'POST');
    assert.deepEqual(JSON.parse(solicitudes[1].init.body), {});
  } finally { globalThis.fetch = anterior; }
});

test('065:RF-22 error de permiso muestra el detalle del servidor', async () => {
  const { equipoApi } = await cargar();
  const anterior = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'El plan ya no existe' }), { status: 400 });
  try { await assert.rejects(equipoApi.revisar('a', 'b'), /El plan ya no existe/); }
  finally { globalThis.fetch = anterior; }
});

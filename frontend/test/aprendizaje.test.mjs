import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

async function cargar() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { VistaAprendizaje } from './src/components/Aprendizaje';
    export { api } from './src/api';
    export const pintar = (estado) => renderToStaticMarkup(createElement(VistaAprendizaje, { estado }));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

test('050:RF-10 aprendizaje consulta la ruta de lectura sin iniciar trabajo', async () => {
  const { api } = await cargar();
  const anterior = globalThis.fetch;
  const pedidos = [];
  globalThis.fetch = async (url, init) => {
    pedidos.push({ url, init });
    return new Response(JSON.stringify({ fases: {}, ultimo_ciclo: null, conjunto_activo: null, bloqueos: [] }));
  };
  try {
    await api.asistenteAprendizaje();
    assert.equal(pedidos.length, 1);
    assert.equal(pedidos[0].url, '/api/asistente/aprendizaje');
    assert.equal(pedidos[0].init?.method ?? 'GET', 'GET');
  } finally { globalThis.fetch = anterior; }
});

test('050:RF-10 siete fases distinguen rechazo y aceptación nativa pendiente', async () => {
  const { pintar } = await cargar();
  const fases = Object.fromEntries(['preparacion', 'entrenamiento', 'seleccion', 'evaluacion',
    'publicacion', 'activacion', 'aceptacion_nativa'].map((f) => [f, { estado: 'pendiente', motivo: '' }]));
  fases.entrenamiento = { estado: 'hecho', motivo: 'candidatos entrenados' };
  fases.evaluacion = { estado: 'rechazado', motivo: 'retroceso frente a la referencia' };
  fases.aceptacion_nativa.motivo = 'sin validación en DIgSILENT del conjunto';
  const html = pintar({ fases, bloqueos: [], ultimo_ciclo: null, conjunto_activo: null });
  assert.equal((html.match(/<tr>/g) ?? []).length, 8);
  for (const texto of ['Preparación', 'Entrenamiento', 'Selección', 'Evaluación', 'Publicación',
    'Activación', 'Validación en PowerFactory', 'Rechazado', 'Pendiente', 'retroceso frente a la referencia']) {
    assert.ok(html.includes(texto), texto);
  }
  assert.ok(html.includes('sin validación en DIgSILENT del conjunto'));
});

test('050:RF-8/10 la vista muestra daños de lectura y versiones sin HTML ejecutable', async () => {
  const { pintar } = await cargar();
  const html = pintar({ fases: { activacion: { estado: 'bloqueado', motivo: '<script>daño</script>',
    versiones: { gru: 'abc123' } } }, bloqueos: [{ motivos: ['diario ilegible'] }],
    ultimo_ciclo: null, conjunto_activo: null });
  assert.ok(html.includes('Bloqueado'));
  assert.ok(html.includes('diario ilegible'));
  assert.ok(html.includes('gru: abc123'));
  assert.ok(html.includes('&lt;script&gt;daño&lt;/script&gt;'));
  assert.ok(!html.includes('<script>'));
});

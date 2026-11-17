import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// Spec 070, T16 (RF-80, RF-81): la tarjeta que el asistente deja para el clic del operador. Solo cinco tipos, cada uno
// con su forma: el resultado de un trabajo no elige rutas ni pinta otra cosa.
const raiz = fileURLToPath(new URL('..', import.meta.url));

async function cargar() {
  const r = await build({ stdin: { contents: `export * from './src/features/asistente/tarjetaOperadorLogica';`,
    resolveDir: raiz, loader: 'ts' }, bundle: true, write: false, format: 'cjs', platform: 'node' });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', r.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
  return mod.exports;
}

const previa = { borrador: 'a'.repeat(32), firma: 'b'.repeat(64), cuenta: 'operador@ejemplo.org', proveedor: 'google',
  para: ['cliente@otra.test'], cc: [], cco: [], asunto: 'Informe', cuerpo: 'x', enlace: null, adjuntos: [],
  validez: { valido: true, motivo: '' }, avisos: {}, limite_bytes: 1 };

test('la tarjeta del correo exige su borrador y su firma', async () => {
  const { tarjetaDe } = await cargar();
  const t = tarjetaDe('enviar_informe', { tarjeta: { tipo: 'enviar_informe', proveedor: 'google',
    para: ['cliente@otra.test', 'no es una dirección'], previa } });
  assert.equal(t.tipo, 'enviar_informe');
  assert.deepEqual(t.para, ['cliente@otra.test']);
  assert.equal(t.previa.firma, previa.firma);
  for (const mala of [{ ...previa, firma: 'corta' }, { ...previa, borrador: '../x' }, null]) {
    assert.equal(tarjetaDe('enviar_informe', { tarjeta: { tipo: 'enviar_informe', previa: mala } }), null);
  }
});

test('solo cinco tipos, y de la misma tarea del plan', async () => {
  const { tarjetaDe } = await cargar();
  assert.equal(tarjetaDe('estado', { tarjeta: { tipo: 'estado' } }), null);
  assert.equal(tarjetaDe('publicar_nube', { tarjeta: { tipo: 'conectar_nube' } }), null);
  assert.equal(tarjetaDe('publicar_nube', { tarjeta: 'publicar_nube' }), null);
  assert.equal(tarjetaDe(null, { tarjeta: { tipo: 'publicar_nube' } }), null);
  const p = tarjetaDe('publicar_nube', { tarjeta: { tipo: 'publicar_nube', proveedor: 'dropbox', salida: '../fuera' } });
  assert.equal(p.proveedor, null);
  assert.equal(p.salida, '');
});

test('conectar ofrece el proveedor que dijo la orden, o los registrados', async () => {
  const { tarjetaDe, proveedoresParaConectar } = await cargar();
  const proveedores = [
    { nombre: 'google', visible: 'Google Drive', registrado: true, se_puede_conectar: true, motivo: null, permisos: '' },
    { nombre: 'microsoft', visible: 'OneDrive', registrado: true, se_puede_conectar: true, motivo: null, permisos: '' },
    { nombre: 'otro', visible: 'X', registrado: true, se_puede_conectar: true, motivo: null, permisos: '' }];
  const todos = tarjetaDe('conectar_nube', { tarjeta: { tipo: 'conectar_nube', proveedor: null, proveedores } });
  assert.deepEqual(proveedoresParaConectar(todos).map((p) => p.nombre), ['google', 'microsoft']);
  const uno = tarjetaDe('conectar_nube', { tarjeta: { tipo: 'conectar_nube', proveedor: 'microsoft', proveedores } });
  assert.deepEqual(proveedoresParaConectar(uno).map((p) => p.nombre), ['microsoft']);
});

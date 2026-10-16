import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';

const entry = new URL('../src/projectBinding.ts', import.meta.url).pathname.replace(/^\/(.:\/)/, '$1');

async function cargar() {
  const salida = await build({
    entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

test('las advertencias de modificaciones manuales no bloquean el proyecto', async () => {
  const { estadoVinculoProyecto } = await cargar();
  const estado = estadoVinculoProyecto({
    name: 'P', path: 'P', feeders: ['A1'],
    binding: { project: 'P' },
    binding_blocked_reason: null,
    binding_warnings: [{
      code: 'PROJECT_BINDING_NATIVE_MODIFIED', message: 'Proyecto modificado',
      elements: [{ change: 'modified', class: 'ElmLne', full_name: 'Grid/L1' }],
    }],
  });

  assert.deepEqual(estado, { bloqueado: false, advertencias: 1, elementos: 1 });
});

test('un error bloqueante sigue deshabilitando las acciones nativas', async () => {
  const { estadoVinculoProyecto } = await cargar();
  const estado = estadoVinculoProyecto({
    name: 'P', path: 'P', feeders: ['A1'], binding: null,
    binding_blocked_reason: 'PROJECT_BINDING_MISSING', binding_warnings: [],
  });

  assert.deepEqual(estado, { bloqueado: true, advertencias: 0, elementos: 0 });
});

test('018:RF-11 sin fuente activa se usa sola la fuente del vínculo; con otra, con botón', async () => {
  const { usoDeLaFuente } = await cargar();
  const proyecto = (code, disponible) => ({
    name: 'P', path: 'P', feeders: ['A1'], binding: { project: 'P' },
    binding_blocked_code: code, binding_blocked_reason: code, binding_fuente_disponible: disponible,
  });

  assert.equal(usoDeLaFuente(proyecto('PROJECT_BINDING_NO_ACTIVE_SOURCE', true)), 'automatico');
  assert.equal(usoDeLaFuente(proyecto('PROJECT_BINDING_SOURCE_MISMATCH', true)), 'boton');
  assert.equal(usoDeLaFuente(proyecto('PROJECT_BINDING_NO_ACTIVE_SOURCE', false)), null);
  assert.equal(usoDeLaFuente(proyecto('PROJECT_BINDING_FOLDER_MISMATCH', true)), null);
  assert.equal(usoDeLaFuente(null), null);
});

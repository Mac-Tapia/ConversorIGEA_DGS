import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

// 065:RF-9: `URL.pathname` deja «%20» y la prueba fallaba en una ruta con espacios.
const entry = fileURLToPath(new URL('../src/operacionSet.ts', import.meta.url));

async function cargar() {
  const salida = await build({
    entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

test('063:RF-36 el diagnóstico sale con los campos de la API', async () => {
  const { cuerpoOperacionSet, FORMULARIO_SET } = await cargar();
  const { cuerpo, error } = cuerpoOperacionSet('P', ['A1', 'A2'], { ...FORMULARIO_SET, verificarFlujos: true });
  assert.equal(error, undefined);
  assert.deepEqual(Object.keys(cuerpo).sort(), ['accion', 'ajustes_flujo', 'cambios', 'conciliar_fases',
    'desactivar_variaciones', 'feeders', 'project', 'reabrir', 'salidas', 'sincronizar_cargas', 'verificar_flujos']);
  assert.equal(cuerpo.verificar_flujos, true);
});

test('063:RF-36 evaluar reúne cambios, variaciones y ajustes', async () => {
  const { cuerpoOperacionSet, FORMULARIO_SET } = await cargar();
  const { cuerpo } = cuerpoOperacionSet('P', ['A1'], {
    ...FORMULARIO_SET, accion: 'evaluar', cambios: '[{"clase": "ElmLne"}]', desactivar: ' V1, V2 ,', ajustes: '{"iopt_at": 1}',
  });
  assert.deepEqual(cuerpo.desactivar_variaciones, ['V1', 'V2']);
  assert.deepEqual(cuerpo.cambios, [{ clase: 'ElmLne' }]);
  assert.deepEqual(cuerpo.ajustes_flujo, { iopt_at: 1 });
});

test('063:RF-37 no se manda lo que el servidor rechazaría', async () => {
  const { cuerpoOperacionSet, FORMULARIO_SET } = await cargar();
  const f = FORMULARIO_SET;
  for (const [proyecto, alims, cambio] of [
    ['', ['A1'], {}],
    ['P', [], {}],
    ['P', ['A1'], { accion: 'aplicar' }],
    ['P', ['A1'], { accion: 'evaluar', verificarFlujos: true, cambios: '[{"a": 1}]' }],
    ['P', ['A1'], { accion: 'evaluar', cambios: '{"a": 1}' }],
    ['P', ['A1'], { accion: 'evaluar', cambios: 'no es json' }],
    ['P', ['A1'], { ajustes: '{"iopt_at": 1.5}' }],
    ['P', ['A1'], { ajustes: '[1]' }],
  ]) {
    const { cuerpo, error } = cuerpoOperacionSet(proyecto, alims, { ...f, ...cambio });
    assert.equal(cuerpo, undefined, JSON.stringify(cambio));
    assert.ok(error);
  }
});

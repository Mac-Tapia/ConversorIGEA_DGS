import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// 096:RF-8 (2026-11-12): con el 8765 ocupado por el programa instalado, el acceso directo abrió la web en el 8766; ese
// navegador no recordaba ningún espacio y la web creó uno vacío, aunque el operador tenía 42 en disco.
let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: { contents: "export { espacioParaRetomar } from './src/shared/useWorkspace';",
             resolveDir: fileURLToPath(new URL('../', import.meta.url)), loader: 'ts' },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external',
  });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

test('096:RF-8 retoma el último espacio con datos, no uno vacío recién creado', async () => {
  const { espacioParaRetomar } = await cargar();
  const lista = [
    { id: 'vacio_nuevo', modified_at: 300, inputs: {}, estado: 'ok' },
    { id: 'antiguo', modified_at: 100, inputs: { red: 'RED.txt' }, estado: 'ok' },
    { id: 'reciente', modified_at: 200, inputs: { vnr_package: 'ELOR' }, estado: 'ok' },
  ];
  assert.equal(espacioParaRetomar(lista), 'reciente');
});

test('096:RF-8 no retoma un espacio dañado ni de una versión más nueva', async () => {
  const { espacioParaRetomar } = await cargar();
  const lista = [
    { id: 'danado', modified_at: 500, inputs: { red: 'x' }, estado: 'danado' },
    { id: 'futuro', modified_at: 400, inputs: { red: 'x' }, estado: 'version_futura' },
    { id: 'bueno', modified_at: 100, inputs: { red: 'x' }, estado: 'ok' },
  ];
  assert.equal(espacioParaRetomar(lista), 'bueno');
});

test('096:RF-8 sin espacios con datos no retoma ninguno, y la web crea uno', async () => {
  const { espacioParaRetomar } = await cargar();
  assert.equal(espacioParaRetomar([]), null);
  assert.equal(espacioParaRetomar([{ id: 'vacio', modified_at: 1, inputs: {}, estado: 'ok' }]), null);
});

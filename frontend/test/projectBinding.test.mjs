import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const entry = fileURLToPath(new URL('../src/shared/projectBinding.ts', import.meta.url));
let renderPanel;

async function panelDeEntrada() {
  if (renderPanel) return renderPanel;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { InputsPanel } from './src/features/conversion/InputsPanel';
        export function render(mode, company, active = {}) {
          const value = {
            ws: { id: 'empresa-prueba', options: { input_mode: mode, empresa_espacio: company }, inputs: {}, missing_inputs: [] },
            health: { slots: { aliases: { grupo: 'aux', etiqueta: 'Equivalencias', obligatorio: false } }, capabilities: { access: true } },
            active, jobs: {}, run: async fn => fn(), setWs: () => {}, startJob: async () => undefined,
          };
          return renderToStaticMarkup(createElement(Ctx.Provider, { value }, createElement(InputsPanel)));
        }`,
      resolveDir: fileURLToPath(new URL('../', import.meta.url)), loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(
    createRequire(import.meta.url), modulo, modulo.exports,
  );
  renderPanel = modulo.exports.render;
  return renderPanel;
}

for (const mode of ['txt', 'mdb', 'vnr']) {
  test(`081:RF-51 el panel ${mode} conserva y muestra la empresa del espacio`, async () => {
    const render = await panelDeEntrada();
    const html = render(mode, 'Distribuidora de prueba');
    assert.match(html, /Empresa del espacio/);
    assert.match(html, /<input[^>]*name="empresa_espacio"[^>]*value="Distribuidora de prueba"/);
    assert.match(html, /Guardar empresa/);
    assert.match(html, /Tres TXT de CYMDIST/);
    assert.match(html, /Base Access/);
    assert.match(html, /VNR-GIS/);
  });
}

for (const lane of ['engine', 'powerfactory']) {
  test(`081:RF-51 la empresa no cambia mientras trabaja ${lane}`, async () => {
    const render = await panelDeEntrada();
    const html = render('txt', null, { [lane]: { id: 'trabajo' } });
    const input = html.match(/<input[^>]*name="empresa_espacio"[^>]*>/)?.[0];
    assert.ok(input, 'falta el campo de empresa del espacio');
    assert.match(input, /disabled/);
  });
}

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

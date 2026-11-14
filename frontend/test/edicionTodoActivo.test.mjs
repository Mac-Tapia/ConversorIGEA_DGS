import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// 086:RF-15, RF-16 — orden del usuario del 2026-11-13: «nada debería estar apagado ni bloqueado». En la edición de
// producto la web ocultaba el gemelo digital, el reentrenamiento, el equipo de revisión por roles, los modelos, el
// aprendizaje y la aceptación del asistente. Se pinta cada pantalla con `producto: true` y se busca lo que antes faltaba.

async function cargar() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { GemeloPIDE } from './src/features/powerfactory/GemeloPIDE';
    import { Asistente } from './src/features/asistente/Asistente';
    import { Ctx } from './src/shared/context';
    const valor = (producto) => ({ ws:{id:'W',options:{},inputs:{}}, jobs:{}, active:{},
      health:{edicion:{producto,beta:[]}}, run: async () => undefined, startJob: async () => undefined });
    export const gemelo = (producto) => renderToStaticMarkup(createElement(Ctx.Provider, { value: valor(producto) },
      createElement(GemeloPIDE, {project:'P',feeders:['F1']})));
    export const asistente = (producto) => renderToStaticMarkup(createElement(Ctx.Provider, { value: valor(producto) },
      createElement(Asistente)));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

test('086:RF-15 el gemelo digital se ofrece en producto igual que en desarrollo', async () => {
  const { gemelo } = await cargar();
  const producto = gemelo(true);
  assert.ok(producto.includes('Gemelo digital'), 'en producto falta el gemelo digital');
  assert.equal(producto, gemelo(false), 'las dos ediciones pintan lo mismo');
});

test('086:RF-15, RF-16 el asistente ofrece reentrenar, modelos, aprendizaje y aceptación en producto', async () => {
  const { asistente } = await cargar();
  const html = asistente(true);
  for (const t of ['Reentrenar', 'Estado de los modelos', 'propuestas y aceptación del agente']) assert.ok(html.includes(t), t);
  assert.equal(html, asistente(false), 'las dos ediciones pintan lo mismo');
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// Plan Maestro PM-20 (2026-11-19): la web ofrecía cada estudio como si estuviera listo, también los que no tenían su
// aceptación cerrada. Spec 100, RF-12: cada botón o pestaña de estudio dice «Sin validar» o queda apagado con su motivo.
let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { MarcaDeCelda } from './src/shared/MarcaValidacion';
    export { celdaDe, marcaDe, refDePestana } from './src/shared/matrizEstudios';
    export const pintar = (marca) => renderToStaticMarkup(createElement(MarcaDeCelda, { marca }));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

const celda = (motor, estado, motivo = '') => ({ motor, estado, motivo, evidencia: [] });
const MATRIZ = {
  motores: [{ clave: 'digsilent', nombre: 'DIgSILENT' }, { clave: 'abierto', nombre: 'Motores abiertos' }],
  estudios: [
    { clave: 'flujo', nombre: 'Flujo de potencia', celdas: [celda('digsilent', 'validado'), celda('abierto', 'validado')] },
    { clave: 'cortocircuito', nombre: 'Cortocircuito', celdas: [
      celda('digsilent', 'sin_validar', 'Falta su prueba de aceptación con este motor.'),
      celda('abierto', 'no_disponible', 'Sin motor abierto de cortocircuito en esta versión.')] },
  ],
};
const leer = (ruta) => readFileSync(new URL(ruta, import.meta.url), 'utf8');

test('100:RF-12 validado no dice nada; sin validar avisa y deja usarlo; no disponible se apaga con su motivo', async () => {
  const { marcaDe } = await cargar();
  assert.equal(marcaDe(MATRIZ, { estudio: 'flujo', motor: 'digsilent' }), null);
  const sin = marcaDe(MATRIZ, { estudio: 'cortocircuito', motor: 'digsilent' });
  assert.equal(sin.texto, 'Sin validar');
  assert.equal(sin.deshabilitado, false);
  assert.match(sin.titulo, /DIgSILENT/);
  const no = marcaDe(MATRIZ, { estudio: 'cortocircuito', motor: 'abierto' });
  assert.equal(no.texto, 'No disponible');
  assert.equal(no.deshabilitado, true);
  assert.match(no.titulo, /Motores abiertos: Sin motor abierto de cortocircuito/);
});

test('100:RF-12 sin la matriz del servidor, o un estudio que no trae, no se inventa ninguna marca', async () => {
  const { marcaDe, celdaDe } = await cargar();
  assert.equal(marcaDe(null, { estudio: 'flujo', motor: 'digsilent' }), null);
  assert.equal(celdaDe(MATRIZ, { estudio: 'otro', motor: 'digsilent' }), null);
  assert.equal(marcaDe(MATRIZ, { estudio: 'flujo', motor: 'pinn' }), null);
});

test('100:RF-12 la marca se pinta con su texto y su motivo, sin citas internas', async () => {
  const { marcaDe, pintar } = await cargar();
  assert.equal(pintar(null), '');
  const html = pintar(marcaDe(MATRIZ, { estudio: 'cortocircuito', motor: 'abierto' }));
  assert.match(html, /No disponible/);
  assert.match(html, /title="No disponible con Motores abiertos: Sin motor abierto de cortocircuito en esta versión\."/);
  assert.doesNotMatch(html, /RF-\d|spec|\b\d{3}\b|\(s\)/i);
});

test('100:RF-12 las pestañas de los módulos llevan el estudio y el motor de sus botones', async () => {
  const { refDePestana } = await cargar();
  assert.deepEqual(refDePestana('pit'), { estudio: 'pit', motor: 'abierto' });
  assert.deepEqual(refDePestana('vad'), { estudio: 'vad', motor: 'conversor' });
  assert.deepEqual(refDePestana('vnr'), { estudio: 'vnr', motor: 'conversor' });
  assert.deepEqual(refDePestana('pide'), { estudio: 'pide', motor: 'digsilent' });
  assert.deepEqual(refDePestana('largo'), { estudio: 'largo_plazo', motor: 'digsilent' });
  assert.equal(refDePestana('normativa'), null);
});

test('100:RF-12 los estudios de 4.2, la calibración, las obras, el PIDE y el gemelo llevan su marca', () => {
  const estudios = leer('../src/features/powerfactory/EstudiosPF.tsx');
  assert.match(estudios, /marcaDe\(matriz, \{ estudio: e\.clave, motor: 'digsilent' \}\)/);
  assert.match(estudios, /disabled=\{marca\?\.deshabilitado\}/);
  const cargas = leer('../src/features/powerfactory/CargasTab.tsx');
  assert.match(cargas, /<MarcaValidacion estudio="calibracion" motor="digsilent" \/>/);
  assert.match(cargas, /<MarcaValidacion estudio="obras" motor="digsilent" \/>/);
  const gemelo = leer('../src/features/powerfactory/GemeloPIDE.tsx');
  assert.match(gemelo, /<MarcaValidacion estudio="gemelo" motor="pinn" \/>/);
  assert.match(gemelo, /estudio=\{plazoPeticion === 'largo_plazo' \? 'largo_plazo' : 'pide'\}/);
  assert.match(leer('../src/app/App.tsx'), /refDePestana\(t\.id\)/);
});

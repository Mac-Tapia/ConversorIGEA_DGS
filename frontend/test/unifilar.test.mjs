import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Spec 111, T23 (RF-23): el unifilar del alimentador junto al plano, sin navegador. Mismos códigos que el plano, la
// misma selección y los mismos resultados; la forma la da el servidor y el navegador no decide ninguna regla eléctrica.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const PLANO = join(FRONT, 'src', 'features', 'plano');

let modulo;
async function cargar() {
  assert.ok(existsSync(join(PLANO, 'UnifilarRed.tsx')), 'falta src/features/plano/UnifilarRed.tsx (111:RF-23)');
  assert.ok(existsSync(join(PLANO, 'logicaUnifilar.ts')), 'falta src/features/plano/logicaUnifilar.ts (111:RF-23)');
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { UnifilarRed } from './src/features/plano/UnifilarRed';
        export * from './src/features/plano/logicaUnifilar';
        export const pintar = (props) => renderToStaticMarkup(createElement(UnifilarRed, props));`,
      resolveDir: FRONT, loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

const barra = (codigo) => ({ codigo, nombre_pf: codigo, lat: null, lon: null, deducido: [], calidad: 'ok', avisos: [], errores: [] });
const tramo = (codigo, desde, hasta) => ({ codigo, nombre_pf: codigo, desde, hasta, fases: 'ABC', tipo: 'AAAC', aereo: true,
  longitud_m: 100, vertices: [[-14, -75.7], [-14.001, -75.7]], paralelo_con: [], original: {}, deducido: [], calidad: 'ok', avisos: [] });
const vista = () => ({
  alimentador: 'A1', kv: 10, fuente: 'N0', source_crs: null, target_crs: 'EPSG:4326', sin_coordenadas: false, revision: 'r'.repeat(64),
  barras: ['N0', 'N1', 'N2', 'N3', 'NX'].map(barra),
  tramos: [tramo('T-1', 'N0', 'N1'), tramo('T-2', 'N1', 'N2'), tramo('T-3', 'N1', 'N3'), tramo('T-9', 'N2', 'NZ')],
  sed: [{ codigo: 'S-5', nombre_pf: 'S-5', barra: 'N3', tramo: null, kva: 50 }],
  maniobras: [{ codigo: 'SW-1', nombre_pf: 'SW-1', clase: 'seccionador', tramo: 'T-2', barra: null, estado: 'abierto' }],
  tipos_de_linea: ['AAAC'], colisiones: [], avisos: [],
  unifilar: { fuente: 'N0', niveles: 4, ancho: 2, sin_alcanzar: ['NX'],
    barras: [{ codigo: 'N0', nivel: 0, orden: 0 }, { codigo: 'N1', nivel: 1, orden: 0 }, { codigo: 'N2', nivel: 2, orden: 0 },
      { codigo: 'N3', nivel: 2, orden: 1 }, { codigo: 'NX', nivel: 3, orden: 0 }] },
});
const capas = (incumple) => ({ pintable: true, motivo: '', mensajes: [], motor: 'pandapower', motor_texto: 'pandapower',
  caso: 'Caso base', revision: 'r'.repeat(64), origen_umbral: 'norma', variacion: 'v1',
  capas: { tension: { leyenda: { magnitud: 'Tensión', unidad: 'p.u.', umbral: null, caso: 'Caso base', revision: 'r', motor_texto: 'pandapower' },
    elementos: [{ codigo: 'N2', valor: 0.91, kv: 10, banda: incumple ? 'baja' : 'normal', motor: 'pandapower',
      incumple: incumple ? { texto: 'Tensión baja', umbral: 0.95 } : null }] } } });

test('111:RF-23 la disposición sale del nivel y el orden del servidor, y la cabecera va a la izquierda', async () => {
  const { disposicionUnifilar, PASO_X, PASO_Y } = await cargar();
  const d = disposicionUnifilar(vista());
  const x = Object.fromEntries(d.barras.map((b) => [b.codigo, b]));
  assert.equal(d.fuente, 'N0');
  assert.ok(x.N0.x < x.N1.x && x.N1.x < x.N2.x, 'los niveles avanzan desde la cabecera');
  assert.equal(x.N2.x, x.N3.x, 'mismo nivel, misma columna');
  assert.equal(x.N3.y - x.N2.y, PASO_Y);
  assert.equal(x.N1.x - x.N0.x, PASO_X);
  // T-9 llega a una barra que no está: se cuenta y no se dibuja; no se inventa su extremo.
  assert.deepEqual(d.sinDibujar, ['T-9']);
  assert.deepEqual(d.tramos.map((t) => t.codigo), ['T-1', 'T-2', 'T-3']);
  assert.deepEqual(d.sinAlcanzar, ['NX']);
});

test('111:RF-2, RF-23 el unifilar pinta cada elemento con el mismo código del plano y avisa de lo que no alcanza', async () => {
  const { pintar } = await cargar();
  const html = pintar({ vista: vista(), elegido: null, capas: null, onElegir: () => {} });
  for (const c of ['N0', 'N1', 'N2', 'N3', 'NX', 'T-1', 'T-2', 'T-3', 'S-5', 'SW-1'])
    assert.ok(html.includes(`data-codigo="${c}"`), `falta ${c} en el unifilar`);
  assert.ok(!html.includes('data-codigo="T-9"'), 'pinta un tramo sin sus dos barras');
  assert.match(html, /role="img"/);
  assert.match(html, /Unifilar del alimentador A1/);
  assert.match(html, /Barras sin camino desde la cabecera: 1/);
  assert.match(html, /unifilar-abierto/, 'la maniobra abierta no se distingue');
  // Un unifilar ancho se desplaza: su caja es una región con nombre a la que se llega con el teclado (axe:
  // scrollable-region-focusable, WCAG 2.1.1).
  assert.match(html, /<div class="unifilar" role="region" aria-label="Unifilar del alimentador A1" tabindex="0">/,
    'la caja desplazable del unifilar no se alcanza con el teclado');
});

test('111:RF-20, RF-23 la selección es la misma: el elegido se resalta en el unifilar', async () => {
  const { pintar } = await cargar();
  const html = pintar({ vista: vista(), elegido: 'T-2', capas: null, onElegir: () => {} });
  assert.match(html, /data-codigo="T-2" class="[^"]*unifilar-elegido/);
  assert.equal((html.match(/unifilar-elegido/g) || []).length, 1, 'se resalta más de un elemento');
});

test('111:RF-10, RF-13, RF-23 los mismos resultados del plano, y un incumplimiento se dice con texto', async () => {
  const { pintar, bandasPorCodigo } = await cargar();
  assert.equal(bandasPorCodigo(capas(true)).get('N2'), 'alerta');
  assert.equal(bandasPorCodigo(capas(false)).get('N2'), 'normal');
  assert.equal(bandasPorCodigo({ ...capas(true), pintable: false }).size, 0, 'pinta resultados no pintables');
  const html = pintar({ vista: vista(), elegido: null, capas: capas(true), onElegir: () => {} });
  assert.match(html, /data-codigo="N2" class="[^"]*unifilar-alerta/);
  assert.match(html, /<title>N2 · Incumple<\/title>/, 'el incumplimiento va solo con color');
});

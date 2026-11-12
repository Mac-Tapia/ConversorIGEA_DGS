import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Usuario (2026-11-12): la red sobre un plano «como en Google Maps», con calles y satélite. En el programa instalado la
// salida de las teselas está apagada y solo se encendía con su variable al arrancar: el operador veía fondo blanco.
let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        export { ayudaFondoMapa, cambiarFondoMapa, ETIQUETA_FONDO_MAPA } from './src/features/conversion/OptionsPanel';
        import { FondoMapa } from './src/features/conversion/OptionsPanel';
        export function pintar(props) { return renderToStaticMarkup(createElement(FondoMapa, props)); }`,
      resolveDir: fileURLToPath(new URL('../', import.meta.url)), loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

const teselas = (cambios) => ({
  nombre: 'teselas', encendida: false, origen: 'edicion', variable: 'CSG_SALIDA_TESELAS',
  destino: 'OpenStreetMap y Esri World Imagery', para_que: 'el fondo', cambiable: true, ...cambios,
});
const nada = () => {};

test('086:RF-67 el interruptor se puede cambiar cuando no lo fija la variable', async () => {
  const { pintar, ETIQUETA_FONDO_MAPA } = await cargar();
  const html = pintar({ salida: teselas({ encendida: true, origen: 'equipo' }), locked: false, onChange: nada });
  assert.ok(html.includes(ETIQUETA_FONDO_MAPA), html);
  assert.match(html, /checked=""/);
  assert.doesNotMatch(html, /disabled=""/);
  assert.equal(ETIQUETA_FONDO_MAPA, 'Fondo de mapa (calles y satélite; pide las teselas a internet)');
});

test('086:RF-68 con la variable fijada, el interruptor no se deja cambiar y lo dice', async () => {
  const { pintar, ayudaFondoMapa } = await cargar();
  const salida = teselas({ encendida: true, origen: 'variable', cambiable: false });
  const html = pintar({ salida, locked: false, onChange: nada });
  assert.match(html, /disabled=""/);
  assert.match(ayudaFondoMapa(salida), /CSG_SALIDA_TESELAS al arrancar/);
  assert.ok(html.includes('CSG_SALIDA_TESELAS'), 'el aviso va en el propio interruptor');
});

test('086:RF-67 sin la salida leída o con un trabajo del motor en curso, no se cambia', async () => {
  const { pintar } = await cargar();
  assert.match(pintar({ salida: null, locked: false, onChange: nada }), /disabled=""/);
  assert.match(pintar({ salida: teselas(), locked: true, onChange: nada }), /disabled=""/);
});

test('086:RF-67 la ayuda dice que vale para las conversiones siguientes y no cambia los mapas hechos', async () => {
  const { ayudaFondoMapa } = await cargar();
  const texto = ayudaFondoMapa(teselas({ origen: 'equipo' }));
  assert.match(texto, /conversiones siguientes/);
  assert.match(texto, /los mapas ya generados no cambian/);
  assert.match(texto, /OpenStreetMap y Esri World Imagery/);
  assert.equal(ayudaFondoMapa(null), '');
});

test('086:RF-67 cambiar guarda en el servidor y enseña lo que devuelve', async () => {
  const { cambiarFondoMapa } = await cargar();
  const pedidas = [];
  let puesta;
  const devuelta = teselas({ encendida: true, origen: 'equipo' });
  const r = await cambiarFondoMapa(async (e) => { pedidas.push(e); return { salidas: [teselas({ nombre: 'vias' }), devuelta] }; },
    true, (s) => { puesta = s; });
  assert.deepEqual(pedidas, [true]);
  assert.equal(r, devuelta);
  assert.equal(puesta, devuelta);
  // Un error del servidor (run devuelve undefined) no cambia lo que se muestra.
  puesta = undefined;
  assert.equal(await cambiarFondoMapa(async () => undefined, false, (s) => { puesta = s; }), undefined);
  assert.equal(puesta, undefined);
});

test('086:RF-67 el panel lo pone junto a «Vista previa en mapa (HTML)» y lo pide a su ruta', () => {
  const panel = readFileSync(new URL('../src/features/conversion/OptionsPanel.tsx', import.meta.url), 'utf8');
  const previa = panel.indexOf('label="Vista previa en mapa (HTML)"');
  const fondo = panel.indexOf('<FondoMapa ');
  assert.ok(previa > 0 && fondo > previa && panel.slice(previa, fondo).split('<Toggle').length === 1);
  const cliente = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8');
  assert.match(cliente, /'\/api\/salidas\/teselas', json\('POST', \{ encendida \}\)/);
});

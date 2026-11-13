import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// 2026-11-12: con la revisión de libros nuevos corriendo como trabajo del motor, «Cargar / listar alimentadores»
// quedó desactivado y luego en cola, y el aviso «Regenerando el dataset…» seguía a la vista cuando ya había terminado.
let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { FeedersPanel } from './src/features/conversion/FeedersPanel';
        export { esAlerta, porConfirmar, textoDelDataset, textoDelFondo, tituloDelAviso } from './src/app/AvisosLibros';
        export function panel(active) {
          const value = {
            ws: { id: 'prueba', loaded: false, missing_inputs: [], totals: {}, catalog_report: null, active_run_id: null,
                  options: {}, demanda: { clientes: { path: 'x' } } },
            health: { capabilities: {}, crs_presets: [], parallel: { auto: 2, cpus: 4 } },
            feeders: [], outputs: [], selected: [], setSelected: () => {}, active, jobs: {},
            run: async (fn) => fn(), setWs: () => {}, startJob: async () => undefined, refresh: async () => null,
            refreshHealth: () => {}, librosNuevosSeq: 3,
          };
          return renderToStaticMarkup(createElement(Ctx.Provider, { value }, createElement(FeedersPanel)));
        }`,
      resolveDir: fileURLToPath(new URL('../', import.meta.url)), loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

function botonCargar(html) {
  const boton = html.match(/<button[^>]*>(?:Cargar \/ listar alimentadores|Volver a cargar)<\/button>/);
  assert.ok(boton, 'no está el botón «Cargar / listar alimentadores»');
  return boton[0];
}

test('104:RF-31 una revisión de fondo no desactiva «Cargar / listar alimentadores»', async () => {
  const { panel } = await cargar();
  // Lo de fondo no es un trabajo de la cola: con la revisión en marcha, no hay nada en ningún carril.
  assert.doesNotMatch(botonCargar(panel({})), /disabled/);
  // Un trabajo del operador en el motor sí lo desactiva, como siempre.
  assert.match(botonCargar(panel({ engine: { id: 'j', lane: 'engine', status: 'running' } })), /disabled/);
});

test('104:RF-31 el aviso de libros no usa la cola ni la barra de trabajos', () => {
  const avisos = readFileSync(new URL('../src/app/AvisosLibros.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(avisos, /startJob|active\.|kind === 'libros_nuevos'/);
  const cliente = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8');
  assert.match(cliente, /libros-nuevos\/verificar-todos/);
});

test('104:RF-31 el indicador de fondo dice lo que hace y calla cuando está libre', async () => {
  const { textoDelFondo } = await cargar();
  assert.equal(textoDelFondo({ estado: 'libre', texto: null, por_verificar: 0 }), null);
  assert.equal(textoDelFondo({ estado: 'en_espera', texto: 'Revisión de libros en pausa' }), 'Revisión de libros en pausa');
  assert.match(textoDelFondo({ estado: 'libre', por_verificar: 2 }), /2 libro\(s\) por verificar/);
});

test('104:RF-38 el dataset desactualizado dice cuándo se regenerará', async () => {
  const { textoDelDataset } = await cargar();
  const hora = () => '10:35';
  assert.match(textoDelDataset({ estado: 'desactualizado', libros_nuevos: ['a'], espera: 'reposo', previsto: 1, reposo_min: 5 }, hora),
    /hacia las 10:35, tras 5 min sin trabajos/);
  assert.match(textoDelDataset({ estado: 'desactualizado', espera: 'motor_ocupado', reposo_min: 5 }, hora),
    /cuando el motor lleve 5 min libre/);
  assert.match(textoDelDataset({ estado: 'desactualizado', espera: 'faltan_fuentes' }, hora), /la cabecera y los medidores/);
  assert.equal(textoDelDataset({ estado: 'al_dia' }, hora), null);
});

test('104:RF-39 el aviso de libros se relee del servidor con cada evento del carril de fondo', () => {
  const uso = readFileSync(new URL('../src/shared/useWorkspace.ts', import.meta.url), 'utf8');
  assert.match(uso, /ev\.type === 'libros_nuevos'/);
  assert.match(uso, /setLibrosNuevosSeq/);
  const app = readFileSync(new URL('../src/app/App.tsx', import.meta.url), 'utf8');
  assert.match(app, /librosNuevosSeq: w\.librosNuevosSeq/);
  const avisos = readFileSync(new URL('../src/app/AvisosLibros.tsx', import.meta.url), 'utf8');
  assert.match(avisos, /useEffect\(\(\) => \{ leer\(\); \}, \[leer, librosNuevosSeq\]\)/);
});

test('104:RF-44, 104:RF-47 cada aviso dice de qué es y el interrumpido o el apartado se ven como alerta', async () => {
  const { esAlerta, tituloDelAviso } = await cargar();
  assert.equal(tituloDelAviso('dataset'), 'Dataset del pronóstico.');
  assert.equal(tituloDelAviso('apartado'), 'Libro de demanda apartado.');
  assert.equal(tituloDelAviso('clientes'), 'Libro de demanda reconocido.');
  assert.ok(esAlerta('La regeneración del dataset del pronóstico quedó interrumpida: sin proceso vivo'));
  assert.ok(esAlerta('0225 Pulso e.xlsx: queda fuera del dataset del pronóstico: formato no reconocido'));
});

test('089:RF-110 el aviso de un formato pide solo las columnas que faltan, con su huella', async () => {
  const { porConfirmar } = await cargar();
  assert.deepEqual(porConfirmar({ huella: '0123456789ab', falta: ['ERI'] }), { huella: '0123456789ab', falta: ['ERI'] });
  assert.equal(porConfirmar({ huella: '0123456789ab', falta: [] }), null);
  assert.equal(porConfirmar(null), null);
});

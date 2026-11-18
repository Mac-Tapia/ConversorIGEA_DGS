import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Spec 111, T15: la pestaña «Plano de la red». Sin navegador: el protocolo con la página del plano, el teclado, la
// tabla virtualizada, el inspector, las capas y la comparación, y que el navegador no decide ninguna regla eléctrica.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const SRC = join(FRONT, 'src');
const PLANO = join(SRC, 'features', 'plano');
const API = join(SRC, 'api', 'plano.ts');

let modulo;
async function cargar() {
  assert.ok(existsSync(API), 'falta src/api/plano.ts');
  assert.ok(existsSync(join(PLANO, 'PlanoRed.tsx')), 'falta src/features/plano/PlanoRed.tsx');
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { InspectorElemento } from './src/features/plano/InspectorElemento';
        import { CapasResultados, Comparacion } from './src/features/plano/CapasResultados';
        import { EdicionesPlano } from './src/features/plano/EdicionesPlano';
        import { TablaElementos } from './src/features/plano/TablaElementos';
        export { ENTRADA, SALIDA, leerMensaje, mensajeAlPlano } from './src/features/plano/mensajesPlano';
        export * as logica from './src/features/plano/logicaPlano';
        export { siguienteIndice, ventanaDeFilas, buscarPorCodigo, elementosDe } from './src/features/plano/logicaPlano';
        import { Ctx } from './src/shared/context';
        import { PlanoRed } from './src/features/plano/PlanoRed';
        export const pintarPestana = (ctx) => renderToStaticMarkup(createElement(Ctx.Provider, { value: ctx }, createElement(PlanoRed)));
        export { TEXTOS } from './src/features/plano/textosPlano';
        export const pintar = (c, props) => renderToStaticMarkup(createElement(
          { InspectorElemento, CapasResultados, Comparacion, EdicionesPlano, TablaElementos }[c], props));`,
      resolveDir: FRONT, loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

const nada = () => {};
const vista = () => ({
  alimentador: 'A1', kv: 10, source_crs: null, target_crs: 'EPSG:4326', sin_coordenadas: false, revision: 'r'.repeat(64),
  tramos: [{ codigo: 'T-1', nombre_pf: 'T-1', desde: 'N1', hasta: 'N2', fases: 'ABC', tipo: 'AAAC', aereo: true,
    longitud_m: 120.5, vertices: [[-14, -75.7], [-14.001, -75.7]], paralelo_con: [],
    original: { tipo: 'AAAC35', fase: 'ABC', longitud_m: null },
    deducido: [{ campo: 'longitud_m', original: null, valor: 120.5, regla: 'longitud_del_trazado',
      motivo: 'la fuente no da la longitud: se mide en el trazado', confianza: null, nivel: 'inferred' }],
    calidad: 'aviso', avisos: ['trazo corto'], errores: [] }],
  barras: [{ codigo: 'N1', nombre_pf: 'N1', lat: -14, lon: -75.7, deducido: [], calidad: 'ok', avisos: [], errores: [] },
    { codigo: 'N2', nombre_pf: 'N2', lat: -14.001, lon: -75.7, deducido: [], calidad: 'ok', avisos: [], errores: [] }],
  sed: [], maniobras: [{ codigo: 'SW-9', nombre_pf: 'SW-9', clase: 'seccionador', tramo: 'T-1', barra: 'N1', estado: 'cerrado' }],
  tipos_de_linea: ['AAAC'], colisiones: [], avisos: [],
});

test('111:RF-15 los tipos del plano salen del contrato generado y no se escriben a mano', () => {
  assert.ok(existsSync(API), 'falta src/api/plano.ts');
  const texto = readFileSync(API, 'utf8');
  assert.match(texto, /from '\.\/esquema'/);
  assert.doesNotMatch(texto, /\binterface\s+\w+/);
  assert.doesNotMatch(texto, /\btype\s+\w+\s*=\s*\{/);
  for (const t of ['PlanoRespuesta', 'VariacionPlanoRespuesta', 'CapasPlanoRespuesta', 'ComparacionPlanoRespuesta'])
    assert.ok(texto.includes(`S['${t}']`), t);
});

test('111:RF-14 la pestaña solo acepta de la página del plano los mensajes de su esquema', async (t) => {
  const { leerMensaje, SALIDA, ENTRADA, mensajeAlPlano } = await cargar();
  const marco = {};
  // test_frontend_rutas copia solo el frontend a una ruta con espacios: allí no está el código del servidor y el
  // cruce con sus listas se hace donde está (como avisosEnSuPaso); lo demás de la prueba corre igual.
  const ruta = join(FRONT, '..', 'src', 'convertersmartgrid', 'adaptadores/pagina_plano.py');
  if (existsSync(ruta)) {
    const pagina = readFileSync(ruta, 'utf8');
    const lista = (n) => JSON.parse(pagina.match(new RegExp(`${n} = \\(([^)]*)\\)`))[1].replace(/'/g, '"').replace(/^/, '[').replace(/,?\s*$/, ']'));
    assert.deepEqual([...ENTRADA], lista('MENSAJES_ENTRADA'));
    assert.deepEqual([...SALIDA], lista('MENSAJES_SALIDA'));
  } else {
    t.diagnostic('sin src/ junto al frontend (copia aislada): el cruce con pagina_plano.py se hace en el repositorio');
  }
  // El marco va con sandbox sin allow-same-origin: su origen es opaco y el navegador lo da como «null».
  const bueno = { source: marco, origin: 'null', data: { tipo: 'seleccionado', clase: 'tramo', codigo: 'T-1', alimentador: 'A1' } };
  assert.deepEqual(leerMensaje(bueno, marco), bueno.data);
  assert.equal(leerMensaje({ ...bueno, source: {} }, marco), null);
  assert.equal(leerMensaje({ ...bueno, origin: 'https://otro.ejemplo' }, marco), null, 'acepta otro origen');
  assert.equal(leerMensaje({ ...bueno, origin: undefined }, marco), null, 'acepta un mensaje sin origen');
  assert.equal(leerMensaje({ source: marco, origin: 'null', data: { tipo: 'borrar', codigo: 'T-1' } }, marco), null);
  assert.equal(leerMensaje({ source: marco, data: { tipo: 'seleccionado', clase: 'tramo', codigo: 3 } }, marco), null);
  assert.equal(leerMensaje({ source: marco, data: 'seleccionado' }, marco), null);
  assert.deepEqual(mensajeAlPlano('seleccionar', { codigo: 'T-1' }), { tipo: 'seleccionar', codigo: 'T-1' });
  assert.throws(() => mensajeAlPlano('borrar', {}));
});

test('111:RF-14 todo con teclado: flechas, inicio, fin y página en la lista de elementos', async () => {
  const { siguienteIndice } = await cargar();
  assert.equal(siguienteIndice(0, 'ArrowDown', 10), 1);
  assert.equal(siguienteIndice(0, 'ArrowUp', 10), 0);
  assert.equal(siguienteIndice(9, 'ArrowDown', 10), 9);
  assert.equal(siguienteIndice(4, 'Home', 10), 0);
  assert.equal(siguienteIndice(4, 'End', 10), 9);
  assert.equal(siguienteIndice(0, 'PageDown', 100, 20), 20);
  assert.equal(siguienteIndice(3, 'x', 10), null);
});

test('111:RF-1 la tabla es virtualizada: con miles de elementos pinta solo su ventana', async () => {
  const { ventanaDeFilas, pintar } = await cargar();
  const v = ventanaDeFilas(3000, 400, 30, 5000);
  assert.ok(v.inicio > 0 && v.fin - v.inicio < 40 && v.fin <= 5000);
  const filas = Array.from({ length: 5000 }, (_, i) => ({ clase: 'tramo', codigo: `T-${i}`, alimentador: 'A1', detalle: '' }));
  const html = pintar('TablaElementos', { filas, seleccionado: null, onElegir: nada });
  assert.ok((html.match(/<tr/g) ?? []).length < 60, 'pinta todas las filas');
  assert.match(html, /aria-rowcount="5001"/);
});

test('111:RF-1 la rejilla de elementos es la tabla misma: sus filas son hijas del grid (WAI-ARIA, axe)', async () => {
  const { pintar } = await cargar();
  const filas = [{ clase: 'tramo', codigo: 'T-1', alimentador: 'A1', detalle: '' }];
  const html = pintar('TablaElementos', { filas, seleccionado: null, onElegir: nada });
  assert.match(html, /<table[^>]*role="grid"[^>]*aria-label="Elementos del alimentador"/, 'el grid no es el <table>');
  assert.doesNotMatch(html, /<div[^>]*role="grid"/, 'el grid envuelve un <table>: aria-required-children');
});

test('111:RF-2, RF-3 el inspector dice el código, el dato original, lo deducido con su motivo y la calidad', async () => {
  const { pintar, elementosDe, buscarPorCodigo } = await cargar();
  const elementos = elementosDe([vista()]);
  assert.deepEqual(buscarPorCodigo(elementos, 't-1').map((e) => e.codigo), ['T-1']);
  const html = pintar('InspectorElemento', { elemento: elementos.find((e) => e.codigo === 'T-1') });
  for (const t of ['T-1', 'AAAC35', 'la fuente no da la longitud: se mide en el trazado', 'trazo corto']) assert.ok(html.includes(t), t);
  assert.match(html, /Con avisos/);
});

const capas = () => ({
  pintable: true, motivo: '', mensajes: [], motor: 'abierto', motor_texto: 'motor abierto (pandapower)', caso: 'Caso A',
  revision: 'r'.repeat(64), origen_umbral: 'por defecto', variacion: 'v1',
  capas: { tension: { leyenda: { magnitud: 'Tensión por barra', unidad: 'p.u.', umbral: { min: 0.95, max: 1.05 }, caso: 'Caso A',
    revision: 'r', motor: 'abierto', motor_texto: 'motor abierto (pandapower)', origen_umbral: 'por defecto' },
    elementos: [{ codigo: 'N2', valor: 0.91, kv: 10, banda: 'baja', motor: 'abierto',
      incumple: { texto: 'Tensión baja: 0,91 p.u., por debajo del mínimo de 0,95 p.u.', icono: 'alerta', valor: 0.91, umbral: 0.95 } }] } },
});

test('111:RF-10, RF-13, RF-18 las capas dicen unidad, umbral, caso y motor, y cada incumplimiento con texto e icono', async () => {
  const { pintar } = await cargar();
  const html = pintar('CapasResultados', { capas: capas(), onElegir: nada });
  for (const t of ['Tensión por barra', 'p.u.', 'Caso A', 'motor abierto (pandapower)', 'por debajo del mínimo de 0,95 p.u.'])
    assert.ok(html.includes(t), t);
  assert.match(html, /aria-label="Incumple"/);
  const no = pintar('CapasResultados', { capas: { ...capas(), pintable: false, motivo: 'El estudio no convergió: no hay resultados que pintar.', capas: {} }, onElegir: nada });
  assert.ok(no.includes('no convergió'));
});

test('111:RF-12, RF-19 la comparación dice si los motores son distintos junto a la diferencia', async () => {
  const { pintar } = await cargar();
  const c = { casos: [{ caso: 'A', variacion: 'v1', motor: 'abierto' }, { caso: 'B', variacion: 'v2', motor: 'DIgSILENT' }],
    mismo_motor: false, aviso_motores: 'Los dos casos se calcularon con motores distintos.', comparable: true, motivo: '',
    elementos: [{ codigo: 'N2', magnitud: 'tension', a: 0.97, b: 0.95, diferencia: -0.02, banda_a: 'normal', banda_b: 'normal', solo_en: null }] };
  const html = pintar('Comparacion', { comparacion: c, onElegir: nada });
  assert.ok(html.includes('motores distintos') && html.includes('N2'));
});

test('111:RF-9 las ediciones sin confirmar se deshacen y rehacen; confirmada, ya no', async () => {
  const { pintar } = await cargar();
  const variacion = { formato: 'f', id: 'v1', alimentador: 'A1', caso: 'Caso A', revision: 'r', revision_cambiada: false, version: 2,
    estado: 'abierta', ediciones: [{ tipo: 'maniobra', codigo: 'SW-9', estado: 'abierto', antes: 'cerrado' }],
    deshechas: [{ tipo: 'maniobra', codigo: 'SW-8', estado: 'abierto', antes: 'cerrado' }] };
  const props = { variacion, ocupado: false, onDeshacer: nada, onRehacer: nada, onConfirmar: nada };
  const abierta = pintar('EdicionesPlano', props);
  assert.ok(abierta.includes('SW-9') && abierta.includes('Deshacer') && abierta.includes('Rehacer'));
  assert.doesNotMatch(abierta, /disabled=""/);
  const cerrada = pintar('EdicionesPlano', { ...props, variacion: { ...variacion, estado: 'confirmada', deshechas: [] } });
  assert.equal((cerrada.match(/disabled=""/g) ?? []).length, 3);
});

test('111:RF-16 la pestaña del plano se añade y no se quita ninguna', () => {
  const app = readFileSync(join(SRC, 'app', 'App.tsx'), 'utf8');
  for (const id of ['results', 'cargas', 'clientes_fijos', 'catalog', 'system', 'asistente', 'plano'])
    assert.ok(app.includes(`id: '${id}'`), id);
  assert.ok(app.includes("label: 'Plano de la red'"));
});

const fuentes = () => (existsSync(PLANO) ? readdirSync(PLANO).filter((f) => /\.tsx?$/.test(f)) : []);
const sinComentarios = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

test('111:RF-15 el navegador no decide ninguna regla eléctrica ni guarda umbrales', () => {
  assert.ok(fuentes().length >= 6, 'faltan los ficheros de features/plano');
  for (const f of fuentes()) {
    const texto = sinComentarios(readFileSync(join(PLANO, f), 'utf8'));
    assert.doesNotMatch(texto, /tension_m(in|ax)_pu|cargabilidad_max|\b0\.9[05]\b|\b1\.0[5]\b/, f);
  }
});

test('111:RF-14 textos cortos, sin requisitos ni jerga interna', async () => {
  const { TEXTOS } = await cargar();
  for (const [clave, t] of Object.entries(TEXTOS)) {
    assert.ok(typeof t === 'string' && t.length <= 110, `${clave}: ${t}`);
    assert.doesNotMatch(t, /RF-\d|\d{3}:RF|CSG_|nombre_pf|loc_name|pandapower|json/i, clave);
  }
  for (const f of fuentes()) assert.doesNotMatch(sinComentarios(readFileSync(join(PLANO, f), 'utf8')), /RF-\d|CSG_/, f);
});

const almacen = (getItem, setItem = () => {}) => ({ getItem, setItem });
const lanza = () => { throw new Error('acceso al almacenamiento denegado'); };

test('111:RF-4 el navegador solo recuerda la variación que se miraba; si el almacenamiento falla o está vacío, nada', async () => {
  const { logica } = await cargar();
  assert.equal(typeof logica.variacionRecordada, 'function', 'falta variacionRecordada');
  assert.equal(typeof logica.recordarVariacion, 'function', 'falta recordarVariacion');
  assert.equal(logica.variacionRecordada(almacen(() => null), 'w1'), null);
  assert.equal(logica.variacionRecordada(almacen(lanza), 'w1'), null);
  assert.equal(logica.variacionRecordada(almacen(() => '["a","b"]'), 'w1'), null, 'una lista no es una variación');
  assert.equal(logica.variacionRecordada(almacen(() => '0123456789abcdef'), 'w1'), '0123456789abcdef');
  assert.doesNotThrow(() => logica.recordarVariacion(almacen(() => null, lanza), 'w1', '0123456789abcdef'));
  assert.equal(logica.variacionRecordada(null, 'w1'), null);
});

test('111:RF-4, RF-12 la lista de variaciones sale de la API, no del navegador', () => {
  const api = readFileSync(API, 'utf8');
  assert.ok(api.includes("S['VariacionesPlanoRespuesta']") && /variaciones: \(/.test(api), 'el cliente no lista las variaciones');
  const pestana = readFileSync(join(PLANO, 'PlanoRed.tsx'), 'utf8');
  assert.ok(pestana.includes('plano.variaciones('), 'la pestaña no pide la lista al servidor');
  assert.doesNotMatch(sinComentarios(pestana), /localStorage/, 'la pestaña usa el almacenamiento sin la guarda común');
});

test('111:RF-4 con el almacenamiento vacío o que lanza, la pestaña carga igual', async () => {
  const { pintarPestana } = await cargar();
  const ctx = { ws: { id: 'w1', options: {}, inputs: {} }, feeders: [{ feeder: 'A1' }], selected: [], jobs: {}, active: {},
    run: async () => undefined, startJob: async () => undefined, health: { edicion: { producto: true, beta: [] } } };
  const previo = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  try {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get: lanza });
    assert.match(pintarPestana(ctx), /Plano de la red/);
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null, setItem: () => {} } });
    assert.match(pintarPestana(ctx), /Plano de la red/);
  } finally {
    if (previo) Object.defineProperty(globalThis, 'localStorage', previo); else delete globalThis.localStorage;
  }
});

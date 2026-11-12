import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const raiz = fileURLToPath(new URL('..', import.meta.url));
// El separador decimal es el de la configuración regional de la web (es-PE), sea cual sea el de Node.
const n1 = (v) => v.toLocaleString('es-PE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

async function cargar() {
  const r = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { Tablero } from './src/features/clientesfijos/Tablero';
    export * from './src/features/clientesfijos/datosTablero';
    export const pintar = (r) => renderToStaticMarkup(createElement(Tablero, { r, wsId: 'Prueba', enlace: '/descarga.xlsx' }));`,
  resolveDir: raiz, loader: 'tsx' }, bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', r.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
  return mod.exports;
}

const mes = (m, p, extra = {}) => ({ mes: m, p_max: p, fecha_p_max: `${m}-03T18:45`, q_en_p_max: p / 3, q_max: p / 3,
  fecha_q_max: `${m}-04T10:00`, p_media: p / 2, q_media: p / 6, energia_p: p / 10, energia_q: p / 30, fp: .95,
  factor_carga: .5, registros: 2976, esperados: 2976, completo: true, copia_de: null, ...extra });
const resumen = (p, crec, tend) => ({ p_max: p, fecha_p_max: '2026-05-03T18:45',
  crecimiento: { p_max: { pct: crec, desde: '2026-01', hasta: '2026-05' }, energia_p: { pct: crec, desde: '2026-01', hasta: '2026-05' },
    q_max: { pct: crec, desde: '2026-01', hasta: '2026-05' }, p_max_coincidente: { pct: 5, desde: '2026-01', hasta: '2026-05' } },
  tendencia: { p_max: tend, energia_p: tend, q_max: tend },
  variacion: { p_max: { '2026-03': { pct: 10, respecto: '2026-01' }, '2026-05': { pct: -4, respecto: '2026-03' } },
    energia_p: { '2026-03': { pct: 2, respecto: '2026-01' } } },
  mes_mayor: { p_max: '2026-03', q_max: '2026-05', energia_p: '2026-03', energia_q: '2026-01' } });
const RESULTADO = {
  alimentadores: ['AL1'], desde: '2026-01', hasta: '2026-05', meses: ['2026-01', '2026-03', '2026-04', '2026-05'],
  libros: [{ libro: '0126.xlsx', mes: '2026-01' }], suministros: 'sum.xlsx',
  renumeraciones: [{ anterior: '111', actual: '900', alimentador: 'AL1' }],
  copias: [{ mes: '2026-04', de: '2026-03', clientes: ['900'], comparables: 1 }],
  conciliacion: { confirmado: 1, discrepa: 1, una_fuente: 0 }, red: false, propuestas: [],
  clientes: [{ codigo: '900', alimentador: 'AL1', sed: 'S1', anteriores: ['111'], libros: [],
    cl: 'CL0001', nombre: 'Doña Ñusta', suministrador: 'GENERADORA',
    veredicto: { estado: 'confirmado', fuentes: 2, acuerdan: ['suministros', 'libro de clientes 2026-05'], texto: 'confirmado' },
    meses: [mes('2026-01', 100), mes('2026-03', 110), mes('2026-04', 110, { copia_de: '2026-03' }), mes('2026-05', 105.6)],
    resumen: resumen(110, 5.6, 1.2) },
  { codigo: '0700000890', alimentador: 'AL1', sed: 'SE9', anteriores: [], libros: [], cl: '', nombre: 'Molino Sur',
    suministrador: '', veredicto: { estado: 'discrepa', fuentes: 1, acuerdan: ['suministros'],
      texto: 'AL1 (suministros); libro de clientes 2026-05 dice AL2' },
    meses: [mes('2026-01', 50)], resumen: resumen(50, null, null) }],
  totales: [{ alimentador: 'AL1', clientes: 1, resumen: resumen(110, 5.6, 1.2), cabecera: [
    { mes: '2026-01', p_max: 400, fecha: '2026-01-05T19:00', fijas_kw: 80, participacion: 20 }],
    meses: [{ mes: '2026-01', clientes: 1, p_max: 100, energia_p: 10, q_max: 33, energia_q: 3, p_max_coincidente: 100,
      fecha_coincidente: '2026-01-03T18:45', copia_de: null }] }],
  avisos: [{ tipo: 'copia', texto: '2026-04: el libro repite los valores de 2026-03' },
    { tipo: 'incompleto', texto: '900 2026-02: 10 de 2688 registros.' },
    { tipo: 'sin_suministro', texto: '3 cliente(s) de los libros no están en el libro de suministros' },
    { tipo: 'discrepancia', texto: '0700000890: AL1 (suministros); libro de clientes 2026-05 dice AL2' }],
  libro: 'clientes_fijos/AL1/x.xlsx', archivo: { ruta: 'G:/archivo/informes/clientes_fijos/AL1/x.xlsx', aviso: null },
};

test('105:RF-23 — series mensuales por cliente y total, sin el mes copiado', async () => {
  const { seriesMensuales } = await cargar();
  const s = seriesMensuales(RESULTADO, 'p_max');
  assert.deepEqual(s.meses, ['2026-01', '2026-03', '2026-05']);
  assert.deepEqual(s.series.map((x) => [x.clave, x.total, x.valores]), [
    ['900', false, [100, 110, 105.6]], ['0700000890', false, [50, null, null]], ['TOTAL AL1', true, [100, null, null]]]);
});

test('105:RF-24 — variaciones con su color: sube, baja o sin dato', async () => {
  const { tablaVariaciones, claseVariacion, fmtPct } = await cargar();
  const t = tablaVariaciones(RESULTADO, 'p_max');
  assert.deepEqual(t.filas[0].celdas, [null, 10, -4]);
  assert.deepEqual([10, -4, 0, null].map(claseVariacion), ['var-sube', 'var-baja', 'var-igual', '']);
  assert.equal(fmtPct(-4), `−${n1(4)} %`);
  assert.equal(fmtPct(12.34), `+${n1(12.34)} %`);
});

test('105:RF-25 — la curva reducida conserva la máxima', async () => {
  const { reducir } = await cargar();
  const puntos = Array.from({ length: 10000 }, (_v, i) => [`2026-01-01T${String(i).padStart(5, '0')}`, i === 7777 ? 999 : 1, null]);
  const r = reducir(puntos, 1000);
  assert.ok(r.length <= 1000);
  assert.ok(r.some((p) => p[1] === 999));
});

test('105:RF-26 — avisos agrupados por tipo, el mes copiado primero', async () => {
  const { avisosPorTipo } = await cargar();
  assert.deepEqual(avisosPorTipo(RESULTADO.avisos).map((g) => [g.titulo, g.textos.length]),
    [['Mes copiado', 1], ['Fuentes que discrepan', 1], ['Mes incompleto', 1], ['Cliente sin suministro', 1]]);
});

test('105:RF-22 a RF-26 — render real del tablero: tarjetas, gráficos, variaciones, cabecera, curva y avisos', async () => {
  const { pintar } = await cargar();
  const html = pintar(RESULTADO);
  for (const t of ['Descargar el libro Excel', 'Archivado en G:/archivo', 'Mes copiado', 'Mes incompleto',
    'Cliente sin suministro', 'P máx del periodo', `${n1(110)} kW`, 'Total AL1', '900', 'antes 111', 'mar 2026',
    'P máxima por mes (kW)', 'Q máxima por mes (kVAR)', 'Energía activa por mes (MWh)', 'Variación mes a mes',
    'Participación en la máxima de cabecera', `${n1(20)} %`, 'Curva de 15 minutos', 'Cargando la curva de 900', '111 → 900']) {
    assert.ok(html.includes(t), t);
  }
  assert.ok(html.includes(`class="var-sube">+${n1(10)} %`));
  assert.ok(html.includes(`class="var-baja">−${n1(4)} %`));
  assert.equal((html.match(/<svg class="curva-svg"/g) ?? []).length, 3, 'tres gráficos mensuales');
  assert.ok(!html.includes('>abr 2026</th>'), 'el mes copiado no va en la tabla de variaciones');
});

test('105:RF-39 — buscador por NIS, CL, nombre (sin tildes y con erratas), SED o alimentador, por relevancia', async () => {
  const { buscarClientes, normalizarCodigo } = await cargar();
  const c = RESULTADO.clientes;
  assert.equal(normalizarCodigo(' 0700000890.0 '), '700000890');
  assert.deepEqual(buscarClientes(c, '700000890').map((e) => [e.codigo, e.campo, e.puntaje]), [['0700000890', 'NIS', 100]]);
  assert.deepEqual(buscarClientes(c, '111')[0], { codigo: '900', puntaje: 100, campo: 'NIS anterior', valor: '111' });
  assert.equal(buscarClientes(c, 'cl0001')[0].campo, 'CL');
  const cercano = buscarClientes(c, 'dona nustaa');
  assert.equal(cercano[0].codigo, '900');
  assert.ok(cercano[0].puntaje >= 60 && cercano[0].puntaje < 80, String(cercano[0].puntaje));
  assert.equal(buscarClientes(c, 'Molino Sur')[0].puntaje, 95);
  assert.deepEqual(buscarClientes(c, 'al1').map((e) => e.codigo), ['0700000890', '900']);
  assert.deepEqual(buscarClientes(c, 'zzzz'), []);
});

test('105:RF-34 — el tablero dice el veredicto de cada cliente y sus discrepancias', async () => {
  const { pintar } = await cargar();
  const html = pintar(RESULTADO);
  for (const t of ['1 confirmado(s)', '1 con discrepancias', 'confirmado en 2 fuentes',
    'discrepa: AL1 (suministros); libro de clientes 2026-05 dice AL2', 'Fuentes que discrepan', 'Buscar cliente',
    'Doña Ñusta · CL0001 · GENERADORA']) assert.ok(html.includes(t), t);
});

async function pintarPestana(trabajos = {}) {
  const r = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { Ctx } from './src/shared/context';
    import { EvolucionFijas } from './src/features/clientesfijos/EvolucionFijas';
    export const pintar = (jobs, active) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
      ws: { id: 'Prueba', demanda: {}, options: {}, inputs: {}, loaded: false }, jobs, active,
      run: async () => undefined, startJob: async () => undefined } }, createElement(EvolucionFijas)));`,
  resolveDir: raiz, loader: 'tsx' }, bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', r.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
  const activo = Object.values(trabajos)[0];
  return mod.exports.pintar(trabajos, activo ? { engine: activo } : {});
}

test('105:RF-21 — la pestaña se pinta sin red cargada, con alimentadores, meses y el botón bloqueado mientras corre', async () => {
  const libre = await pintarPestana();
  for (const t of ['Alimentadores (0 de 0)', 'Desde', 'Hasta', 'Calcular la evolución']) assert.ok(libre.includes(t), t);
  const ocupada = await pintarPestana({ j1: { id: 'j1', kind: 'clientes_fijos_evolucion', workspace_id: 'Prueba', status: 'running' } });
  assert.match(ocupada, /<button[^>]*disabled=""[^>]*>Calculando…<\/button>/);
});

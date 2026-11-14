import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

/** Spec 072, T17: el tipo de análisis en la web (corto plazo, PIDE, largo plazo), sin servidor ni DIgSILENT. */
async function cargar() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { TipoDeAnalisis, SeguirDondeQuedo, estadoConDisco, pasosDelTipo, DESTINO } from './src/features/powerfactory/TipoDeAnalisis';
    import { GemeloPIDE, cuerpoPlanificar, porEntregable } from './src/features/powerfactory/GemeloPIDE';
    import { Ctx } from './src/shared/context';
    export { pasosDelTipo, cuerpoPlanificar, porEntregable, DESTINO, estadoConDisco };
    export const seguir = (props) => renderToStaticMarkup(createElement(SeguirDondeQuedo, props));
    export const tipo = (props) => renderToStaticMarkup(createElement(TipoDeAnalisis, {
      onTipo: () => undefined, onAnio: () => undefined, error: '', planificacion: true, ...props }));
    export const gemelo = (plazo) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
      ws:{id:'W'}, jobs:{}, active:{}, health:{edicion:{producto:true,beta:[]}},
      run: async (f) => f(), startJob: async (f) => f() } },
      createElement(GemeloPIDE, {project:'P',feeders:['F1'],plazo,anio:'2031',onAnio:()=>undefined,tipos:null})));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

const anios = (xs, base) => xs.map((a) => ({ relativo: a, calendario: base == null ? null : base + a }));
const obra = (c, t) => ({ codigo: c, titulo: t });
const TIPOS = {
  norma: { acto: 'RM 428-2017-MEM/DM', titulo: 'Norma de prueba', estado_juridico: 'proyecto', vigente: false, nota: '' },
  estudio: { anio_presentacion: 2031, anio_base: 2030 }, periodo_corto: 4, ciclo_anios: 4, anio_presentacion_perfil: null,
  tipos: [
    { clave: 'corto_plazo', titulo: 'Corto plazo', descripcion: 'Hoy', articulos: [], anios: anios([0, 1, 2, 3, 4], 2030),
      formatos: [], entregables: [{ clave: 'informe_estudio', titulo: 'Informe de estudio eléctrico', formatos: [] }],
      obras_admitidas: [obra('bancos', 'Bancos de condensadores')], obras_excluidas: [obra('set_nueva', 'SET nueva')], aplica_obras: true },
    { clave: 'pide', titulo: 'PIDE', descripcion: 'Periodo', articulos: [{ numero: 11, titulo: 'Alcances y etapas del PIDE' }],
      anios: anios([4, 5, 6, 7], 2030), formatos: ['F08'], entregables: [{ clave: 'formulacion_pide', titulo: 'PIDE: Formulación', formatos: ['F08'] }],
      obras_admitidas: [obra('bancos', 'Bancos de condensadores'), obra('set_nueva', 'SET nueva')], obras_excluidas: [], aplica_obras: true },
    { clave: 'largo_plazo', titulo: 'Planeamiento de largo plazo', descripcion: 'Horizonte', articulos: [{ numero: 6, titulo: 'Alcances' }],
      anios: anios([4, 8, 12, 16, 20], 2030), formatos: ['F01', 'F07'],
      entregables: [{ clave: 'diagnostico', titulo: 'Plan de largo plazo: Diagnóstico', formatos: ['F01'] },
        { clave: 'alternativas', titulo: 'Plan de largo plazo: Alternativas', formatos: ['F07'] }],
      obras_admitidas: [obra('bancos', 'Bancos de condensadores'), obra('set_nueva', 'SET nueva')], obras_excluidas: [], aplica_obras: false },
  ],
};
const NADA = { proyecto: false, alimentadores: false, calibrado: false, cargas: false, conProyecto: false, informes: false,
  pide: false, largo: false };

test('072:RF-29 los tres tipos se eligen de forma explícita, ninguno por defecto', async () => {
  const { tipo } = await cargar();
  const html = tipo({ tipo: null, anio: '', tipos: TIPOS, estado: NADA });
  assert.equal((html.match(/role="radio"/g) ?? []).length, 3);
  assert.ok(!html.includes('aria-checked="true"'));
  for (const t of ['Corto plazo', 'PIDE', 'Planeamiento de largo plazo', 'Elija uno']) assert.ok(html.includes(t), t);
  const elegido = tipo({ tipo: 'pide', anio: '2031', tipos: TIPOS, estado: NADA });
  assert.equal((elegido.match(/aria-checked="true"/g) ?? []).length, 1);
});

test('072:RF-30, 072:RF-31, 072:RF-32, 072:RF-37 la ficha dice horizonte, obras, entregables y la norma no vigente', async () => {
  const { tipo } = await cargar();
  const corto = tipo({ tipo: 'corto_plazo', anio: '', tipos: TIPOS, estado: NADA });
  for (const t of ['00 (2030)', '04 (2034)', 'Bancos de condensadores', 'No entran', 'SET nueva', 'Informe de estudio eléctrico',
    'se aplican', 'RM 428-2017-MEM/DM', 'no se presenta como norma vigente']) assert.ok(corto.includes(t), t);
  assert.ok(!corto.includes('Año de presentación'), 'el corto plazo no pide año de presentación');
  const largo = tipo({ tipo: 'largo_plazo', anio: '2031', tipos: TIPOS, estado: NADA });
  for (const t of ['20 (2050)', 'Plan de largo plazo: Diagnóstico (F01)', 'se plantean, no se aplican', 'Año de presentación (se presenta cada 4 años)']) {
    assert.ok(largo.includes(t), t);
  }
});

test('072:RF-36 sin año de presentación aquí ni en el perfil se avisa antes de planificar', async () => {
  const { tipo } = await cargar();
  assert.ok(tipo({ tipo: 'pide', anio: '', tipos: TIPOS, estado: NADA }).includes('«Planificar» se rechaza'));
  assert.ok(!tipo({ tipo: 'pide', anio: '2031', tipos: TIPOS, estado: NADA }).includes('«Planificar» se rechaza'));
  const conPerfil = { ...TIPOS, anio_presentacion_perfil: 2027 };
  assert.ok(!tipo({ tipo: 'pide', anio: '', tipos: conPerfil, estado: NADA }).includes('«Planificar» se rechaza'));
});

test('072:RF-33 cada tipo encadena sus pasos con su estado y su acceso a la sección existente', async () => {
  const { pasosDelTipo, DESTINO } = await cargar();
  const corto = pasosDelTipo('corto_plazo', NADA, true);
  assert.deepEqual(corto.map((p) => p.destino), [DESTINO.proyecto, DESTINO.calibracion, DESTINO.nuevas, DESTINO.obras, DESTINO.informes]);
  assert.equal(corto.find((p) => p.clave === 'nuevas').hecho, null, 'las cargas nuevas son opcionales');
  const pide = pasosDelTipo('pide', { ...NADA, proyecto: true, alimentadores: true, calibrado: true }, true);
  assert.deepEqual(pide.map((p) => p.hecho), [true, true, false, false, false]);
  assert.equal(pide[2].destino, DESTINO.obras, 'el PIDE parte del corto plazo');
  const largo = pasosDelTipo('largo_plazo', { ...NADA, largo: true }, false);
  assert.ok(largo.slice(-2).every((p) => p.hecho && p.destino === DESTINO.planificacion && /no está activa/.test(p.nota)));
  assert.ok(!largo.some((p) => p.destino === DESTINO.obras), 'el largo plazo no aplica obras en «Con proyecto»');
  const { tipo } = await cargar();
  const html = tipo({ tipo: 'corto_plazo', anio: '', tipos: TIPOS, estado: { ...NADA, proyecto: true } });
  assert.equal((html.match(/Ir al paso/g) ?? []).length, 5);
  assert.ok(html.includes('hecho') && html.includes('pendiente') && html.includes('opcional'));
});

test('072:RF-38 el PIDE sin «Con proyecto» avisa y no bloquea', async () => {
  const { tipo } = await cargar();
  assert.ok(tipo({ tipo: 'pide', anio: '2031', tipos: TIPOS, estado: NADA }).includes('el PIDE parte'));
  assert.ok(!tipo({ tipo: 'pide', anio: '2031', tipos: TIPOS, estado: { ...NADA, conProyecto: true } }).includes('el PIDE parte'));
});

test('072:RF-34, 072:RF-35 «Planificar» manda el tipo; en largo plazo nunca aplica obras', async () => {
  const { cuerpoPlanificar } = await cargar();
  const f = { capex: ' ', anio: '2031', formato01: '', implementar: true };
  const largo = cuerpoPlanificar('P', ['F1'], 'largo_plazo', f);
  assert.equal(largo.plazo, 'largo_plazo');
  assert.equal(largo.implementar, false);
  assert.equal(largo.anio_presentacion, 2031);
  assert.equal(largo.capex, null);
  const pide = cuerpoPlanificar('P', ['F1'], 'pide', f);
  assert.equal(pide.plazo, 'pide');
  assert.equal(pide.implementar, true);
  const corto = cuerpoPlanificar('P', ['F1'], 'corto_plazo', f);
  assert.ok(!('plazo' in corto), 'el corto plazo no se planifica en el paso 5: sin tipo, como siempre');
  assert.ok(!('plazo' in cuerpoPlanificar('P', ['F1'], null, f)));
});

test('072:RF-34, 072:RF-35 el paso 5 en largo plazo no deja aplicar obras y dice qué escribe', async () => {
  const { gemelo } = await cargar();
  const largo = gemelo('largo_plazo');
  assert.ok(largo.includes('Planificar el largo plazo'));
  assert.match(largo, /<input type="checkbox" disabled=""/);
  assert.ok(largo.includes('solo sus módulos (F01 a F07)'));
  const pide = gemelo('pide');
  assert.ok(pide.includes('Planificar como PIDE') && !/<input type="checkbox" disabled=""/.test(pide));
  assert.ok(gemelo(null).includes('>Planificar<'), 'sin tipo, el botón de siempre');
});

test('072:RF-32 los documentos del estudio se agrupan por entregable con las claves del servidor', async () => {
  const { porEntregable } = await cargar();
  const grupos = porEntregable(['1_diagnostico_ab12.docx', '2_alternativas_ab12.docx', '3_formulacion_pide_ab12.docx', 'raro.docx'], TIPOS);
  assert.deepEqual(grupos.map((g) => g.titulo), ['PIDE', 'Planeamiento de largo plazo', 'Documentos del estudio']);
  assert.deepEqual(grupos[1].ficheros, ['1_diagnostico_ab12.docx', '2_alternativas_ab12.docx']);
  assert.deepEqual(porEntregable(['1_diagnostico_x.docx'], null), [{ titulo: 'Documentos del estudio', ficheros: ['1_diagnostico_x.docx'] }]);
});


const AVANCE = { cargas: [{ sed: 'SECA001', alimentador: 'CA101', sola: true }], estudiados: ['CA101'], obras: false,
  informes: [] };

test('072:RF-33 lo guardado en disco marca los pasos aunque la sesión no tenga sus trabajos', async () => {
  const { estadoConDisco } = await cargar();
  const e = estadoConDisco({ ...NADA, proyecto: true, alimentadores: true, calibrado: true }, AVANCE, ['CA101', 'CHN102']);
  assert.equal(e.cargas, true);
  assert.equal(e.conProyecto, false);
  // Solo cuenta lo de los alimentadores marcados.
  assert.equal(estadoConDisco(NADA, AVANCE, ['CHN102']).cargas, false);
  assert.deepEqual(estadoConDisco(NADA, null, ['CA101']), NADA);
});

test('072:RF-33 con los marcados calibrados hay camino directo a 4.2 y 4.4', async () => {
  const { seguir, DESTINO } = await cargar();
  assert.equal(DESTINO.estudios, 'paso-estudios');
  const html = seguir({ avance: AVANCE, calibrados: ['CA101', 'CHN102'], order: ['CA101', 'CHN102'] });
  for (const t of ['Seguir donde quedó', 'SECA001 (CA101)', 'Falta el flujo de «Con proyecto» de CHN102',
    'Ir a 4.2 · Estudios', 'Ir a 4.4 · Preparar informe', 'los pasos 2 y 3 siguen abajo']) assert.ok(html.includes(t), t);
  const listo = seguir({ avance: { ...AVANCE, estudiados: ['CA101', 'CHN102'] }, calibrados: ['CA101', 'CHN102'],
    order: ['CA101', 'CHN102'] });
  assert.ok(listo.includes('Flujos de «Con proyecto» ya corridos: CA101, CHN102'));
  // Sin calibrar todos los marcados, no se ofrece el atajo.
  assert.equal(seguir({ avance: AVANCE, calibrados: ['CA101'], order: ['CA101', 'CHN102'] }), '');
});

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
    import { TipoDeAnalisis, SeguirDondeQuedo, estadoConDisco, pasosDelTipo, DESTINO, anioParaTipos, motivoAnio } from './src/features/powerfactory/TipoDeAnalisis';
    import { GemeloPIDE, cuerpoPlanificar, porEntregable, avisosDeEpisodio, claseDeEpisodio, fechaDeEpisodio, TEXTO_EPISODIO, motivoPlanificar } from './src/features/powerfactory/GemeloPIDE';
    import { Ctx } from './src/shared/context';
    export { avisosDeEpisodio, claseDeEpisodio, fechaDeEpisodio, TEXTO_EPISODIO };
    export { pasosDelTipo, cuerpoPlanificar, porEntregable, DESTINO, estadoConDisco, anioParaTipos, motivoAnio, motivoPlanificar };
    export const seguir = (props) => renderToStaticMarkup(createElement(SeguirDondeQuedo, props));
    export const tipo = (props) => renderToStaticMarkup(createElement(TipoDeAnalisis, {
      onTipo: () => undefined, onAnio: () => undefined, error: '', planificacion: true, ...props }));
    export const gemelo = (plazo) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
      ws:{id:'W'}, jobs:{}, active:{}, health:{edicion:{producto:true,beta:[]}},
      run: async (f) => f(), startJob: async (f) => f() } },
      createElement(GemeloPIDE, {project:'P',feeders:['F1'],plazo,anio:'2031',onAnio:()=>undefined,tipos:null})));
    export const gemeloCon = (props) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
      ws:{id:'W'}, jobs:{}, active:{}, health:{edicion:{producto:true,beta:[]}},
      run: async (f) => f(), startJob: async (f) => f() } },
      createElement(GemeloPIDE, {project:'P',feeders:['F1'],plazo:'pide',anio:'2031',onAnio:()=>undefined,tipos:null,...props})));`,
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
  anio_presentacion_rango: { min: 2000, max: 2100 },
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
    'se aplican', 'RM 428-2017-MEM/DM', 'no es norma vigente']) assert.ok(corto.includes(t), t);
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
  // 072:RF-18, 025:RF-67: el tipo de cambio va SOLO si el operador lo escribe (sin él, la llamada no cambia).
  assert.ok(!('tipo_cambio' in pide), 'sin tipo de cambio escrito, no se envía');
  assert.equal(cuerpoPlanificar('P', ['F1'], 'pide', { ...f, tipoCambio: '3,495' }).tipo_cambio, 3.495);
  assert.equal(cuerpoPlanificar('P', ['F1'], 'pide', { ...f, tipoCambio: ' 3.5 ' }).tipo_cambio, 3.5);
  assert.ok(!('tipo_cambio' in cuerpoPlanificar('P', ['F1'], 'pide', { ...f, tipoCambio: '  ' })));
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


const AVANCE = { cargas: [{ sed: 'SECA001', alimentador: 'CA191', sola: true }], estudiados: ['CA191'], obras: false,
  informes: [] };

test('072:RF-33 lo guardado en disco marca los pasos aunque la sesión no tenga sus trabajos', async () => {
  const { estadoConDisco } = await cargar();
  const e = estadoConDisco({ ...NADA, proyecto: true, alimentadores: true, calibrado: true }, AVANCE, ['CA191', 'CHN192']);
  assert.equal(e.cargas, true);
  assert.equal(e.conProyecto, false);
  // Solo cuenta lo de los alimentadores marcados.
  assert.equal(estadoConDisco(NADA, AVANCE, ['CHN192']).cargas, false);
  assert.deepEqual(estadoConDisco(NADA, null, ['CA191']), NADA);
});

test('072:RF-33 con los marcados calibrados hay camino directo a 4.2 y 4.4', async () => {
  const { seguir, DESTINO } = await cargar();
  assert.equal(DESTINO.estudios, 'paso-estudios');
  const html = seguir({ avance: AVANCE, calibrados: ['CA191', 'CHN192'], order: ['CA191', 'CHN192'] });
  for (const t of ['Seguir donde quedó', 'SECA001 (CA191)', 'Falta el flujo de «Con proyecto» de CHN192',
    'Ir a 4.2 · Estudios', 'Ir a 4.4 · Preparar informe', 'los pasos 2 y 3 siguen abajo']) assert.ok(html.includes(t), t);
  const listo = seguir({ avance: { ...AVANCE, estudiados: ['CA191', 'CHN192'] }, calibrados: ['CA191', 'CHN192'],
    order: ['CA191', 'CHN192'] });
  assert.ok(listo.includes('Flujos de «Con proyecto» ya corridos: CA191, CHN192'));
  // Sin calibrar todos los marcados, no se ofrece el atajo.
  assert.equal(seguir({ avance: AVANCE, calibrados: ['CA191'], order: ['CA191', 'CHN192'] }), '');
});

test('024:RF-5 la tabla de episodios del gemelo se lee en español y sin rutas de DIgSILENT', async () => {
  const { avisosDeEpisodio, claseDeEpisodio, fechaDeEpisodio, TEXTO_EPISODIO } = await cargar();
  assert.deepEqual(claseDeEpisodio('counterfactual'), ['Escenario simulado', 'ok']);
  assert.deepEqual(claseDeEpisodio('converged_with_violations'), ['Converge con violaciones', 'err']);
  assert.deepEqual(claseDeEpisodio('quarantine'), ['En revisión', 'warn']);
  assert.equal(TEXTO_EPISODIO.sin_proyecto, 'Sin proyecto');
  assert.equal(TEXTO_EPISODIO.ajuste, 'Calibración');
  assert.doesNotMatch(fechaDeEpisodio('2026-11-13T23:23:22+00:00'), /T23|\+00:00/);
  const ruta = (n) => `tensión 0.9468 p.u. en ElmTerm:Network Model.IntPrjfolder\\Network Data.IntPrjfolder\\CA191_CHN192.ElmNet\\${n}.ElmTerm fuera de 0.95–1.05 (NTCSE)`;
  assert.equal(avisosDeEpisodio([ruta(11799)]), 'barra 11799 a 0,9468 p.u., fuera de 0,95–1,05 (NTCSE)');
  assert.match(avisosDeEpisodio([ruta(1), ruta(2), ruta(3), ruta(4)]), /barra 1 .* · barra 2 .* · y 2 más$/);
  assert.equal(avisosDeEpisodio(['sin medida para comprobar la calibración']), 'sin medida para comprobar la calibración');
});


test('072:RF-18 — la pantalla del PIDE pide el tipo de cambio, con su rótulo y sin suponer moneda', async () => {
  const { gemelo } = await cargar();
  const html = gemelo('pide');
  assert.match(html, /Tipo de cambio/);
  assert.match(html, /inputMode="decimal"|inputmode="decimal"/);
});


// La revisión en pantalla del 2026-11-14 vio dos campos «Año de presentación» con rangos distintos (1900–2200 arriba,
// 2000–2100 en el paso 5) para un mismo valor. Ahora es un solo campo, con el rango que da la API con los tipos.
const RANGO = { min: 2010, max: 2090 };
const conRango = { ...TIPOS, anio_presentacion_rango: RANGO, ciclo_anios: 5 };
const atributos = (html, marca) => {
  const m = html.match(new RegExp(`<input[^>]*${marca}[^>]*>`));
  assert.ok(m, `no está el campo ${marca}`);
  return m[0];
};
const MOTIVO = 'El año de presentación va de 2010 a 2090.';
const conId = (html, id) => html.includes(`id="${id}"`) && new RegExp(`id="${id}"[^>]*>${MOTIVO.replace('.', '\\.')}<`).test(html);

test('072:RF-1, 072:RF-36 el año de presentación usa el rango y el ciclo de la API, arriba y en el paso 5', async () => {
  const { tipo, gemeloCon } = await cargar();
  for (const html of [tipo({ tipo: 'pide', anio: '2031', tipos: conRango, estado: NADA }), gemeloCon({ tipos: conRango })]) {
    const campo = atributos(html, 'name="anio_presentacion"');
    assert.match(campo, /min="2010"/);
    assert.match(campo, /max="2090"/);
    assert.ok(!/1900|2200/.test(campo), 'sin el rango del año de los casos');
    assert.match(html, /Año de presentación \(se presenta cada 5 años\)/);
    assert.ok(!html.includes('cada 4 años'), 'el ciclo sale de la metodología, no del código');
  }
  // Sin los tipos todavía, ni rango inventado ni ciclo supuesto.
  const sin = gemeloCon({ tipos: null });
  const campo = atributos(sin, 'name="anio_presentacion"');
  assert.ok(!/ min=| max=/.test(campo), campo);
  assert.ok(!sin.includes('se presenta cada'));
});

test('072:RF-36 un año fuera del rango se dice junto al campo, una vez, y el campo lo señala', async () => {
  const { tipo, motivoAnio } = await cargar();
  // Antes de llamarla: sin la función, la prueba cae por su aserción, no por un TypeError.
  assert.equal(typeof motivoAnio, 'function', 'TipoDeAnalisis no exporta motivoAnio');
  for (const mal of ['2095', '2009', '20x1', '2031.5']) assert.equal(motivoAnio(mal, conRango), MOTIVO, mal);
  for (const bien of ['', '  ', '203', '2010', '2090', ' 2031 ']) assert.equal(motivoAnio(bien, conRango), null, bien);
  assert.equal(motivoAnio('2095', null), null, 'sin rango de la API no se juzga: la API dirá 422');
  const html = tipo({ tipo: 'pide', anio: '2095', tipos: conRango, estado: NADA });
  const campo = atributos(html, 'name="anio_presentacion"');
  assert.match(campo, /aria-invalid="true"/);
  const id = campo.match(/aria-describedby="([^"]+)"/)?.[1];
  assert.ok(id, 'el campo apunta a su motivo');
  assert.ok(conId(html, id), 'el motivo es visible y lleva ese id');
  assert.equal(html.split('va de 2010 a 2090').length - 1, 1, 'el aviso no se repite');
  const bien = atributos(tipo({ tipo: 'pide', anio: '2031', tipos: conRango, estado: NADA }), 'name="anio_presentacion"');
  assert.ok(!bien.includes('aria-describedby') && !bien.includes('aria-invalid="true"'), bien);
});

test('072:RF-36 los tipos solo se piden con un año dentro del rango conocido', async () => {
  const { anioParaTipos } = await cargar();
  assert.equal(typeof anioParaTipos, 'function', 'TipoDeAnalisis no exporta anioParaTipos');
  assert.equal(anioParaTipos('', RANGO), null);
  assert.equal(anioParaTipos('203', RANGO), null, 'mientras se escribe cuenta como sin año');
  assert.equal(anioParaTipos('2031', RANGO), 2031);
  assert.equal(anioParaTipos(' 2090 ', RANGO), 2090);
  assert.equal(anioParaTipos('2095', RANGO), undefined);
  assert.equal(anioParaTipos('2031.5', RANGO), undefined);
  assert.equal(anioParaTipos('2095', null), 2095, 'sin rango todavía, decide la API');
});

test('072:RF-18, 072:RF-36 «Planificar» desactivado dice por qué en un texto visible y enlazado', async () => {
  const { gemeloCon, motivoPlanificar } = await cargar();
  assert.equal(typeof motivoPlanificar, 'function', 'GemeloPIDE no exporta motivoPlanificar');
  assert.equal(motivoPlanificar({ tipoCambio: '0', anio: '2031', tipos: conRango })?.causa, 'tipo_cambio');
  assert.equal(motivoPlanificar({ tipoCambio: 'abc', anio: '2095', tipos: conRango })?.causa, 'tipo_cambio');
  assert.equal(motivoPlanificar({ tipoCambio: '', anio: '2095', tipos: conRango })?.causa, 'anio');
  assert.equal(motivoPlanificar({ tipoCambio: '3,495', anio: '2031', tipos: conRango }), null);
  assert.equal(motivoPlanificar({ tipoCambio: '', anio: '', tipos: null }), null);
  const html = gemeloCon({ tipos: conRango, anio: '2095' });
  const boton = html.match(/<button[^>]*>Planificar como PIDE<\/button>/)?.[0];
  assert.ok(boton, 'está el botón');
  assert.match(boton, /disabled=""/);
  const id = boton.match(/aria-describedby="([^"]+)"/)?.[1];
  assert.ok(id, 'el botón apunta a su motivo');
  assert.ok(conId(html, id), 'el motivo es visible, junto al campo, y lleva ese id');
  assert.ok(!/title="El /.test(boton), 'el motivo no queda solo en el title');
  assert.equal(html.split('va de 2010 a 2090').length - 1, 1, 'un solo aviso');
  const libre = gemeloCon({ tipos: conRango, anio: '2031' }).match(/<button[^>]*>Planificar como PIDE<\/button>/)?.[0] ?? '';
  assert.ok(libre && !libre.includes('disabled') && !libre.includes('aria-describedby'), libre);
});

test('072:RF-44 en la pestaña de su módulo el recuadro se titula como la pestaña, también mientras cargan los tipos o si fallan', async () => {
  // El usuario se quejó dos veces del recuadro «Tipo de análisis» (18-11): en su pestaña el tipo va fijo y el título es el
  // de la pestaña desde el primer instante, sin esperar a /api/planeamiento/tipos ni depender de que responda.
  const { tipo } = await cargar();
  const etiquetas = { corto_plazo: 'Corto plazo', pide: 'PIDE', largo_plazo: 'Largo plazo' };
  const estado = { proyecto: false, alimentadores: false, calibrado: false, cargas: false, conProyecto: false, informes: false, pide: false, largo: false };
  for (const [clave, etiqueta] of Object.entries(etiquetas)) {
    for (const [caso, extra] of [['cargando', { tipos: null, error: '' }], ['con error', { tipos: null, error: 'No se pudo leer los tipos.' }]]) {
      const html = tipo({ tipo: clave, anio: '', estado, fijo: true, ...extra });
      assert.ok(html.includes(`<h3>${etiqueta}</h3>`), `${clave}, ${caso}: el título no es «${etiqueta}»: ${html.slice(0, 160)}`);
      assert.ok(!html.includes('Tipo de análisis'), `${clave}, ${caso}: sale «Tipo de análisis»`);
    }
  }
});

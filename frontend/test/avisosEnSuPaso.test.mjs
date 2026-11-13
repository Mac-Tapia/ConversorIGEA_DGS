import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

// Usuario, 2026-11-12: arriba de la web se apilaban «Trabajo interrumpido: Cargar / listar alimentadores · 11:20:31» y
// «· 10:33:13» con «Aún no hay ninguna copia de sus datos…»: «estos mensajes deberían aparecer en el numeral que
// corresponde de la web». Y las dos interrupciones ya no valían: después el mismo «Cargar / listar» terminó bien.
let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { AvisosTrabajo } from './src/shared/AvisosTrabajo';
        import { AvisosDatos } from './src/app/AvisosDatos';
        import { FeedersPanel } from './src/features/conversion/FeedersPanel';
        export * from './src/shared/pasoDeTrabajo';
        export { darPorVisto } from './src/shared/AvisosTrabajo';
        function valor(jobs, extra = {}) {
          return {
            ws: { id: 'W', loaded: false, missing_inputs: [], no_disponibles: [], avisos_datos: [], options: {}, ...extra.ws },
            health: { copia_datos: { vencida: false }, capabilities: {}, ...extra.health },
            feeders: [], outputs: [], selected: [], setSelected: () => {}, active: extra.active ?? {}, pf: null,
            jobs, run: async (fn) => fn(), setWs: () => {}, startJob: async () => undefined,
            refresh: async () => undefined, refreshHealth: () => {},
          };
        }
        const pintar = (el, jobs, extra) => renderToStaticMarkup(createElement(Ctx.Provider, { value: valor(jobs, extra) }, el));
        export const paso = (p, jobs, extra) => pintar(createElement(AvisosTrabajo, { paso: p }), jobs, extra);
        export const arriba = (jobs, pestanas, extra) => pintar(createElement(AvisosDatos, { pestanas }), jobs, extra);
        export const alimentadores = (jobs) => pintar(createElement(FeedersPanel), jobs);`,
      resolveDir: fileURLToPath(new URL('../', import.meta.url)), loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  globalThis.localStorage ??= { getItem: () => null, setItem: () => {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

let n = 0;
const trabajo = (kind, status, extra = {}) => {
  n += 1;
  return { id: `j${n}`, kind, status, workspace_id: 'W', lane: 'engine', title: extra.title ?? `T ${kind}`,
    created_at: extra.created_at ?? n, finished_at: extra.finished_at ?? n, error: extra.error ?? 'motivo', ...extra };
};
const porId = (...js) => Object.fromEntries(js.map((j) => [j.id, j]));

// ---------------------------------------------------------------- la tabla kind → paso, completa
const SRC = fileURLToPath(new URL('../../src/convertersmartgrid/', import.meta.url));
function pythonDe(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? pythonDe(join(dir, e.name))
    : e.name.endsWith('.py') ? [join(dir, e.name)] : []));
}

/** Los `kind` que el servidor encola: el segundo argumento literal de cada `submit(`, también el de un `x if c else y`. */
function kindsDelServidor() {
  const kinds = new Set();
  const sinLeer = [];
  for (const f of pythonDe(SRC)) {
    const texto = readFileSync(f, 'utf8');
    const rel = f.slice(SRC.length).split(sep).join('/');
    for (const m of texto.matchAll(/(?<!def |pool\.)\bsubmit\(\s*([\s\S]{0,200})/g)) {
      const linea = texto.slice(0, m.index).split('\n').length;
      const args = m[1];
      // ws, 'kind' | ws_or_404(wid), 'kind' | ws.id, 'a' if simular else 'b'
      const literal = args.match(/^(?:[\w.]+(?:\([^)]*\))?\s*,\s*)?'([a-z_0-9]+)'(?:\s+if\s+\w+\s+else\s+'([a-z_0-9]+)')?/);
      if (literal) { kinds.add(literal[1]); if (literal[2]) kinds.add(literal[2]); continue; }
      sinLeer.push(`${rel}:${linea}: submit(${args.slice(0, 60).replace(/\s+/g, ' ')}`);
    }
    for (const m of texto.matchAll(/^KIND = '([a-z_0-9]+)'/gm)) kinds.add(m[1]);
  }
  return { kinds, sinLeer };
}

/** Los `submit` con el `kind` en una variable: cada uno con lo que puede valer y por qué. */
const DINAMICOS = {
  // registro_modulos.lanzar_estudio: el puerto del módulo, que solo admite 'estudio' o 'sesion'.
  'registro_modulos.py': { llamadas: 1, kinds: ['estudio', 'sesion'] },
  // encolar_ciclo_aprendizaje: kind = f'aprendizaje:{huella}'; el reintento del vigilante repite el kind de su trabajo,
  // y el submit(ws, kind, …) de la API es el que usan todos los literales leídos.
  'web/app.py': { llamadas: 3, kinds: ['aprendizaje'] },
  // vnr/web/app.py: el submit(kind, title, fn) del adaptador, con 'download' y f'vnr_export_{target}' (cymdist o dgs).
  'adaptadores/entrada/vnr/web/app.py': { llamadas: 2, kinds: ['download', 'vnr_export_cymdist', 'vnr_export_dgs'] },
};

/** Kinds que el servidor ya no encola pero que siguen en el historial de los espacios: sus avisos se muestran igual.
 *  libros_nuevos: desde 104:RF-30 la revisión va en su carril de fondo, sin trabajo; los de antes siguen guardados. */
const HISTORICOS = ['libros_nuevos'];

test('086:RF-70 086:RF-71 todo kind del servidor tiene su fila en la tabla, con paso o en la zona general', async (t) => {
  // 065:RF-9 (suite completa del 2026-11-12): test_frontend_rutas copia solo el frontend a una ruta con espacios para probarlo;
  // allí no está el código del servidor. Esta comprobación es del proyecto entero y se hace donde está.
  if (!existsSync(SRC)) { t.skip('el código del servidor no está junto al frontend (copia aislada)'); return; }
  const { PASO_DE_TRABAJO, PASOS } = await cargar();
  const { kinds, sinLeer } = kindsDelServidor();
  for (const d of Object.values(DINAMICOS)) for (const k of d.kinds) kinds.add(k);
  for (const k of HISTORICOS) kinds.add(k);
  // Una forma nueva de llamar a submit no se cuela: o se lee su literal, o está declarada arriba.
  const porFichero = {};
  for (const s of sinLeer) porFichero[s.split(':')[0]] = (porFichero[s.split(':')[0]] ?? 0) + 1;
  const declarados = Object.fromEntries(Object.entries(DINAMICOS).map(([f, d]) => [f, d.llamadas]));
  assert.deepEqual(porFichero, declarados, `submit sin kind literal, o uno declarado que ya no está:\n${sinLeer.join('\n')}`);
  assert.ok(kinds.size >= 50, `se leyeron pocos kind (${kinds.size}): el patrón de búsqueda dejó de servir`);
  const faltan = [...kinds].filter((k) => !(k in PASO_DE_TRABAJO)).sort();
  assert.deepEqual(faltan, [], `kind sin fila en PASO_DE_TRABAJO: ${faltan.join(', ')}`);
  for (const [k, p] of Object.entries(PASO_DE_TRABAJO)) assert.ok(p === null || p in PASOS, `${k} → ${p}`);
  // Los de la zona general, dichos: lo que encola el servidor solo o va a otro espacio.
  const generales = Object.entries(PASO_DE_TRABAJO).filter(([, p]) => p === null).map(([k]) => k).sort();
  assert.deepEqual(generales, ['aprendizaje', 'copia_datos', 'download', 'libros_nuevos', 'vnr_export_cymdist',
    'vnr_export_dgs']);
  // Y ninguna fila sobra: cada una es un kind que el servidor encola hoy.
  const sobran = Object.keys(PASO_DE_TRABAJO).filter((k) => !kinds.has(k));
  assert.deepEqual(sobran, [], `filas sin kind en el servidor: ${sobran.join(', ')}`);
});

test('086:RF-70 los pasos que pidió el usuario', async () => {
  const { pasoDeTrabajo } = await cargar();
  assert.equal(pasoDeTrabajo('load'), 'alimentadores');
  assert.equal(pasoDeTrabajo('convert'), 'alimentadores');
  assert.equal(pasoDeTrabajo('convert_group'), 'alimentadores');
  assert.equal(pasoDeTrabajo('recalibrar'), 'pf-calibracion');
  assert.equal(pasoDeTrabajo('estudios'), 'pf-estudios');
  assert.equal(pasoDeTrabajo('informe_estudio'), 'pf-informes');
  assert.equal(pasoDeTrabajo('informe_factibilidad'), 'pf-informes');
  assert.equal(pasoDeTrabajo('aprendizaje:abc123'), null);
  assert.equal(pasoDeTrabajo('uno_que_aun_no_existe'), null, 'uno sin fila cae en la zona general');
});

// ---------------------------------------------------------------- cada paso con su aviso
test('086:RF-70 086:RF-72 «Cargar / listar» interrumpido sale en «2 Alimentadores», con sus tres botones', async () => {
  const { alimentadores, paso } = await cargar();
  const j = trabajo('load', 'interrumpido', { title: 'Cargar / listar alimentadores', error: 'El servidor se detuvo con este trabajo a medias' });
  const html = alimentadores(porId(j));
  const cabecera = html.indexOf('</span> Alimentadores</h2>');
  const aviso = html.indexOf('Trabajo interrumpido: Cargar / listar alimentadores');
  assert.ok(cabecera >= 0 && aviso > cabecera, html.slice(0, 600));
  for (const boton of ['Reintentar', 'Ver su registro', 'Dar por visto']) assert.ok(html.includes(`>${boton}</button>`), boton);
  assert.equal(paso('pf-calibracion', porId(j)), '', 'no sale en otro paso');
});

test('086:RF-70 cada paso enseña los avisos de sus trabajos y de ningún otro', async () => {
  const { paso, PASO_DE_TRABAJO, PASOS } = await cargar();
  for (const p of Object.keys(PASOS)) {
    const kind = Object.entries(PASO_DE_TRABAJO).find(([, v]) => v === p)[0];
    const otro = Object.entries(PASO_DE_TRABAJO).find(([, v]) => v && v !== p)[0];
    const jobs = porId(trabajo(kind, 'failed', { title: `propio ${kind}` }), trabajo(otro, 'cancelled', { title: `ajeno ${otro}` }));
    const html = paso(p, jobs);
    assert.ok(html.includes(`data-aviso-trabajo="${kind}"`), `${p}: ${html}`);
    assert.ok(!html.includes('ajeno'), `${p} enseña uno de ${otro}`);
  }
  const html = paso('pf-informes', porId(trabajo('informe_estudio', 'failed'), trabajo('informe_factibilidad', 'cancelled')));
  assert.match(html, /Trabajo fallido: T informe_estudio/);
  assert.match(html, /Trabajo cancelado: T informe_factibilidad/);
});

test('086:RF-72 «Reintentar» solo en los que se repiten con sus mismos datos, y apagado con su carril ocupado', async () => {
  const { paso, REPETIBLES } = await cargar();
  assert.ok(!paso('pf-calibracion', porId(trabajo('recalibrar', 'interrumpido'))).includes('Reintentar'),
    'recalibrar lleva proyecto, periodo y alimentadores: se repite desde su botón');
  assert.ok(paso('pf-proyecto', porId(trabajo('pf_projects', 'failed'))).includes('>Reintentar<'));
  assert.ok(REPETIBLES.includes('load'));
  const ocupado = paso('alimentadores', porId(trabajo('load', 'interrumpido')), { active: { engine: { id: 'x' } } });
  assert.match(ocupado, /<button[^>]*disabled=""[^>]*>Reintentar/);
});

// ---------------------------------------------------------------- resolución automática
test('086:RF-73 un interrumpido que después terminó bien, del mismo kind y ámbito, no se muestra', async () => {
  const { avisosDeTrabajos, alimentadores } = await cargar();
  const t = 'Cargar / listar alimentadores';
  const a = trabajo('load', 'interrumpido', { title: t, created_at: 10 });
  const b = trabajo('load', 'interrumpido', { title: t, created_at: 20 });
  const ok = trabajo('load', 'done', { title: t, created_at: 30 });
  assert.equal(avisosDeTrabajos(porId(a, b), 'W', []).length, 1, 'dos del mismo ámbito, un aviso');
  assert.equal(avisosDeTrabajos(porId(a, b), 'W', [])[0].anteriores.length, 1);
  assert.deepEqual(avisosDeTrabajos(porId(a, b, ok), 'W', []), []);
  assert.ok(!alimentadores(porId(a, b, ok)).includes('Trabajo interrumpido'));
  // Uno bueno anterior no resuelve al que falló después.
  const despues = trabajo('load', 'failed', { title: t, created_at: 40 });
  assert.equal(avisosDeTrabajos(porId(a, ok, despues), 'W', [])[0].job.id, despues.id);
});

test('086:RF-73 el ámbito es el espacio y el proyecto o los alimentadores de su título', async () => {
  const { avisosDeTrabajos } = await cargar();
  const fallo = trabajo('recalibrar', 'interrumpido', { title: 'Recalibrar · PROY_A · AL209', created_at: 1 });
  const otroProyecto = trabajo('recalibrar', 'done', { title: 'Recalibrar · PROY_B · AL209', created_at: 2 });
  const otroEspacio = trabajo('recalibrar', 'done', { title: 'Recalibrar · PROY_A · AL209', created_at: 3, workspace_id: 'X' });
  const otroKind = trabajo('pf_escaneo', 'done', { title: 'Recalibrar · PROY_A · AL209', created_at: 4 });
  assert.equal(avisosDeTrabajos(porId(fallo, otroProyecto, otroEspacio, otroKind), 'W', []).length, 1);
  const reintento = trabajo('recalibrar', 'done', { title: 'Recalibrar · PROY_A · AL209 (reintento)', created_at: 5 });
  assert.deepEqual(avisosDeTrabajos(porId(fallo, reintento), 'W', []), [], 'el reintento del vigilante es el mismo ámbito');
  assert.deepEqual(avisosDeTrabajos(porId(fallo), 'W', [fallo.id]), [], 'dado por visto');
  assert.deepEqual(avisosDeTrabajos(porId(trabajo('load', 'done'), trabajo('load', 'running')), 'W', []), []);
});

// ---------------------------------------------------------------- arriba, solo lo general
test('086:RF-74 086:RF-71 arriba: la copia en una línea, y de trabajos solo los que no tienen paso', async () => {
  const { arriba } = await cargar();
  const jobs = porId(trabajo('load', 'interrumpido', { title: 'Cargar / listar alimentadores' }),
    trabajo('libros_nuevos', 'failed', { title: 'Reconocer libros nuevos de demanda' }));
  const html = arriba(jobs, ['results', 'cargas'], { health: { copia_datos: { vencida: true, edad_dias: null } } });
  assert.match(html, /<details class="alert alert-warn aviso-linea"[^>]*><summary>Aún no hay ninguna copia de sus datos\./);
  assert.ok(html.includes('<span class="mas">más</span>'));
  assert.ok(!html.includes('Cargar / listar alimentadores'), 'el de «Cargar / listar» va a su paso, no arriba');
  assert.ok(html.includes('Trabajo fallido: Reconocer libros nuevos de demanda'));
});

test('086:RF-85 el aviso de la copia trae la carpeta y «Hacer una copia ahora»; copiando, el botón espera', async () => {
  const { arriba, pasoDeTrabajo } = await cargar();
  const sinCopia = { health: { copia_datos: { vencida: true, edad_dias: null }, server_paths: true } };
  const html = arriba({}, ['results'], sinCopia);
  assert.match(html, /aria-label="Carpeta de la copia"/);
  assert.match(html, /<button[^>]*>Hacer una copia ahora<\/button>/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Hacer una copia ahora/, 'sin carpeta escrita, el botón espera a que se escriba');
  const copiando = arriba(porId(trabajo('copia_datos', 'running', { title: 'Copia de los datos' })), ['results'], sinCopia);
  assert.match(copiando, /<button[^>]*disabled=""[^>]*>Copiando…<\/button>/);
  const remoto = arriba({}, ['results'], { health: { copia_datos: { vencida: true, edad_dias: null }, server_paths: false } });
  assert.ok(remoto.includes('use la orden del manual'));
  assert.equal(pasoDeTrabajo('copia_datos'), null, 'su fallo sale arriba, junto al aviso de la copia');
  assert.ok(!arriba({}, ['results']).includes('Hacer una copia ahora'), 'con la copia al día no hay aviso ni botón');
});

test('086:RF-75 un aviso cuya pestaña no se ofrece va arriba; si se ofrece, su pestaña lo cuenta', async () => {
  const { arriba, avisosDeTrabajos, avisosPorPestana, esGeneral } = await cargar();
  const cat = trabajo('catalog', 'failed', { title: 'Generar catálogo y auditar' });
  const rec = trabajo('recalibrar', 'interrumpido', { title: 'Recalibrar · P' });
  const avisos = avisosDeTrabajos(porId(cat, rec), 'W', []);
  assert.ok(arriba(porId(cat, rec), ['results', 'cargas']).includes('Generar catálogo y auditar'),
    'sin entradas cargadas no hay pestaña de catálogo: no se pierde, sale arriba');
  assert.ok(!arriba(porId(cat), ['results', 'cargas', 'catalog']).includes('Generar catálogo'));
  assert.deepEqual(avisosPorPestana(avisos, ['cargas', 'catalog']), { cargas: 1, catalog: 1 });
  assert.equal(avisos.filter((a) => esGeneral(a, ['cargas'])).length, 1);
});

test('086:RF-72 «Dar por visto» en un paso lo quita de todos, con sus anteriores del mismo ámbito', async () => {
  const { paso, darPorVisto } = await cargar();
  const a = trabajo('pf_verificar', 'failed', { title: 'Verificar la convergencia · Q', created_at: 1 });
  const b = trabajo('pf_verificar', 'failed', { title: 'Verificar la convergencia · Q', created_at: 2 });
  assert.match(paso('pf-nuevas', porId(a, b)), /también 1 vez antes/);
  darPorVisto([b.id, a.id]);
  assert.equal(paso('pf-nuevas', porId(a, b)), '');
});

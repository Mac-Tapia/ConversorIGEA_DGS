import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Spec 072 (módulos): el corto plazo, el PIDE y el largo plazo en su pestaña, como el VNR, el PIT y el VAD. Sin
// navegador: cada pestaña es la MISMA «Cargas en DIgSILENT» con su tipo fijo y solo sus secciones, con los ids de su
// pestaña; «Cargas en DIgSILENT» sigue entera; el PIDE ya no es beta; y la matriz de cobertura por pestaña.
const RAIZ = fileURLToPath(new URL('../', import.meta.url));
const SRC = join(RAIZ, 'src');

/** 072 (módulos): sección → su título en la pantalla, la llamada de api/client.ts, su ruta y una prueba del servidor. */
const SECCIONES = {
  proyecto: { titulo: '1 · Proyecto de DIgSILENT', llamada: 'pfProjects', ruta: '/powerfactory/projects',
    prueba: 'tests/test_cargas_pf_front.py' },
  calibracion: { titulo: '2 · Alimentadores y calibración', llamada: 'pfVerificarBase', ruta: '/powerfactory/caso-base',
    prueba: 'tests/test_caso_base_web.py' },
  nuevas: { titulo: '3 · Integración de nuevas', llamada: 'cargasPlan', ruta: '/lote/plan',
    prueba: 'tests/test_cargas_pf_ubicacion.py' },
  obras: { titulo: '4 · Obras y estudios', llamada: 'obrasConProyecto', ruta: '/pf/obras/con-proyecto',
    prueba: 'tests/test_set_nueva_web.py' },
  planificacion: { titulo: '5 · Planificación PIDE y gemelo digital', llamada: 'pide', ruta: '/pide',
    prueba: 'tests/test_gemelo_pide_front.py' },
};
/** 072 (módulos): lo que enseña cada pestaña, de los pasos de su tipo (pasosDelTipo). */
const MATRIZ = {
  corto_plazo: { pestana: 'corto', etiqueta: 'Corto plazo', ve: ['proyecto', 'calibracion', 'nuevas', 'obras'], no: ['planificacion'] },
  pide: { pestana: 'pide', etiqueta: 'PIDE', ve: ['proyecto', 'calibracion', 'obras', 'planificacion'], no: ['nuevas'] },
  largo_plazo: { pestana: 'largo', etiqueta: 'Largo plazo', ve: ['proyecto', 'calibracion', 'planificacion'], no: ['nuevas', 'obras'] },
};

let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { CargasTab } from './src/features/powerfactory/CargasTab';
        export { pasosDelTipo } from './src/features/powerfactory/TipoDeAnalisis';
        export { api } from './src/api/client';
        export const pintar = (modulo) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
          ws: { id: 'W', options: {}, inputs: {} },
          health: { edicion: { producto: true, beta: [] }, capabilities: {}, copia_datos: { vencida: false } },
          active: {}, run: async () => undefined, startJob: async () => undefined, jobs: {},
        } }, createElement(CargasTab, modulo ? { modulo } : {})));
        export const pintarCon = (modulo, extra) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
          ws: { id: 'W', options: {}, inputs: {} },
          health: { edicion: { producto: true, beta: [] }, capabilities: {}, copia_datos: { vencida: false } },
          active: {}, run: async () => undefined, startJob: async () => undefined, jobs: {}, ...extra,
        } }, createElement(CargasTab, modulo ? { modulo } : {})));`,
      resolveDir: RAIZ, loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  globalThis.localStorage ??= { getItem: () => null, setItem: () => {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

test('072:RF-42 las tres pestañas están en TABS, junto a VNR, PIT y VAD, y son CargasTab con su módulo', () => {
  const app = readFileSync(join(SRC, 'app', 'App.tsx'), 'utf-8');
  for (const [clave, m] of Object.entries(MATRIZ)) {
    assert.match(app, new RegExp(`\\{ id: '${m.pestana}', label: '${m.etiqueta}', el: <CargasTab modulo="${clave}" \\/>, entradas: false \\}`),
      `falta la pestaña «${m.etiqueta}»`);
  }
  assert.match(app, /\{ id: 'cargas', label: 'Cargas en DIgSILENT', el: <CargasTab \/>, entradas: false \}/, 'la de siempre sigue');
});

test('072:RF-42 matriz de cobertura: cada pestaña enseña sus secciones y no las de otro tipo, con su llamada, su ruta y su prueba', async () => {
  const { pintar, api } = await cargar();
  const cliente = readFileSync(join(SRC, 'api', 'client.ts'), 'utf-8');
  // 065:RF-9: test_frontend_rutas prueba una copia del frontend sola; allí no están las pruebas del servidor.
  const conServidor = existsSync(join(RAIZ, '..', 'tests'));
  for (const s of Object.values(SECCIONES)) {
    assert.equal(typeof api[s.llamada], 'function', `falta api.${s.llamada}`);
    assert.ok(cliente.includes(s.ruta), `api/client.ts no llama a ${s.ruta}`);
    if (conServidor) {
      const prueba = join(RAIZ, '..', s.prueba);
      assert.ok(existsSync(prueba) && readFileSync(prueba, 'utf-8').includes(s.ruta), `${s.prueba} no prueba ${s.ruta}`);
    }
  }
  for (const [clave, m] of Object.entries(MATRIZ)) {
    const html = pintar(clave);
    for (const s of m.ve) assert.ok(html.includes(SECCIONES[s].titulo), `${m.etiqueta}: falta «${SECCIONES[s].titulo}»`);
    for (const s of m.no) assert.ok(!html.includes(SECCIONES[s].titulo), `${m.etiqueta}: sobra «${SECCIONES[s].titulo}»`);
    // El tipo ya está elegido: no se ofrece cambiarlo, y los ids van con el prefijo de la pestaña.
    assert.ok(!html.includes('role="radiogroup" aria-label="Tipo de análisis"'), `${m.etiqueta}: ofrece cambiar el tipo`);
    assert.ok(html.includes(`id="${clave}-paso-proyecto"`) && !html.includes('id="paso-proyecto"'), `${m.etiqueta}: ids sin prefijo`);
  }
});

test('072:RF-42 y RF-43 «Cargas en DIgSILENT» sigue entera, sin repetir la elección del tipo que ya tiene su pestaña', async () => {
  const { pintar } = await cargar();
  const html = pintar();
  // RF-43 (usuario, 18-11): corto plazo, PIDE y largo plazo son pestañas; aquí no se vuelven a ofrecer.
  assert.ok(!html.includes('role="radiogroup" aria-label="Tipo de análisis"'), 'repite el selector de tipo de las pestañas');
  assert.ok(!html.includes('<h3>Tipo de análisis</h3>'), 'repite el recuadro «Tipo de análisis»');
  for (const s of Object.values(SECCIONES)) assert.ok(html.includes(s.titulo), `falta «${s.titulo}»`);
  assert.ok(html.includes('id="paso-proyecto"') && html.includes('id="paso-planificacion"'));
  // El año de presentación sigue en su paso 5 (072:RF-36): quitar el recuadro no lo quita. Sin proyecto el paso 5 aún
  // no pinta su formulario, así que se mira el código: la pestaña le pasa el año y GemeloPIDE pinta su campo.
  const cargas = readFileSync(join(SRC, 'features', 'powerfactory', 'CargasTab.tsx'), 'utf-8');
  const gemelo = readFileSync(join(SRC, 'features', 'powerfactory', 'GemeloPIDE.tsx'), 'utf-8');
  assert.match(cargas, /<GemeloPIDE [^>]*anio=\{anioPresentacion\}[\s\S]*?onAnio=\{setAnioPresentacion\}/,
    'el paso 5 ya no recibe el año de presentación');
  assert.match(gemelo, /<CampoAnioPresentacion /, 'el paso 5 ya no pinta el campo del año de presentación');
});

test('072:RF-43 ningún otro control de la web se llama «Tipo de análisis» para elegir otra cosa', () => {
  // Solo TipoDeAnalisis.tsx (el recuadro de los módulos) puede decir «Tipo de análisis»; el selector de dónde se busca la
  // máxima (alimentadores, SET o sistema) se llamaba igual y confundía con las pestañas de corto plazo, PIDE y largo plazo.
  const fuera = [];
  const recorrer = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const ruta = join(dir, e.name);
      if (e.isDirectory()) recorrer(ruta);
      else if (/\.(tsx|ts)$/.test(e.name) && e.name !== 'TipoDeAnalisis.tsx'
        && /Tipo de análisis/.test(readFileSync(ruta, 'utf-8').replace(/\/\/.*$|\{\/\*[\s\S]*?\*\/\}|\/\*[\s\S]*?\*\//gm, ''))) {
        fuera.push(ruta.slice(SRC.length + 1));
      }
    }
  };
  recorrer(SRC);
  assert.deepEqual(fuera, [], `«Tipo de análisis» fuera del recuadro de los módulos: ${fuera.join(', ')}`);
});

test('072:RF-42 el PIDE ya no es beta: su paso no lleva la marca y la edición no lo lista', async () => {
  const { pintar } = await cargar();
  const html = pintar('pide');
  assert.ok(html.includes('5 · Planificación PIDE y gemelo digital') && !html.includes('En beta'));
  const edicion = readFileSync(join(SRC, 'shared', 'edicion.ts'), 'utf-8');
  assert.ok(!/ClaveBeta = [^;]*'pide'/.test(edicion), 'ClaveBeta todavía tiene «pide»');
});


test('072:RF-45 el proyecto y sus alimentadores elegidos son del espacio: Cargas, Corto plazo, PIDE y Largo plazo los ven igual', async () => {
  // El usuario (18-11): «lo que haga esta parte debe estar vinculado, evitar hacer doble trabajo». Las cuatro pestañas son
  // el mismo CargasTab montado a la vez; antes cada una guardaba su proyecto y había que elegirlo otra vez en cada una.
  const { pintarCon } = await cargar();
  const lectura = { id: 'J1', kind: 'pf_projects', status: 'done', title: 'Leer proyectos',
    result: { folder: 'ConverterSmartGrid', projects: [
      { name: 'P1', path: 'Lote/P1', feeders: ['F1', 'F2'] }, { name: 'P2', path: 'Lote/P2', feeders: ['F3'] }] } };
  const espacio = { id: 'W', inputs: {}, options: { pf_proyecto_elegido: 'Lote/P2', pf_alimentadores_elegidos: ['F3'] } };
  for (const modulo of [undefined, 'corto_plazo', 'pide', 'largo_plazo']) {
    const html = pintarCon(modulo, { ws: espacio, setWs: () => undefined, jobs: { J1: lectura } });
    assert.match(html, /<option value="Lote\/P2" selected="">/, `${modulo ?? 'cargas'}: no tiene elegido el proyecto del espacio`);
    assert.doesNotMatch(html, /<option value="" selected="">— elija un proyecto —/, `${modulo ?? 'cargas'}: pide elegir otra vez`);
  }
  // Otro espacio sin proyecto elegido: nada del anterior (la elección es de cada espacio, no del navegador).
  const otro = { id: 'W2', inputs: {}, options: {} };
  for (const modulo of [undefined, 'pide']) {
    const html = pintarCon(modulo, { ws: otro, setWs: () => undefined, jobs: { J1: lectura } });
    assert.match(html, /<option value="" selected="">— elija un proyecto —/, `${modulo ?? 'cargas'}: arrastra el proyecto de otro espacio`);
    assert.doesNotMatch(html, /<option value="Lote\/P2" selected="">/, `${modulo ?? 'cargas'}: arrastra Lote/P2`);
  }
});

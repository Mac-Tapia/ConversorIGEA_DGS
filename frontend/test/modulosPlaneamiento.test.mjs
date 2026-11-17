import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
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

test('072:RF-42 «Cargas en DIgSILENT» sigue entera: el selector de tipo, todas sus secciones y sus ids de siempre', async () => {
  const { pintar } = await cargar();
  const html = pintar();
  assert.ok(html.includes('role="radiogroup" aria-label="Tipo de análisis"'));
  for (const s of Object.values(SECCIONES)) assert.ok(html.includes(s.titulo), `falta «${s.titulo}»`);
  assert.ok(html.includes('id="paso-proyecto"') && html.includes('id="paso-planificacion"'));
});

test('072:RF-42 el PIDE ya no es beta: su paso no lleva la marca y la edición no lo lista', async () => {
  const { pintar } = await cargar();
  const html = pintar('pide');
  assert.ok(html.includes('5 · Planificación PIDE y gemelo digital') && !html.includes('En beta'));
  const edicion = readFileSync(join(SRC, 'shared', 'edicion.ts'), 'utf-8');
  assert.ok(!/ClaveBeta = [^;]*'pide'/.test(edicion), 'ClaveBeta todavía tiene «pide»');
});

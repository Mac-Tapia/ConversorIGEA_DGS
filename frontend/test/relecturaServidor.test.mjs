import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// rc5 (2026-11-12): tras «Cargar perfil», el CRS de origen seguía diciendo «Sin perfil de empresa…»: la página leía el
// perfil del estado del servidor solo al abrirse. La conversión del servidor ya usaba el CRS del perfil.
let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { OptionsPanel } from './src/features/conversion/OptionsPanel';
        export { guardarPerfil } from './src/features/conversion/PerfilEmpresa';
        export function opciones(perfil) {
          const value = {
            ws: { id: 'prueba', options: { include_geography: true, source_crs: null, target_crs: 'EPSG:4326' } },
            health: { capabilities: { geo: true, preview: true }, crs_presets: [], perfil_empresa: perfil,
                      parallel: { auto: 2, cpus: 4 } },
            active: {}, jobs: {}, run: async (fn) => fn(), setWs: () => {}, startJob: async () => undefined,
            refreshHealth: () => {},
          };
          return renderToStaticMarkup(createElement(Ctx.Provider, { value }, createElement(OptionsPanel)));
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

test('086:RF-59 guardar el perfil con éxito vuelve a leer el estado del servidor', async () => {
  const { guardarPerfil } = await cargar();
  let lecturas = 0;
  const estado = { ruta: 'perfil_empresa.json', existe: true, errores: [], desconocidas: [], faltan: [] };
  assert.equal(await guardarPerfil(async () => estado, () => { lecturas += 1; }), estado);
  assert.equal(lecturas, 1);
});

test('086:RF-59 un perfil rechazado no cambia lo que se muestra', async () => {
  const { guardarPerfil } = await cargar();
  let lecturas = 0;
  assert.equal(await guardarPerfil(async () => undefined, () => { lecturas += 1; }), undefined);
  assert.equal(lecturas, 0);
});

test('086:RF-59 el panel del perfil pasa la relectura del estado de la página', () => {
  const panel = readFileSync(new URL('../src/features/conversion/PerfilEmpresa.tsx', import.meta.url), 'utf8');
  assert.match(panel, /const \{[^}]*\brefreshHealth\b[^}]*\} = useApp\(\)/);
  assert.match(panel, /guardarPerfil\([^;]*refreshHealth\)/);
  const app = readFileSync(new URL('../src/app/App.tsx', import.meta.url), 'utf8');
  assert.match(app, /refreshHealth: leerHealth/, 'la página da a los paneles la misma lectura que hace al abrirse');
});

test('086:RF-59 con el CRS en el perfil, el campo lo enseña y no avisa de que falta', async () => {
  const { opciones } = await cargar();
  const con = opciones({ crs_origen: 'EPSG:32718', error: null });
  assert.ok(con.includes('placeholder="EPSG:32718 (del perfil de empresa)"'), con);
  assert.ok(!con.includes('Sin perfil de empresa'));
  const sin = opciones({ error: null });
  assert.ok(sin.includes('Sin perfil de empresa'));
});

// rc5 (2026-11-12): asignados los libros en «2.1» y calibrado, «Recalibrar «Sin proyecto»» seguía diciendo «El espacio
// no tiene libros de demanda…» hasta recargar: lo pedía al servidor solo al elegir el proyecto.
async function claveLibros() {
  const salida = await build({
    entryPoints: [fileURLToPath(new URL('../src/features/powerfactory/DemandaMedida.tsx', import.meta.url))],
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  return m.exports.claveLibros;
}

test('086:RF-62 la clave de los libros cambia al asignarlos, quitarlos o cambiar su carpeta', async () => {
  const clave = await claveLibros();
  const medidores = { name: 'medidores.xlsx', origin: 'server', source_kind: 'file' };
  const cabecera = { name: 'cabecera', origin: 'server', source_kind: 'folder', libros: ['a.xlsx'] };
  assert.equal(clave(undefined), clave({}));
  assert.notEqual(clave({}), clave({ medidores }), 'asignar un libro');
  assert.notEqual(clave({ medidores }), clave({ medidores, cabecera }));
  assert.notEqual(clave({ medidores, cabecera }), clave({ medidores, cabecera: { ...cabecera, libros: ['a.xlsx', 'b.xlsx'] } }));
  assert.equal(clave({ medidores, cabecera }), clave({ cabecera, medidores }), 'el orden de las claves no cuenta');
  assert.equal(clave({ medidores, cabecera: undefined }), clave({ medidores }), 'quitar un libro');
});

test('086:RF-62 las dos lecturas de «Recalibrar» se repiten cuando cambian los libros del espacio', () => {
  const fuente = readFileSync(new URL('../src/features/powerfactory/DemandaMedida.tsx', import.meta.url), 'utf8');
  const efectos = [...fuente.matchAll(/useEffect\(\(\) => \{((?:(?!useEffect\()[\s\S])*?)\}, \[([^\]]*)\]\)/g)]
    .filter((m) => m[1].includes('api.recalibrarDatos'));
  assert.equal(efectos.length, 2, 'el bloque de recalibrar y el de recalibrar con criterios');
  for (const m of efectos) assert.match(m[2], /\blibros\b/, m[2]);
  assert.equal((fuente.match(/const libros = claveLibros\(ws\.demanda\)/g) ?? []).length, 2);
});

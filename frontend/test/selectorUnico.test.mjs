import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// 109 T19 (SELECTOR-UNICO): el campo único «Elegir archivo» de cada entrada y el «Guardar en…» de cada salida.
const raiz = fileURLToPath(new URL('..', import.meta.url));

async function cargar() {
  const r = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { FileDrop, GuardarSalida } from './src/shared/ui';
    import { NubeEntradasCtx } from './src/shared/nubeEntradas';
    export * from './src/shared/origenes';
    const con = (valor, hijo) => valor ? createElement(NubeEntradasCtx.Provider, { value: valor }, hijo) : hijo;
    export const pintarCampo = (props, valor) => renderToStaticMarkup(con(valor,
      createElement(FileDrop, { onFiles: () => undefined, ...props }, 'Soltar o elegir')));
    export const pintarGuardar = (props, valor) => renderToStaticMarkup(con(valor, createElement(GuardarSalida, props)));`,
  resolveDir: raiz, loader: 'tsx' }, bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', r.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
  return mod.exports;
}

const cuenta = (nombre, conectada) => ({ nombre, conectada, cuenta: conectada ? 'operador@ejemplo.org' : null });

test('109:RF-21 el equipo siempre; Drive u OneDrive solo con su cuenta conectada', async () => {
  const { origenesDe } = await cargar();
  assert.deepEqual(origenesDe(null), ['equipo']);
  assert.deepEqual(origenesDe([cuenta('google', false), cuenta('microsoft', false)]), ['equipo']);
  assert.deepEqual(origenesDe([cuenta('microsoft', true), cuenta('google', true)]), ['equipo', 'google', 'microsoft']);
  assert.deepEqual(origenesDe([{ nombre: 'google', conectada: true, cuenta: null }]), ['equipo'],
    'conectada sin cuenta no cuenta');
});

test('109:RF-21 sin nube el campo es el de siempre; con cuenta ofrece su origen en el mismo campo', async () => {
  const { pintarCampo } = await cargar();
  const solo = pintarCampo({ accept: '.xlsx' });
  assert.match(solo, /Soltar o elegir/);
  assert.match(solo, /type="file"/);
  assert.doesNotMatch(solo, /Google Drive|OneDrive/);
  const conNube = pintarCampo({ accept: '.xlsx' }, { origenes: ['equipo', 'google', 'microsoft'], traer: async () => [] });
  assert.match(conNube, /role="group" aria-label="Elegir de la nube"/);
  assert.match(conNube, />Google Drive<\/button>/);
  assert.match(conNube, />OneDrive<\/button>/);
  assert.doesNotMatch(conNube, /RF-\d|109:/, 'sin citas de requisitos en pantalla');
});

test('109:RF-23 cada entrada admite solo sus tipos, por extensión o por MIME', async () => {
  const { admite, separarPorTipo, tiposEnPalabras } = await cargar();
  assert.equal(admite('Libro.XLSX', '', '.xlsx,.csv'), true);
  assert.equal(admite('libro.xls', '', '.xlsx,.csv'), false);
  assert.equal(admite('acta', 'application/pdf', '.pdf,application/pdf'), true);
  assert.equal(admite('foto.heic', 'image/heic', 'image/*'), true);
  assert.equal(admite('cualquiera.bin', '', undefined), true, 'sin filtro, todo vale');
  assert.equal(tiposEnPalabras('.xlsx,.csv,.xlsm'), '.xlsx, .csv o .xlsm');
  const r = separarPorTipo([{ name: 'a.xlsx', type: '' }, { name: 'b.pdf', type: '' }], '.xlsx,.csv');
  assert.deepEqual(r.validos.map((f) => f.name), ['a.xlsx']);
  assert.equal(r.aviso, '«b.pdf» no vale aquí: admite .xlsx o .csv.');
  assert.equal(separarPorTipo([{ name: 'a.xlsx', type: '' }], '.xlsx').aviso, null);
  assert.match(separarPorTipo([{ name: 'x.doc', type: '' }, { name: 'y.doc', type: '' }], '.pdf').aviso,
    /^«x\.doc», «y\.doc» no valen aquí: admite \.pdf\.$/);
});

function ventana({ picker, cancelar } = {}) {
  const hecho = { escrito: null, cerrado: false, clic: null, revocado: null };
  const w = {
    document: { createElement: () => ({ href: '', download: '', click() { hecho.clic = { href: this.href, nombre: this.download }; } }),
      body: { appendChild: () => undefined } },
    URL: { createObjectURL: () => 'blob:prueba', revokeObjectURL: (u) => { hecho.revocado = u; } },
  };
  if (picker) {
    w.showSaveFilePicker = async ({ suggestedName }) => {
      hecho.sugerido = suggestedName;
      if (cancelar) { const e = new Error('cancelado'); e.name = 'AbortError'; throw e; }
      return { createWritable: async () => ({ write: async (d) => { hecho.escrito = d; }, close: async () => { hecho.cerrado = true; } }) };
    };
  }
  return { w, hecho };
}

test('109:RF-24 guardar en el equipo pide la carpeta y el nombre; sin ese diálogo, va a la descarga del navegador', async () => {
  const { guardarEnEquipo } = await cargar();
  const datos = new Blob(['informe']);
  const con = ventana({ picker: true });
  assert.equal(await guardarEnEquipo(datos, 'estudio.docx', con.w), 'guardado');
  assert.equal(con.hecho.sugerido, 'estudio.docx');
  assert.equal(con.hecho.escrito, datos);
  assert.equal(con.hecho.cerrado, true);
  const cancelado = ventana({ picker: true, cancelar: true });
  assert.equal(await guardarEnEquipo(datos, 'estudio.docx', cancelado.w), 'cancelado');
  assert.equal(cancelado.hecho.escrito, null);
  const sin = ventana();
  assert.equal(await guardarEnEquipo(datos, 'estudio.docx', sin.w), 'descargado');
  assert.deepEqual(sin.hecho.clic, { href: 'blob:prueba', nombre: 'estudio.docx' });
  assert.equal(sin.hecho.revocado, 'blob:prueba');
});

test('109:RF-24 «Guardar en…» va junto a la salida; «Nube» solo con una cuenta conectada', async () => {
  const { pintarGuardar } = await cargar();
  const props = { url: '/api/workspaces/w/files/informes/e.docx?download=1', nombre: 'e.docx', rel: 'informes/e.docx' };
  const solo = pintarGuardar(props);
  assert.match(solo, /aria-label="Guardar e\.docx en una carpeta"/);
  assert.doesNotMatch(solo, />Nube</);
  const Publicar = ({ seleccion }) => `publicar:${seleccion.join(',')}`;
  const conNube = pintarGuardar(props, { origenes: ['equipo', 'google'], traer: async () => [], Publicar });
  assert.match(conNube, /publicar:informes\/e\.docx/);
});

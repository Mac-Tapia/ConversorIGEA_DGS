import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// Prueba con la cuenta local, 2026-11-16 (PRUEBA-CUENTA-LOCAL/INFORME.md): «Hacer una copia ahora» escribía unos 20 GB en
// Google Drive con un clic, sin previa ni «Cancelar»; el aviso decía «Aún no hay ninguna copia» con una en la carpeta; y
// sobraban seis textos. Spec 086: aclaración de RF-82 y RF-83, RF-108, RF-109 y RF-110.
let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { Ctx } from './src/shared/context';
        import { AvisosDatos, PreviaCopia } from './src/app/AvisosDatos';
        import { OptionsPanel } from './src/features/conversion/OptionsPanel';
        import { TipoDeAnalisis } from './src/features/powerfactory/TipoDeAnalisis';
        export { MARCADOR_CARPETA_COPIA, resumenCopia, ultimaBuena } from './src/app/AvisosDatos';
        export { resumenAuto, lineaDeEntrada } from './src/features/conversion/InputsPanel';
        export { textoPildoraPf } from './src/app/InstalacionesPowerFactory';
        export { textoNorma } from './src/features/powerfactory/TipoDeAnalisis';
        export { fmtBytes } from './src/shared/formato';
        export { api } from './src/api/client';
        const nada = () => undefined;
        export const previa = (p) => renderToStaticMarkup(createElement(PreviaCopia, { previa: p, onCopiar: nada, onCancelar: nada }));
        export const aviso = (copia) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
          ws: { id: 'W', no_disponibles: [], avisos_datos: [] }, health: { copia_datos: copia, server_paths: true },
          jobs: {}, run: async (f) => f(), setWs: nada, startJob: async () => undefined, refreshHealth: nada } },
          createElement(AvisosDatos, { pestanas: [] })));
        export const opciones = () => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
          ws: { id: 'W', options: { source_crs: 'EPSG:32718', target_crs: 'EPSG:4326', include_geography: true } },
          health: { capabilities: { geography: true, xlsx: true }, perfil_empresa: {}, crs_presets: [],
            parallel: { auto: 4, cpus: 8 } },
          active: {}, run: async (f) => f(), setWs: nada } }, createElement(OptionsPanel)));
        export const tipo = (props) => renderToStaticMarkup(createElement(TipoDeAnalisis, {
          onTipo: nada, onAnio: nada, error: '', planificacion: true, anio: '', estado: {}, ...props }));`,
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

const GB = 1024 ** 3;
const PREVIA = {
  destino: 'D:/copias', ficheros_fisicos: 8989, nombres: 11933, bytes_fisicos: 19.8 * GB, bytes_logicos: 83 * GB,
  libre: 20.9 * GB, margen: 64 * 1024 ** 2, cabe: true, texto: 'La copia ocupará 19,8 GB…',
  raices: [{ nombre: 'datos', etiqueta: 'Espacios de trabajo', ruta: 'D:/datos', ficheros: 8000, bytes: 19 * GB },
    { nombre: 'config', etiqueta: 'Configuración', ruta: 'D:/config', ficheros: 2, bytes: 4096 }],
  copias: [],
};
const COPIA = (estado, extra = {}) => ({ nombre: `csg-copia-${estado}`, ruta: `D:/copias/csg-copia-${estado}`, estado,
  motivo: null, creada: Date.UTC(2026, 10, 12, 18, 42) / 1000, bytes: 19.8 * GB, ficheros: 8989, nombres: 11933,
  errores: 0, ...extra });
const botones = (html) => [...html.matchAll(/<button[^>]*>([^<]*)<\/button>/g)].map((b) => b[1]);

test('086:RF-82 la previa dice lo que ocupará, lo libre y lo que se copia, con «Copiar» y «Cancelar»', async () => {
  const { previa } = await cargar();
  const html = previa(PREVIA);
  assert.ok(html.includes('Ocupará <strong>19.8 GB</strong>'), 'lo que ocupará, en GB');
  assert.ok(html.includes('Libre: <strong>20.9 GB</strong>'), 'el espacio libre del destino');
  assert.ok(html.includes('D:/copias'), 'el destino');
  assert.ok(html.includes('Espacios de trabajo: 19.0 GB') && html.includes('Configuración: 4.0 KB'), 'lo que se copia');
  assert.deepEqual(botones(html).filter((b) => b !== '×'), ['Cancelar', 'Copiar']);
});

test('086:RF-83 si no cabe, la previa da las dos cifras y no ofrece «Copiar»', async () => {
  const { previa } = await cargar();
  const html = previa({ ...PREVIA, libre: 5 * GB, cabe: false });
  assert.match(html, /role="alert"[^>]*>No cabe: ocupará 19\.8 GB y hay\s*5\.0 GB libres\. No se copia nada\./);
  assert.deepEqual(botones(html).filter((b) => b !== '×'), ['Cancelar'], 'sin sitio no hay «Copiar»');
});

test('086:RF-82 «Copiar» manda la previa vista y la confirmación; la previa es un GET sin escritura', async () => {
  const { api } = await cargar();
  const llamadas = [];
  const fetchReal = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    llamadas.push({ url, init });
    return { ok: true, status: 200, json: async () => ({}) };
  };
  try {
    await api.previaCopia('C:/Users/Ana/OneDrive/copias de datos');
    await api.copiarDatos('W', PREVIA);
  } finally {
    globalThis.fetch = fetchReal;
  }
  assert.equal(llamadas[0].url, '/api/copia-datos/previa?carpeta=C%3A%2FUsers%2FAna%2FOneDrive%2Fcopias%20de%20datos');
  assert.ok(!llamadas[0].init || !llamadas[0].init.method || llamadas[0].init.method === 'GET', 'la previa no escribe');
  assert.equal(llamadas[1].url, '/api/workspaces/W/copia-datos');
  assert.deepEqual(JSON.parse(llamadas[1].init.body), { carpeta: 'D:/copias', confirmada: true });
});

test('086:RF-108 la previa lista las copias de la carpeta con fecha, tamaño, estado y errores', async () => {
  const { previa } = await cargar();
  assert.ok(previa(PREVIA).includes('Copias en esta carpeta</h3><p class="small muted">Ninguna.</p>'));
  const html = previa({ ...PREVIA, copias: [COPIA('buena'), COPIA('con_errores', { errores: 2 }),
    COPIA('no_valida', { creada: null, bytes: null, motivo: 'El manifiesto no tiene el contenido esperado.' }),
    COPIA('a_medias', { creada: null, bytes: null })] });
  const filas = [...html.matchAll(/<li[^>]*>(.*?)<\/li>/g)].map((f) => f[1].replace(/<[^>]+>/g, ''));
  const copias = filas.filter((f) => f.includes(' · '));
  assert.equal(copias.length, 4, filas.join(' | '));
  assert.match(copias[0], /12\/11\/26.* · 19\.8 GB · Completa$/);
  assert.match(copias[1], / · Con errores · 2 errores$/);
  assert.match(copias[2], /^Sin fecha · — · No válida$/);
  assert.match(copias[3], /^Sin fecha · — · A medias$/);
  assert.ok(html.includes('title="El manifiesto no tiene el contenido esperado."'), 'el motivo, al pasar el ratón');
});

test('086:RF-109 el aviso nunca dice «no hay»; cuenta la copia que la previa vio en la carpeta', async () => {
  const { resumenCopia, ultimaBuena, aviso } = await cargar();
  const sinNada = { ultima: null, ruta: null, edad_dias: null, maxima_dias: 7, vencida: true, aviso: '' };
  assert.equal(resumenCopia(sinNada), 'No consta ninguna copia de sus datos.');
  const html = aviso(sinNada);
  assert.ok(html.includes('No consta ninguna copia de sus datos.') && !/no hay/i.test(html), html);
  const ahora = Date.UTC(2026, 10, 16) / 1000;
  const vista = ultimaBuena([COPIA('no_valida', { creada: ahora }), COPIA('buena', { creada: ahora - 4 * 86400 }),
    COPIA('buena', { creada: ahora - 9 * 86400 }), COPIA('con_errores', { creada: ahora - 86400 })]);
  assert.equal(vista, ahora - 4 * 86400, 'solo cuentan las completas, y la más nueva');
  assert.equal(resumenCopia(sinNada, vista, ahora), 'La última copia de sus datos tiene 4 días.');
  assert.equal(resumenCopia(sinNada, ahora - 9 * 86400, ahora), 'La última copia de sus datos tiene 9 días (el máximo es 7).');
  const vieja = { ...sinNada, ultima: ahora - 20 * 86400, edad_dias: 20 };
  assert.equal(resumenCopia(vieja, null, ahora), 'La última copia de sus datos tiene 20 días (el máximo es 7).');
  assert.equal(resumenCopia(vieja, ahora - 30 * 86400, ahora), 'La última copia de sus datos tiene 20 días (el máximo es 7).',
    'una vista más vieja que la del servidor no cuenta');
  assert.equal(ultimaBuena([]), null);
});

test('086:RF-110 el campo de la copia vale para cualquier carpeta, no supone Google Drive', async () => {
  const { MARCADOR_CARPETA_COPIA, aviso } = await cargar();
  const html = aviso({ ultima: null, ruta: null, edad_dias: null, maxima_dias: 7, vencida: true, aviso: '' });
  assert.ok(html.includes(`placeholder="${MARCADOR_CARPETA_COPIA}"`));
  for (const fijo of ['G:', 'Mi unidad', 'copias_de_datos']) assert.ok(!MARCADOR_CARPETA_COPIA.includes(fijo), fijo);
  assert.ok(MARCADOR_CARPETA_COPIA.includes('OneDrive') && MARCADOR_CARPETA_COPIA.includes('disco'));
  assert.ok(!html.includes('Google Drive'), 'la explicación tampoco nombra un solo proveedor');
});

test('086:RF-110 el aviso de la casilla automática, sin «(s)», sin ceros de titular ni «por contenido»', async () => {
  const { resumenAuto } = await cargar();
  const casilla = () => 'RED';
  const uno = resumenAuto({ assigned: [], unassigned: [{ name: 'entorno.txt', reason: 'no declara tablas conocidas de CYMDIST' }] }, casilla);
  assert.deepEqual(uno, { tono: 'warn', titulo: 'entorno.txt no se reconoce', detalle: 'entorno.txt: no declara tablas conocidas de CYMDIST' });
  const dos = resumenAuto({ assigned: [], unassigned: [{ name: 'a.txt', reason: 'x' }, { name: 'b.txt', reason: 'y' }] }, casilla);
  assert.equal(dos.titulo, 'Ningún fichero reconocido');
  assert.equal(resumenAuto({ assigned: [{ slot: 'red', name: 'R.txt' }], unassigned: [] }, casilla).titulo, '1 fichero asignado');
  const tres = resumenAuto({ assigned: [1, 2, 3].map((i) => ({ slot: 'red', name: `R${i}.txt` })), unassigned: [] }, casilla);
  assert.deepEqual([tres.tono, tres.titulo, tres.detalle.split('\n')[0]], ['ok', '3 ficheros asignados', 'R1.txt → RED']);
  for (const r of [uno, dos, tres]) assert.ok(!/\(s\)|por contenido|^0 /.test(r.titulo), r.titulo);
});

test('086:RF-110 la píldora de la cabecera nombra la instalación, sin la versión de Python', async () => {
  const { textoPildoraPf } = await cargar();
  assert.equal(textoPildoraPf({ instalacion: 'PowerFactory 2024', api_version: '3.12' }), 'PowerFactory 2024');
  assert.equal(textoPildoraPf(null), 'PowerFactory');
});

test('086:RF-110 072:RF-37 la norma, en una frase sin paréntesis y solo con un tipo elegido', async () => {
  const { textoNorma, tipo } = await cargar();
  const norma = { acto: 'RM 428-2017-MEM/DM', titulo: 'Norma de prueba', estado_juridico: 'proyecto', vigente: false, nota: '' };
  const texto = textoNorma(norma);
  assert.equal(texto, 'Según RM 428-2017-MEM/DM, «Norma de prueba». Estado jurídico: proyecto; no es norma vigente.');
  assert.ok(!texto.includes('('));
  assert.equal(textoNorma({ ...norma, vigente: true }), 'Según RM 428-2017-MEM/DM, «Norma de prueba».');
  const tipos = { norma, tipos: [{ clave: 'corto_plazo', titulo: 'Corto plazo', descripcion: '', articulos: [], anios: [],
    formatos: [], entregables: [], obras_admitidas: [], obras_excluidas: [], aplica_obras: true }],
  anio_presentacion_perfil: null, anio_presentacion_rango: { min: 2000, max: 2100 } };
  assert.ok(!tipo({ tipo: null, tipos }).includes('RM 428'), 'en la vista inicial, sin elegir nada, no sale');
});

test('086:RF-110 la ayuda del CRS va plegada, detrás de su resumen', async () => {
  const { opciones } = await cargar();
  const html = opciones();
  assert.match(html, /<details class="ayuda"><summary>Qué CRS vale<\/summary><div class="muted">Cualquier EPSG <b>proyectado en metros<\/b>[^<]*100\.000 veces/);
  assert.ok(!/<details class="ayuda" open/.test(html), 'plegada al abrir la web');
});

test('086:RF-110 (W8) con la fuente ya cargada, la línea de la entrada no vuelve a pedir «Cargar / listar»', async () => {
  const { lineaDeEntrada } = await cargar();
  assert.equal(typeof lineaDeEntrada, 'function', 'falta lineaDeEntrada en InputsPanel (086:RF-110, W8)');
  assert.equal(lineaDeEntrada(true, 'txt', true, []), 'Los tres TXT cargados.');
  assert.equal(lineaDeEntrada(true, 'mdb', true, []), 'Base de datos cargada.');
  assert.equal(lineaDeEntrada(true, 'vnr', true, []), 'Paquete VNR-GIS cargado.');
  assert.match(lineaDeEntrada(true, 'txt', false, []), /Pulse «Cargar \/ listar alimentadores»/);
  assert.equal(lineaDeEntrada(false, 'txt', false, ['RED', 'CARGA']), 'Pendientes: RED, CARGA.');
});


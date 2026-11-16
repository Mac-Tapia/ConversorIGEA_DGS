import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// 109 T14: la tarjeta de las cuentas, el selector, las versiones y compartir, pintados de verdad con React.
const raiz = fileURLToPath(new URL('..', import.meta.url));

async function cargar() {
  const r = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { TarjetaCuentas } from './src/app/CuentasNube';
    import { ListaVinculos } from './src/features/nube/VersionesNuevas';
    import { VistaCompartir } from './src/features/nube/PublicarExpediente';
    export * from './src/features/nube/logica';
    export { separarDirecciones } from './src/shared/direcciones';
    export const pintarCuentas = (p) => renderToStaticMarkup(createElement(TarjetaCuentas, p));
    export const pintarVinculos = (p) => renderToStaticMarkup(createElement(ListaVinculos, p));
    export const pintarCompartir = (p) => renderToStaticMarkup(createElement(VistaCompartir, p));`,
  resolveDir: raiz, loader: 'tsx' }, bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', r.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
  return mod.exports;
}

const nada = () => undefined;
const fila = (nombre, visible, extra = {}) => ({ nombre, visible, registrado: true, se_puede_conectar: true, motivo: null,
  permisos: 'Solo los ficheros que usted elija.', conectada: false, cuenta: null, permisos_concedidos: null,
  puede_publicar: null, puede_enviar: null, ...extra });
const SIN_REGISTRO = [
  fila('google', 'Google Drive', { registrado: false, se_puede_conectar: false,
    motivo: 'Sin cuenta conectada: configure config/nube.json (falta registrar la aplicación de Google Drive …)' }),
  fila('microsoft', 'OneDrive', { registrado: false, se_puede_conectar: false, motivo: 'Sin cuenta conectada: …' }),
];
const base = { cuentas: SIN_REGISTRO, error: null, aviso: null, ocupado: false, onConectar: nada, onDesconectar: nada };
// Lo que el operador nunca debe leer en pantalla: citas de la spec ni jerga interna.
const sinJerga = (html) => {
  assert.doesNotMatch(html, /RF-\d|109:|110:|CSG_|NUBE_REGISTRO|\.py\b/);
};

test('109:RF-19 sin cliente OAuth la tarjeta dice «Sin cuenta conectada: configure config/nube.json» y no ofrece conectar', async () => {
  const { pintarCuentas, SIN_CUENTA } = await cargar();
  assert.equal(SIN_CUENTA, 'Sin cuenta conectada: configure config/nube.json');
  const html = pintarCuentas(base);
  assert.ok(html.includes(SIN_CUENTA), html);
  assert.doesNotMatch(html, />Conectar</);
  assert.doesNotMatch(html, /docs\//);
  sinJerga(html);
});

test('109:RF-19 si la API falla, la tarjeta no se rompe: dice que no hay cuenta y muestra el motivo del servidor', async () => {
  const { pintarCuentas, SIN_CUENTA } = await cargar();
  const html = pintarCuentas({ ...base, cuentas: null, error: 'No se encontró la ruta' });
  assert.ok(html.includes(SIN_CUENTA));
  assert.ok(html.includes('No se encontró la ruta'));
  assert.match(html, /role="alert"|aria-live/);
});

test('109:RF-1, RF-14 con el registro hecho: conectar la que falta, desconectar la conectada y su correo a la vista', async () => {
  const { pintarCuentas, SIN_CUENTA } = await cargar();
  const html = pintarCuentas({ ...base, cuentas: [
    fila('google', 'Google Drive', { conectada: true, cuenta: 'ana@ejemplo.org' }),
    fila('microsoft', 'OneDrive')] });
  assert.ok(!html.includes(SIN_CUENTA));
  assert.ok(html.includes('ana@ejemplo.org'));
  assert.match(html, />Desconectar</);
  assert.match(html, />Conectar</);
  // Cada botón dice de qué proveedor es, para el lector de pantalla.
  assert.match(html, /aria-label="Conectar OneDrive"/);
  assert.match(html, /aria-label="Desconectar Google Drive"/);
  sinJerga(html);
});

test('109:RF-1, 110:RF-1 cada cuenta conectada dice lo que permite hoy: archivos y correo, con la misma cuenta', async () => {
  const { pintarCuentas } = await cargar();
  const html = pintarCuentas({ ...base, cuentas: [
    fila('google', 'Google Drive', { conectada: true, cuenta: 'ana@ejemplo.org', puede_publicar: true, puede_enviar: true,
      permisos_concedidos: ['drive.file', 'gmail.send'] }),
    fila('microsoft', 'OneDrive', { conectada: true, cuenta: 'luis@ejemplo.org', puede_publicar: false, puede_enviar: false,
      permisos_concedidos: ['Files.Read'] })] });
  assert.ok(html.includes('Archivos: leer y publicar · Correo: enviar'), html);
  assert.ok(html.includes('Archivos: leer · Correo: no'), html);
  // Sin saber los permisos (null), no se inventa nada.
  const sinSaber = pintarCuentas({ ...base, cuentas: [fila('google', 'Google Drive', { conectada: true, cuenta: 'a@b.org' })] });
  assert.doesNotMatch(sinSaber, /Archivos:|Correo:/);
  sinJerga(html);
  assert.doesNotMatch(html, /gmail\.send|Files\.Read|drive\.file/);
});

test('109:RF-19 registrado pero con la salida a la nube apagada: no se ofrece conectar y se dice por qué', async () => {
  const { pintarCuentas } = await cargar();
  const html = pintarCuentas({ ...base, cuentas: [
    fila('google', 'Google Drive', { se_puede_conectar: false, motivo: 'La salida a la nube está apagada.' }),
    fila('microsoft', 'OneDrive', { registrado: false, se_puede_conectar: false, motivo: 'Sin cuenta conectada: …' })] });
  assert.doesNotMatch(html, />Conectar</);
  assert.ok(html.includes('La salida a la nube está apagada.'));
});

test('109:RF-1, RF-14 los botones se desactivan mientras se conecta o desconecta (sin doble envío)', async () => {
  const { pintarCuentas } = await cargar();
  const html = pintarCuentas({ ...base, ocupado: true, cuentas: [fila('google', 'Google Drive')] });
  assert.match(html, /<button[^>]*disabled=""[^>]*>Conectar</);
});

test('109:RF-1 la vuelta del proveedor se lee de la dirección y se dice en una frase', async () => {
  const { leerRetorno } = await cargar();
  assert.equal(leerRetorno(''), null);
  assert.equal(leerRetorno('?panel=cargas'), null);
  assert.deepEqual(leerRetorno('?nube=conectada&proveedor=google'), { tono: 'ok', texto: 'Google Drive conectado.' });
  assert.deepEqual(leerRetorno('?nube=conectada&proveedor=microsoft'), { tono: 'ok', texto: 'OneDrive conectado.' });
  assert.equal(leerRetorno('?nube=cancelada').tono, 'warn');
  assert.equal(leerRetorno('?nube=error').tono, 'error');
  // Un proveedor que no es de la lista no se pinta tal cual.
  assert.equal(leerRetorno('?nube=conectada&proveedor=<b>x</b>').texto, 'Cuenta conectada.');
});

test('109:RF-3, RF-16 del selector solo valen los ids que llegan del propio origen, del proveedor abierto y con su forma', async () => {
  const { seleccionDelSelector, MENSAJE_SELECCION } = await cargar();
  const ok = { origin: 'http://127.0.0.1:8765', data: { tipo: MENSAJE_SELECCION, proveedor: 'google', modo: 'ficheros', ids: ['a1', 'b2'] } };
  assert.deepEqual(seleccionDelSelector(ok, 'http://127.0.0.1:8765', 'google', 'ficheros'), ['a1', 'b2']);
  assert.equal(seleccionDelSelector({ ...ok, origin: 'https://otro.example' }, 'http://127.0.0.1:8765', 'google', 'ficheros'), null);
  assert.equal(seleccionDelSelector(ok, 'http://127.0.0.1:8765', 'microsoft', 'ficheros'), null);
  assert.equal(seleccionDelSelector(ok, 'http://127.0.0.1:8765', 'google', 'carpeta'), null);
  assert.equal(seleccionDelSelector({ ...ok, data: { ...ok.data, tipo: 'otro' } }, 'http://127.0.0.1:8765', 'google', 'ficheros'), null);
  assert.equal(seleccionDelSelector({ ...ok, data: { ...ok.data, ids: [1, 2] } }, 'http://127.0.0.1:8765', 'google', 'ficheros'), null);
  // Cancelar en el selector devuelve una lista vacía: no es un error, no importa nada.
  assert.deepEqual(seleccionDelSelector({ ...ok, data: { ...ok.data, ids: [] } }, 'http://127.0.0.1:8765', 'google', 'ficheros'), []);
});

test('109:RF-3, RF-4 la importación dice a qué casilla o libro va y respeta un solo fichero por casilla', async () => {
  const { peticionImportar } = await cargar();
  assert.deepEqual(peticionImportar('google', ['x'], 'casilla:red'), { proveedor: 'google', ids: ['x'], casilla: 'red' });
  assert.deepEqual(peticionImportar('microsoft', ['a', 'b'], 'libro:clientes'),
    { proveedor: 'microsoft', ids: ['a', 'b'], libro: 'clientes' });
  assert.throws(() => peticionImportar('google', ['a', 'b'], 'casilla:red'), /un solo fichero/);
  assert.throws(() => peticionImportar('google', [], 'casilla:red'), /Elija/);
  assert.throws(() => peticionImportar('google', ['a'], ''), /Elija/);
  // Un libro que no es de la lista del contrato no sale del navegador.
  assert.throws(() => peticionImportar('google', ['a'], 'libro:otro'), /Elija/);
});

test('109:RF-9 publicar pide el permiso solo a la cuenta conectada que no lo concedió o de la que no se sabe', async () => {
  const { faltaPermiso } = await cargar();
  assert.equal(faltaPermiso(fila('microsoft', 'OneDrive', { conectada: true, cuenta: 'a@b.org', puede_publicar: false }), 'publicar'), true);
  assert.equal(faltaPermiso(fila('microsoft', 'OneDrive', { conectada: true, cuenta: 'a@b.org', puede_publicar: null }), 'publicar'), true);
  assert.equal(faltaPermiso(fila('google', 'Google Drive', { conectada: true, cuenta: 'a@b.org', puede_publicar: true }), 'publicar'), false);
  assert.equal(faltaPermiso(fila('google', 'Google Drive', { puede_publicar: false }), 'publicar'), false);
  assert.equal(faltaPermiso(undefined, 'enviar'), false);
  assert.equal(faltaPermiso(fila('google', 'Google Drive', { conectada: true, cuenta: 'a@b.org', puede_enviar: true }), 'enviar'), false);
});

test('109:RF-7, RF-8, RF-10 lo que el contrato da como objeto libre se lee campo a campo y lo malformado no se pinta', async () => {
  const { destinoDe, nombreDestino, comparacionDe, publicacionesDe } = await cargar();
  const v = (extra) => ({ id: 'x', proveedor: 'google', item_id: 'i', nombre_remoto: 'r.txt', vigente: {}, historial: [],
    estado: 'nueva', comprobado: '', motivo: null, nueva: null, destino: {}, candidata: null, ...extra });
  assert.deepEqual(destinoDe(v({ destino: { casilla: 'red' } })), { casilla: 'red', libro: null });
  assert.equal(nombreDestino(v({ destino: { libro: 'clientes' } })), 'Libro de clientes');
  assert.equal(nombreDestino(v({ destino: { casilla: 7 } })), '');
  assert.equal(comparacionDe(v({})), null);
  assert.equal(comparacionDe(v({ candidata: { comparacion: { iguales: 'no' } } })), null);
  assert.deepEqual(comparacionDe(v({ candidata: { comparacion: { iguales: false, anterior: { tamano: 10 },
    nueva: { tamano: 'x' } } } })), { iguales: false, tamanoAnterior: 10, tamanoNuevo: null, lineas: null });
  assert.deepEqual(publicacionesDe([
    { tipo: 'publicacion', clave: 'k1', nombre_remoto: 'exp.zip', hora: '2026-11-15T10:00:00' },
    { tipo: 'permiso', clave: 'k2', publicacion: 'k1' },
    { tipo: 'publicacion', paquete: 'p' },
    { tipo: 'publicacion', clave: 'k3', paquete: 'p3' }]),
  [{ clave: 'k1', etiqueta: 'exp.zip · 2026-11-15 10:00' }, { clave: 'k3', etiqueta: 'p3' }]);
});

test('109:RF-8 la comparación sin tamaños legibles dice que el contenido es distinto, sin números inventados', async () => {
  const { pintarVinculos } = await cargar();
  const v = { id: 'x', destino: { casilla: 'red' }, proveedor: 'google', item_id: 'i', nombre_remoto: 'r.txt', vigente: {},
    historial: [], estado: 'nueva', comprobado: '', motivo: null, nueva: null,
    candidata: { comparacion: { iguales: false, anterior: {}, nueva: {} } } };
  const html = pintarVinculos({ vinculos: [v], ocupado: false, onTraer: nada, onAceptar: nada });
  assert.ok(html.includes('Contenido distinto.'), html);
  assert.doesNotMatch(html, /NaN|undefined/);
  sinJerga(html);
});

test('109:RF-10 los destinatarios se separan por coma, punto y coma o línea, sin repetidos, y los mal escritos se nombran', async () => {
  const { separarDirecciones } = await cargar();
  const r = separarDirecciones('ana@ejemplo.org; Luis@Ejemplo.org,\nana@EJEMPLO.org  mal@  ');
  assert.deepEqual(r.validas, ['ana@ejemplo.org', 'Luis@Ejemplo.org']);
  assert.deepEqual(r.invalidas, ['mal@']);
  assert.deepEqual(separarDirecciones('   ').validas, []);
});

test('109:RF-10, RF-11, RF-20 compartir solo se confirma sin datos crudos, con confirmación y, si es público, con su autorización', async () => {
  const { puedeConfirmarCompartir } = await cargar();
  const previa = { acceso: [{ destinatario: 'ana@ejemplo.org', rol: 'lectura' }], destinatarios: ['ana@ejemplo.org'],
    publico: false, aviso_publico: null, bloqueo: [], confirmacion: 'tok', nombre: 'exp.zip', proveedor: 'google',
    paquete: 'p', publicacion: 'c' };
  assert.equal(puedeConfirmarCompartir(previa, false), true);
  assert.equal(puedeConfirmarCompartir({ ...previa, bloqueo: ['red.txt'], confirmacion: null }, false), false);
  assert.equal(puedeConfirmarCompartir({ ...previa, confirmacion: null }, false), false);
  const publica = { ...previa, publico: true, aviso_publico: 'Cualquiera que tenga el enlace podrá verlo, sin iniciar sesión.' };
  assert.equal(puedeConfirmarCompartir(publica, false), false);
  assert.equal(puedeConfirmarCompartir(publica, true), true);
  assert.equal(puedeConfirmarCompartir(null, true), false);
});

test('109:RF-10, RF-11 la vista de compartir lista quién tendrá acceso y avisa del enlace público con su casilla', async () => {
  const { pintarCompartir } = await cargar();
  const previa = { acceso: [{ destinatario: 'ana@ejemplo.org', rol: 'lectura' },
    { destinatario: 'cualquiera con el enlace', rol: 'lectura' }], destinatarios: ['ana@ejemplo.org'], publico: true,
  aviso_publico: 'Cualquiera que tenga el enlace podrá verlo, sin iniciar sesión.', bloqueo: [], confirmacion: 'tok',
  nombre: 'exp.zip', proveedor: 'google', paquete: 'p', publicacion: 'c' };
  const html = pintarCompartir({ previa, autorizo: false, onAutorizo: nada, ocupado: false, onConfirmar: nada });
  assert.ok(html.includes('ana@ejemplo.org'));
  assert.ok(html.includes('cualquiera con el enlace'));
  assert.ok(html.includes('Cualquiera que tenga el enlace podrá verlo'));
  assert.match(html, /type="checkbox"/);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Compartir</);
  assert.match(pintarCompartir({ previa, autorizo: true, onAutorizo: nada, ocupado: false, onConfirmar: nada }),
    /<button(?![^>]*disabled)[^>]*>Compartir</);
  sinJerga(html);
});

test('109:RF-20 un expediente con datos crudos nombra los ficheros que lo impiden y no deja compartir', async () => {
  const { pintarCompartir } = await cargar();
  const previa = { acceso: [{ destinatario: 'ana@ejemplo.org', rol: 'lectura' }], destinatarios: ['ana@ejemplo.org'],
    publico: false, aviso_publico: null, bloqueo: ['entrega/RED.txt', 'base.mdb'], confirmacion: null, nombre: 'exp.zip',
    proveedor: 'google', paquete: 'p', publicacion: 'c' };
  const html = pintarCompartir({ previa, autorizo: false, onAutorizo: nada, ocupado: false, onConfirmar: nada });
  assert.ok(html.includes('entrega/RED.txt') && html.includes('base.mdb'));
  assert.match(html, /<button[^>]*disabled=""[^>]*>Compartir</);
});

test('109:RF-7, RF-8, RF-17 cada vínculo dice si hay versión nueva, si no se pudo comprobar o si está al día', async () => {
  const { pintarVinculos, estadoVinculo } = await cargar();
  const v = (estado, extra = {}) => ({ id: estado, destino: { casilla: 'red' }, proveedor: 'google', item_id: 'i',
    nombre_remoto: `${estado}.txt`, vigente: { copia: 'nube/copias/x', nombre: `${estado}.txt`, sha256: 'a'.repeat(64),
      tamano: 1000, revision: 'r1', formato_origen: 'txt', formato_exportado: null, importado: '2026-11-15T10:00:00' },
    historial: [], estado, comprobado: '2026-11-15T10:00:00', motivo: null, nueva: null, candidata: null, ...extra });
  assert.equal(estadoVinculo(v('al_dia')).tono, 'ok');
  assert.equal(estadoVinculo(v('nueva')).tono, 'warn');
  assert.equal(estadoVinculo(v('sin_comprobar', { motivo: 'sin red' })).tono, 'muted');
  const candidata = { ...v('x').vigente, revision: 'r2', comparacion: { anterior: { tamano: 1000, sha256: 'a', revision: 'r1',
    modificado: null }, nueva: { tamano: 1200, sha256: 'b', revision: 'r2', modificado: null }, iguales: false,
  lineas: { anadidas: 3, quitadas: 1 } } };
  const html = pintarVinculos({ vinculos: [v('al_dia'), v('nueva', { nueva: { revision: 'r2', tamano: 1200 } }),
    v('sin_comprobar', { motivo: 'No se pudo comprobar si hay una versión nueva: sin red' }),
    v('traida', { estado: 'nueva', candidata })], ocupado: false, onTraer: nada, onAceptar: nada });
  assert.ok(html.includes('Al día'));
  assert.ok(html.includes('Versión nueva'));
  assert.ok(html.includes('No se pudo comprobar'));
  assert.match(html, />Traer y comparar</);
  // Comparación: lo que cambia, y la nueva solo entra con un botón aparte.
  assert.ok(html.includes('+3') && html.includes('−1'));
  assert.match(html, />Usar la versión nueva</);
  sinJerga(html);
});

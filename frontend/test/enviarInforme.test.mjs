import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// 110 T10: la ventana «Enviar por correo», pintada de verdad con React, y su lógica.
const raiz = fileURLToPath(new URL('..', import.meta.url));

async function cargar() {
  const r = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { BotonEnviar, EnviarDesde, VistaPrevia, HistorialEnvios } from './src/features/powerfactory/EnviarInforme';
    export * from './src/features/powerfactory/enviarInformeLogica';
    export const pintarBoton = (p) => renderToStaticMarkup(createElement(BotonEnviar, p));
    export const pintarDesde = (p) => renderToStaticMarkup(createElement(EnviarDesde, p));
    export const pintarPrevia = (p) => renderToStaticMarkup(createElement(VistaPrevia, p));
    export const pintarHistorial = (p) => renderToStaticMarkup(createElement(HistorialEnvios, p));`,
  resolveDir: raiz, loader: 'tsx' }, bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', r.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
  return mod.exports;
}

const nada = () => undefined;
const cuenta = (nombre, visible, extra = {}) => ({ nombre, visible, registrado: true, se_puede_conectar: true,
  motivo: null, permisos: '', conectada: false, cuenta: null, permisos_concedidos: null, puede_publicar: null,
  puede_enviar: null, ...extra });
const sinJerga = (html) => assert.doesNotMatch(html, /RF-\d|109:|110:|CSG_|\.py\b|firma="|sha256/i);

test('110:RF-1 sin cuenta conectada el botón está desactivado y dice por qué, sin fallar', async () => {
  const { motivoSinCuenta, pintarBoton, SIN_CUENTA } = await cargar();
  assert.equal(SIN_CUENTA, 'Sin cuenta conectada: configure config/nube.json');
  const sinRegistro = [cuenta('google', 'Google Drive', { registrado: false, se_puede_conectar: false }),
    cuenta('microsoft', 'OneDrive', { registrado: false, se_puede_conectar: false })];
  assert.equal(motivoSinCuenta(sinRegistro, null), SIN_CUENTA);
  assert.equal(motivoSinCuenta(null, 'No responde'), `${SIN_CUENTA} (No responde)`);
  assert.match(motivoSinCuenta([cuenta('google', 'Google Drive')], null), /Conecte una cuenta/);
  assert.equal(motivoSinCuenta([cuenta('google', 'Google Drive', { conectada: true, cuenta: 'a@b.org' })], null), null);
  const html = pintarBoton({ motivo: SIN_CUENTA, onAbrir: nada });
  assert.match(html, /<button[^>]*disabled=""[^>]*>Enviar por correo</);
  assert.ok(html.includes(SIN_CUENTA));
  assert.match(pintarBoton({ motivo: null, onAbrir: nada }), /<button(?![^>]*disabled)[^>]*>Enviar por correo</);
});

test('110:RF-1 las cuentas para enviar son las conectadas, con su proveedor', async () => {
  const { cuentasDeCorreo } = await cargar();
  assert.deepEqual(cuentasDeCorreo([cuenta('google', 'Google Drive', { conectada: true, cuenta: 'a@b.org',
    puede_enviar: true }), cuenta('microsoft', 'OneDrive')]),
  [{ proveedor: 'google', cuenta: 'a@b.org', etiqueta: 'a@b.org (Google)', puedeEnviar: true }]);
  assert.deepEqual(cuentasDeCorreo(null), []);
});

test('110:RF-1 una cuenta sin el permiso de envío, o sin saberlo, se ofrece a pedirlo; la elegida se busca por su valor', async () => {
  const { cuentasDeCorreo, cuentaElegida } = await cargar();
  const opciones = cuentasDeCorreo([
    cuenta('google', 'Google Drive', { conectada: true, cuenta: 'a@b.org', puede_enviar: false,
      permisos_concedidos: ['drive.file'] }),
    cuenta('microsoft', 'OneDrive', { conectada: true, cuenta: 'c@d.org', puede_enviar: null })]);
  assert.deepEqual(opciones.map((o) => o.puedeEnviar), [false, false]);
  assert.equal(cuentaElegida(opciones, 'microsoft|c@d.org').cuenta, 'c@d.org');
  assert.equal(cuentaElegida(opciones, 'google|otra@b.org'), undefined);
  assert.equal(cuentaElegida(opciones, ''), undefined);
});

test('110:RF-1 «Enviar desde» lista las cuentas de la nube y, si la elegida aún no envía, pide el permiso a esa misma cuenta', async () => {
  const { cuentasDeCorreo, pintarDesde, motivoSinCuenta } = await cargar();
  const opciones = cuentasDeCorreo([
    cuenta('google', 'Google Drive', { conectada: true, cuenta: 'ana@ejemplo.org', puede_enviar: true }),
    cuenta('microsoft', 'OneDrive', { conectada: true, cuenta: 'luis@ejemplo.org', puede_enviar: false })]);
  const lista = pintarDesde({ opciones, valor: 'google|ana@ejemplo.org', onCambio: nada, onPedirPermiso: nada });
  assert.match(lista, /<span>Enviar desde<\/span>/);
  assert.ok(lista.includes('ana@ejemplo.org (Google)') && lista.includes('luis@ejemplo.org (Microsoft)'));
  assert.doesNotMatch(lista, /Dar permiso para enviar/);
  const falta = pintarDesde({ opciones, valor: 'microsoft|luis@ejemplo.org', onCambio: nada, onPedirPermiso: nada });
  assert.match(falta, />Dar permiso para enviar</);
  // No hay un segundo «Conectar» en el correo: sin cuentas, la ventana remite a la nube.
  assert.doesNotMatch(falta, />Conectar</);
  assert.match(motivoSinCuenta([cuenta('google', 'Google Drive')], null), /Cuentas en la nube/);
  sinJerga(falta);
});

test('110:RF-1, RF-4 la petición lleva los campos de la ventana, y cambiar uno anula la vista previa', async () => {
  const { peticionVistaPrevia, mismaPeticion } = await cargar();
  const campos = { cuenta: 'google|a@b.org', para: 'x@y.org; z@y.org', cc: '', cco: 'w@y.org', asunto: 'Informe',
    cuerpo: 'Adjunto.', adjuntar: ['docx', 'pdf'] };
  const p = peticionVistaPrevia(campos, { informe: 'factibilidad.docx', proyecto: 'P1', escenario: null });
  assert.deepEqual(p, { informe: 'factibilidad.docx', proyecto: 'P1', escenario: null, proveedor: 'google',
    cuenta: 'a@b.org', para: ['x@y.org', 'z@y.org'], cc: [], cco: ['w@y.org'], asunto: 'Informe', cuerpo: 'Adjunto.',
    adjuntar: ['docx', 'pdf'], origen: 'web' });
  assert.equal(mismaPeticion(p, peticionVistaPrevia(campos, { informe: 'factibilidad.docx', proyecto: 'P1', escenario: null })), true);
  assert.equal(mismaPeticion(p, peticionVistaPrevia({ ...campos, para: 'x@y.org' },
    { informe: 'factibilidad.docx', proyecto: 'P1', escenario: null })), false);
  assert.throws(() => peticionVistaPrevia({ ...campos, para: '' }, { informe: 'f.docx' }), /destinatario/);
  assert.throws(() => peticionVistaPrevia({ ...campos, para: 'mal@' }, { informe: 'f.docx' }), /mal@/);
  assert.throws(() => peticionVistaPrevia({ ...campos, cuenta: '' }, { informe: 'f.docx' }), /cuenta/);
});

const PREVIA = { borrador: '0'.repeat(32), firma: 'f'.repeat(64), cuenta: 'a@b.org', proveedor: 'google',
  para: ['x@y.org', 'jaun@empresa.pe'], cc: [], cco: [], asunto: 'Factibilidad CA101', cuerpo: 'Adjunto el informe.',
  enlace: null, adjuntos: [{ nombre: 'factibilidad.docx', tamano: 52000, sha256: 'a'.repeat(64) },
    { nombre: 'factibilidad.pdf', tamano: 1048576, sha256: 'b'.repeat(64) }],
  validez: { valido: true, motivo: '' }, avisos: {}, limite_bytes: 26214400, excede_limite: false, confirmado: false,
  ventana: '/espacios/x/correo/0' };

test('110:RF-1, RF-3 la vista previa enseña para quién, el asunto, el cuerpo y los adjuntos con su tamaño', async () => {
  const { pintarPrevia } = await cargar();
  const html = pintarPrevia({ previa: PREVIA, ocupado: false, onConfirmar: nada });
  for (const t of ['x@y.org', 'Factibilidad CA101', 'Adjunto el informe.', 'factibilidad.docx', 'factibilidad.pdf', '1.0 MB'])
    assert.ok(html.includes(t), t);
  assert.match(html, /<button(?![^>]*disabled)[^>]*>Confirmar y enviar</);
  sinJerga(html);
});

test('110:RF-12 un estudio no válido se dice en la ventana y no se presenta como válido', async () => {
  const { pintarPrevia } = await cargar();
  const html = pintarPrevia({ previa: { ...PREVIA, validez: { valido: false, motivo: 'el estudio no terminó' } },
    ocupado: false, onConfirmar: nada });
  assert.ok(html.includes('No válido como estudio: el estudio no terminó'));
  assert.match(html, /alert-warn/);
});

test('110:RF-14 una dirección no habitual lleva su aviso y la sugerencia, sin bloquear el envío', async () => {
  const { pintarPrevia } = await cargar();
  const html = pintarPrevia({ previa: { ...PREVIA, avisos: { 'jaun@empresa.pe':
    { aviso: 'No es un contacto habitual de este espacio.', sugerencia: 'juan@empresa.pe' } } }, ocupado: false, onConfirmar: nada });
  assert.ok(html.includes('No es un contacto habitual de este espacio.'));
  assert.ok(html.includes('¿Quiso decir juan@empresa.pe?'));
  assert.match(html, /<button(?![^>]*disabled)[^>]*>Confirmar y enviar</);
});

test('110:RF-5, RF-7 «Confirmar y enviar» se desactiva mientras el envío corre (sin doble envío)', async () => {
  const { pintarPrevia } = await cargar();
  assert.match(pintarPrevia({ previa: PREVIA, ocupado: true, onConfirmar: nada }),
    /<button[^>]*disabled=""[^>]*>Confirmar y enviar</);
});

test('110:RF-10 un adjunto por encima del límite lo dice y propone el enlace', async () => {
  const { pintarPrevia } = await cargar();
  const html = pintarPrevia({ previa: { ...PREVIA, excede_limite: true, limite_bytes: 3145728 }, ocupado: false,
    onConfirmar: nada });
  assert.ok(html.includes('3.0 MB'));
  assert.match(html, /enlace/);
});

test('110:RF-8, RF-9, RF-13 el historial dice el estado de cada envío y un desconocido se resuelve con «Llegó» o «No llegó»', async () => {
  const { pintarHistorial, textoEstado } = await cargar();
  assert.equal(textoEstado('aceptado').tono, 'ok');
  assert.equal(textoEstado('rechazado').tono, 'error');
  assert.match(textoEstado('desconocido').texto, /Enviados/);
  assert.equal(textoEstado('enviando').tono, 'info');
  const envio = (clave, estado, extra = {}) => ({ clave, estado, hora: '2026-11-15T10:00:00', cuenta: 'a@b.org',
    destinatarios: { para: ['x@y.org'], cc: [], cco: [] }, motivo: '', resolucion: null, intento: 1, ...extra });
  const html = pintarHistorial({ envios: [envio('1'.repeat(64), 'aceptado'), envio('2'.repeat(64), 'desconocido'),
    envio('3'.repeat(64), 'rechazado', { motivo: 'La cuenta se desconectó: vuelva a conectarla.' })],
  ocupado: false, onResolver: nada });
  assert.ok(html.includes('x@y.org'));
  assert.ok(html.includes('La cuenta se desconectó: vuelva a conectarla.'));
  assert.equal((html.match(/>Llegó</g) ?? []).length, 1);
  assert.equal((html.match(/>No llegó</g) ?? []).length, 1);
  assert.ok(pintarHistorial({ envios: [], ocupado: false, onResolver: nada }).includes('Sin envíos'));
  sinJerga(html);
});

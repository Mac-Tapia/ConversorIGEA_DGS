/**
 * 109 T19 (SELECTOR-UNICO; 109:RF-21 a RF-23): cada entrada tiene un solo campo «Elegir archivo» con su origen. En la
 * web con la nube simulada (tests/e2e_web_nube_simulada.py, puerto siguiente): sin cuenta, solo el equipo; con Google
 * Drive y OneDrive conectados, sus botones en el mismo campo, y lo elegido allí entra en la casilla como una subida.
 * Un fichero de otro tipo no entra y se dice cuál y qué admite. La página del selector del proveedor la sirve el propio
 * recorrido (devuelve los ids por postMessage, como el selector real): nada sale de la máquina.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { captura, expect, revisarAxe, sinRedNiErrores, test } from './comun.mjs';
import { carpetaNubeE2E, puertoNubeE2E } from './entorno.mjs';

const FLUJO = 'f05_selector_unico';
const BASE = `http://127.0.0.1:${puertoNubeE2E()}`;
const token = () => JSON.parse(readFileSync(join(carpetaNubeE2E(), 'sesiones', `${puertoNubeE2E()}.json`), 'utf8')).token;

test.use({ baseURL: BASE });

/** La web con la nube simulada, en un espacio nuevo (la fixture `web` de comun.mjs abre la de los demás recorridos). */
async function abrir(page) {
  await page.goto(`/?acceso=${encodeURIComponent(token())}`);
  await expect(page.getByRole('heading', { name: 'ConverterSmartGrid', level: 1 })).toBeVisible({ timeout: 60_000 });
  const antes = await page.locator('.ws-id span[title]').getAttribute('title');
  await page.getByRole('button', { name: 'Nuevo espacio' }).click();
  const dialogo = page.getByRole('dialog').filter({ hasText: 'Nuevo espacio de trabajo' });
  await dialogo.getByRole('button', { name: 'Crear' }).click();
  await expect(dialogo).toBeHidden();
  await expect(page.locator('.ws-id span[title]')).not.toHaveAttribute('title', antes ?? '');
  await tresTxt(page);
  return page.locator('.ws-id span[title]').getAttribute('title');
}

/** La alternativa «TXT», cuyas casillas usa el recorrido. */
async function tresTxt(page) {
  const opcion = page.getByRole('radiogroup', { name: 'Alternativa de entrada' }).getByRole('radio', { name: 'TXT', exact: true });
  await opcion.click();
  await expect(opcion).toHaveAttribute('aria-checked', 'true');
}

/** Conecta la cuenta como lo haría el operador: el proveedor (simulado) autoriza y la web vuelve por /nube/retorno. */
async function conectar(page, wid, proveedor) {
  const { url } = await post(page, `/api/workspaces/${wid}/nube/${proveedor}/conectar`, {});
  const params = await post(page, '/__sim/autorizar', { url });
  await page.goto(`/nube/retorno?${new URLSearchParams(params)}`);
  await expect(page.getByRole('heading', { name: 'ConverterSmartGrid', level: 1 })).toBeVisible({ timeout: 60_000 });
  await tresTxt(page);
}

/** La página del selector del proveedor: devuelve los ids elegidos a la web, como la real, y se cierra. */
async function selectorQueElige(context, proveedor, ids) {
  await context.route(`**/nube/selector/${proveedor}**`, (ruta) => ruta.fulfill({
    contentType: 'text/html; charset=utf-8',
    body: `<!doctype html><title>Selector</title><script>
      window.opener.postMessage({ tipo: 'csg-nube-seleccion', proveedor: '${proveedor}', modo: 'ficheros',
        ids: ${JSON.stringify(ids)} }, location.origin);
      setTimeout(() => window.close(), 100);</script>`,
  }));
}

/** Un POST desde la propia página, con su Origin y su cookie, como lo haría la web. Devuelve el JSON. */
async function post(page, ruta, datos) {
  const r = await page.evaluate(async ([u, d]) => {
    const res = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) });
    return { ok: res.ok, texto: await res.text() };
  }, [ruta, datos]);
  expect(r.ok, `${ruta}: ${r.texto}`).toBeTruthy();
  return JSON.parse(r.texto);
}

/**
 * La casilla comprueba lo que entra igual venga de donde venga (RF-4, RF-22): si el fichero no encaja con ella, pregunta
 * antes de reemplazar el que había. El recorrido lo acepta, como el operador.
 */
async function usarloSiPregunta(page) {
  const dialogo = page.getByRole('dialog').filter({ hasText: 'El fichero no encaja con la casilla' });
  try {
    await dialogo.waitFor({ state: 'visible', timeout: 15_000 });
  } catch {
    return;
  }
  await dialogo.getByRole('button', { name: 'Usarlo igualmente' }).click();
  await expect(dialogo).toBeHidden();
}

const casilla = (page, etiqueta) => page.locator('.slot').filter({ hasText: etiqueta });

test('109:RF-21 a RF-23 un campo por entrada: equipo, Google Drive y OneDrive, con el filtro de su tipo', async (
  { page, context, externas, errores }, testInfo) => {
  const wid = await abrir(page);
  const red = casilla(page, 'RED — topología');
  const carga = casilla(page, 'CARGA — demanda por cliente');

  // Sin cuenta: el campo es el del equipo, sin botones de la nube (RF-21).
  await expect(red.getByText('Soltar el fichero o')).toBeVisible();
  await expect(red.getByRole('button', { name: 'Google Drive' })).toHaveCount(0);

  // Equipo: un tipo que no admite la entrada no entra y se dice (RF-23); el suyo, sí.
  await red.locator('input[type=file]').setInputFiles({ name: 'acta.pdf', mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4') });
  await expect(red.getByRole('alert')).toContainText('«acta.pdf» no vale aquí: admite');
  await red.locator('input[type=file]').setInputFiles({ name: 'RED_equipo.txt', mimeType: 'text/plain',
    buffer: Buffer.from('RED de prueba\n') });
  await expect(red.locator('.slot-name')).toHaveText('RED_equipo.txt');
  await expect(red.getByRole('alert')).toHaveCount(0);
  await captura(page, FLUJO, '1-equipo');

  // Con las dos cuentas conectadas, sus botones salen en el mismo campo de cada entrada (RF-21).
  await conectar(page, wid, 'google');
  await conectar(page, wid, 'microsoft');
  await expect(red.getByRole('group', { name: 'Elegir de la nube' })).toBeVisible();
  await expect(red.getByRole('button', { name: 'Google Drive' })).toBeVisible();
  await expect(red.getByRole('button', { name: 'OneDrive' })).toBeVisible();

  // Google Drive: lo elegido llega como copia fija y entra en la casilla como una subida (RF-22).
  const deDrive = (await post(page, '/__sim/crear', { proveedor: 'google',
    nombre: 'RED_drive.txt', contenido: 'RED desde Drive\n' })).id;
  await selectorQueElige(context, 'google', [deDrive]);
  await red.getByRole('button', { name: 'Google Drive' }).click();
  await usarloSiPregunta(page);
  await expect(red.locator('.slot-name')).toHaveText('RED_drive.txt', { timeout: 60_000 });

  // OneDrive, en otra entrada.
  const deOneDrive = (await post(page, '/__sim/crear', { proveedor: 'microsoft',
    nombre: 'CARGA_onedrive.txt', contenido: 'CARGA desde OneDrive\n' })).id;
  await selectorQueElige(context, 'microsoft', [deOneDrive]);
  await carga.getByRole('button', { name: 'OneDrive' }).click();
  await usarloSiPregunta(page);
  await expect(carga.locator('.slot-name')).toHaveText('CARGA_onedrive.txt', { timeout: 60_000 });

  // Un fichero de la nube de otro tipo tampoco entra (RF-23).
  const pdf = (await post(page, '/__sim/crear', { proveedor: 'google', nombre: 'plano.pdf',
    contenido: '%PDF-1.4' })).id;
  await selectorQueElige(context, 'google', [pdf]);
  await red.getByRole('button', { name: 'Google Drive' }).click();
  await expect(red.getByRole('alert')).toContainText('«plano.pdf» no vale aquí', { timeout: 60_000 });
  await expect(red.locator('.slot-name')).toHaveText('RED_drive.txt');

  await captura(page, FLUJO, '2-nube');
  await revisarAxe(page, FLUJO, 'campo-unico', testInfo);
  sinRedNiErrores(externas, errores);
});

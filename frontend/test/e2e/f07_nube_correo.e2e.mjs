/**
 * 109 T16: el recorrido de Nube y Correo en el navegador real, con el proveedor simulado y en modo claro y oscuro
 * (109:RF-1, 109:RF-2, 109:RF-14, 109:RF-19; 110:RF-2).
 *
 * - En la web de los demás recorridos, sin `config/nube.json` (la configuración la apunta a un fichero que no existe):
 *   la tarjeta «Cuentas en la nube» dice «Sin cuenta conectada: configure config/nube.json» y no ofrece conectar
 *   (109:RF-19); la web no falla.
 * - En la web con la nube simulada (tests/e2e_web_nube_simulada.py, puerto siguiente): conectar Google Drive con el
 *   permiso de leer y OneDrive con el de enviar correo; cada cuenta dice lo que permite («Archivos: leer · Correo: …»,
 *   109:RF-1 y 110:RF-2, la misma cuenta da los archivos y el correo); las herramientas de la nube salen en la tarjeta;
 *   ningún token queda en el navegador (109:RF-2); desconectar pide confirmación y deja la otra cuenta (109:RF-14).
 *
 * En cada estado: axe sin infracciones graves, ninguna cita a requisitos ni a tareas y ningún plural con «(s)» a la
 * vista, y ninguna petición fuera de la máquina: la nube es la simulada, en memoria, y nada se escribe en un Google
 * Drive ni un OneDrive reales. El teclado solo abre y cierra un diálogo con Intro y Escape: no se tabula.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { captura, espacioNuevo, expect, revisarAxe, sinRedNiErrores, test } from './comun.mjs';
import { carpetaNubeE2E, puertoNubeE2E } from './entorno.mjs';

const FLUJO = 'f07_nube_correo';
const BASE_NUBE = `http://127.0.0.1:${puertoNubeE2E()}`;
const tokenNube = () => JSON.parse(readFileSync(join(carpetaNubeE2E(), 'sesiones', `${puertoNubeE2E()}.json`), 'utf8')).token;

/** El texto de la web sin aplicación registrada (frontend/src/api/nube.ts, SIN_CUENTA). */
const SIN_CUENTA = 'Sin cuenta conectada: configure config/nube.json';
/** Un plural escrito «alimentador(es)» o «fichero(s)»: la web escribe el número y la palabra que le toca. */
const PLURAL_ENTRE_PARENTESIS = /\p{L}\((?:s|es)\)/gu;
/** Lo que nunca debe quedar en el navegador: los tokens del simulado y los nombres de sus campos (109:RF-2). */
const CREDENCIAL = /\b(?:acc|ref)-(?:google|microsoft)-\d+|access_token|refresh_token|client_secret|code_verifier/;

const TEMAS = [['claro', 'light'], ['oscuro', 'dark']];

const tarjeta = (page) => page.getByRole('region', { name: 'Cuentas en la nube', exact: true });

/** El modo de color que pidió el recorrido es el que pinta la web (tokens de styles.css). */
async function enModo(page, esquema) {
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe(esquema);
}

/** Ningún «(s)» a la vista, en ningún estado del recorrido. */
async function sinPluralesEntreParentesis(page, donde) {
  const texto = await page.evaluate(() => document.body.innerText);
  expect([...new Set(texto.match(PLURAL_ENTRE_PARENTESIS) ?? [])], `plurales con «(s)» a la vista en ${donde}`).toEqual([]);
}

/** 109:RF-2: ni localStorage, ni sessionStorage, ni las cookies que ve la página guardan credenciales del proveedor. */
async function sinCredencialesEnElNavegador(page) {
  const guardado = await page.evaluate(() => {
    const leer = (almacen) => {
      try {
        return Object.keys(almacen).map((k) => `${k}=${almacen.getItem(k)}`);
      } catch {
        return [];
      }
    };
    return [...leer(window.localStorage), ...leer(window.sessionStorage), document.cookie];
  });
  expect(guardado.filter((v) => CREDENCIAL.test(v)), 'credenciales en el navegador').toEqual([]);
}

/** La web con la nube simulada, en un espacio nuevo; devuelve su id. */
async function abrirNube(page) {
  await page.goto(`/?acceso=${encodeURIComponent(tokenNube())}`);
  await expect(page.getByRole('heading', { name: 'ConverterSmartGrid', level: 1 })).toBeVisible({ timeout: 60_000 });
  await espacioNuevo(page);
  return page.locator('.ws-id span[title]').getAttribute('title');
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
 * Conecta la cuenta como el operador (como en f05): el proveedor simulado consiente y la web vuelve por /nube/retorno.
 * Con `alcance` («enviar»), la cuenta se conecta para el correo.
 */
async function conectar(page, wid, proveedor, alcance) {
  const { url } = await post(page, `/api/workspaces/${wid}/nube/${proveedor}/conectar`, alcance ? { alcance } : {});
  const params = await post(page, '/__sim/autorizar', { url });
  await page.goto(`/nube/retorno?${new URLSearchParams(params)}`);
  await expect(page.getByRole('heading', { name: 'ConverterSmartGrid', level: 1 })).toBeVisible({ timeout: 60_000 });
}

/** La fila de una cuenta conectada, por su botón de desconectar. */
const filaConectada = (page, visible) => tarjeta(page).getByRole('listitem')
  .filter({ has: page.getByRole('button', { name: `Desconectar ${visible}`, exact: true }) });

for (const [tema, esquema] of TEMAS) {
  test.describe(`[${tema}]`, () => {
    test.use({ colorScheme: esquema });

    test(`109:RF-19 [${tema}] sin config/nube.json la tarjeta dice que no hay cuenta y no ofrece conectar`, async (
      { web: page, externas, errores }, testInfo) => {
      await enModo(page, esquema);
      const cuentas = tarjeta(page);
      await expect(cuentas).toBeVisible();
      await expect(cuentas.getByText(SIN_CUENTA, { exact: true })).toBeVisible();
      await expect(cuentas.getByRole('button', { name: 'Conectar Google Drive', exact: true })).toHaveCount(0);
      await expect(cuentas.getByRole('button', { name: 'Conectar OneDrive', exact: true })).toHaveCount(0);
      // Lo local sigue: las entradas se ven y la página no deja errores (sinRedNiErrores).
      await expect(page.getByRole('radiogroup', { name: 'Alternativa de entrada', exact: true })).toBeVisible();

      await captura(page, FLUJO, `1-sin-cuenta-${tema}`);
      await revisarAxe(page, FLUJO, `sin-cuenta-${tema}`, testInfo);
      await sinPluralesEntreParentesis(page, `sin cuenta (${tema})`);
      await sinCredencialesEnElNavegador(page);
      sinRedNiErrores(externas, errores);
    });

    test.describe('con la nube simulada', () => {
      test.use({ baseURL: BASE_NUBE });

      test(`109:RF-1, RF-2 y RF-14, 110:RF-2 [${tema}] conectar para leer y para el correo, y desconectar`, async (
        { page, externas, errores }, testInfo) => {
        const wid = await abrirNube(page);
        await enModo(page, esquema);
        const cuentas = tarjeta(page);

        // Registradas en el equipo y sin conectar: se ofrece conectar cada una, y no se dice que falte el registro.
        await expect(cuentas.getByRole('button', { name: 'Conectar Google Drive', exact: true })).toBeVisible();
        await expect(cuentas.getByRole('button', { name: 'Conectar OneDrive', exact: true })).toBeVisible();
        await expect(cuentas.getByText(SIN_CUENTA, { exact: true })).toHaveCount(0);
        await revisarAxe(page, FLUJO, `sin-conectar-${tema}`, testInfo);

        // Google Drive para leer (109:RF-1): vuelve conectado, con su cuenta y sin permiso de correo. En Google, leer y
        // publicar piden el mismo permiso (drive.file, oauth.py): la cuenta dice que publica.
        await conectar(page, wid, 'google');
        await expect(cuentas.getByText('Google Drive conectado.', { exact: true })).toBeVisible();
        const google = filaConectada(page, 'Google Drive');
        await expect(google).toContainText('operador@ejemplo.org');
        await expect(google).toContainText('Archivos: leer y publicar · Correo: no');

        // OneDrive para el correo (110:RF-2: solo el permiso de enviar): la misma cuenta dice lo que permite.
        await conectar(page, wid, 'microsoft', 'enviar');
        await expect(cuentas.getByText('OneDrive conectado.', { exact: true })).toBeVisible();
        const onedrive = filaConectada(page, 'OneDrive');
        await expect(onedrive).toContainText('operador@ejemplo.org');
        await expect(onedrive).toContainText('Archivos: leer · Correo: enviar');
        await expect(google).toContainText('Archivos: leer y publicar · Correo: no');

        // Con cuentas conectadas, las herramientas de la nube salen en la tarjeta.
        for (const nombre of ['Importar', 'Versiones', 'Publicar']) {
          await expect(cuentas.getByRole('button', { name: nombre, exact: true })).toBeVisible();
        }
        await captura(page, FLUJO, `2-conectadas-${tema}`);
        await revisarAxe(page, FLUJO, `conectadas-${tema}`, testInfo);
        await sinPluralesEntreParentesis(page, `cuentas conectadas (${tema})`);
        // 109:RF-2: los tokens se quedan en el cofre del servidor; nada en el navegador.
        await sinCredencialesEnElNavegador(page);

        // «Importar», con el teclado: Intro lo abre y Escape lo cierra, sin elegir nada (nada se descarga).
        await cuentas.getByRole('button', { name: 'Importar', exact: true }).focus();
        await page.keyboard.press('Enter');
        const importar = page.getByRole('dialog').filter({ hasText: 'Importar de la nube' });
        await expect(importar).toBeVisible();
        await expect(importar.getByRole('button', { name: 'Elegir fichero', exact: true })).toBeVisible();
        await captura(page, FLUJO, `3-importar-${tema}`);
        await revisarAxe(page, FLUJO, `importar-${tema}`, testInfo);
        await sinPluralesEntreParentesis(page, `importar (${tema})`);
        await page.keyboard.press('Escape');
        await expect(importar).toBeHidden();

        // Desconectar pide confirmación, conserva lo importado y deja la otra cuenta (109:RF-14).
        await cuentas.getByRole('button', { name: 'Desconectar OneDrive', exact: true }).click();
        const confirmar = page.getByRole('dialog').filter({ hasText: 'Las copias ya importadas y los recibos se conservan.' });
        await expect(confirmar).toBeVisible();
        await revisarAxe(page, FLUJO, `desconectar-${tema}`, testInfo);
        await confirmar.getByRole('button', { name: 'Desconectar', exact: true }).click();
        await expect(confirmar).toBeHidden();
        await expect(cuentas.getByRole('button', { name: 'Conectar OneDrive', exact: true })).toBeVisible();
        await expect(cuentas.getByRole('button', { name: 'Desconectar Google Drive', exact: true })).toBeVisible();

        await captura(page, FLUJO, `4-desconectada-${tema}`);
        await revisarAxe(page, FLUJO, `desconectada-${tema}`, testInfo);
        await sinPluralesEntreParentesis(page, `desconectada (${tema})`);
        await sinCredencialesEnElNavegador(page);
        sinRedNiErrores(externas, errores);
      });
    });
  });
}

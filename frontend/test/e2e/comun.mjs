/**
 * Base de los recorridos E2E (Plan Maestro V1, F-12): entrar en la web aislada con el token de su sesión, cortar
 * toda salida a la red, revisar con axe-core y guardar capturas y resultados por SHA.
 */
import { test as base, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { evidenciaDe, puertoE2E } from './entorno.mjs';

const FRONT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PUERTO = puertoE2E();
const CARPETA = process.env.CSG_E2E_DIR || join(tmpdir(), `csg-e2e-${PUERTO}`);
export const EVIDENCIA = evidenciaDe(FRONT);

/** WCAG 2.0, 2.1 y 2.2, niveles A y AA: lo que axe sabe comprobar de forma automática. */
export const ETIQUETAS_WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const GRAVES = new Set(['serious', 'critical']);

const LOCALES = new Set(['127.0.0.1', 'localhost', '[::1]']);

/** El token de la sesión que el lanzador dejó para este puerto (086:RF-19). */
function token() {
  const ruta = join(CARPETA, 'sesiones', `${PUERTO}.json`);
  let datos;
  try {
    datos = JSON.parse(readFileSync(ruta, 'utf8'));
  } catch (e) {
    throw new Error(`No se puede leer la sesión de la web de prueba (${ruta}): ${e.message}`);
  }
  if (typeof datos?.token !== 'string' || !datos.token) throw new Error(`La sesión ${ruta} no tiene token.`);
  return datos.token;
}

export const test = base.extend({
  /** Las peticiones que salían de la máquina y se cortaron: un recorrido correcto no hace ninguna. */
  externas: async ({ context }, use) => {
    const cortadas = [];
    await context.route('**/*', (ruta) => {
      const url = new URL(ruta.request().url());
      if (['data:', 'blob:'].includes(url.protocol) || LOCALES.has(url.hostname)) return ruta.continue();
      cortadas.push(url.href);
      return ruta.abort('internetdisconnected');
    });
    await use(cortadas);
  },
  /** Errores de la consola y de la página: un recorrido correcto no deja ninguno. */
  errores: async ({ page }, use) => {
    const lista = [];
    page.on('pageerror', (e) => lista.push(`pageerror: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') lista.push(`console: ${m.text()}`); });
    await use(lista);
  },
  /** La web abierta con la cookie de la sesión, en un espacio nuevo para no heredar nada de otro recorrido. */
  web: async ({ page, externas, errores }, use) => {
    void externas; void errores;
    await page.goto(`/?acceso=${encodeURIComponent(token())}`);
    await expect(page.getByRole('heading', { name: 'ConverterSmartGrid', level: 1 })).toBeVisible({ timeout: 60_000 });
    await espacioNuevo(page);
    await use(page);
  },
});

export { expect };

/** Crea un espacio de trabajo vacío con el botón de la cabecera y su confirmación, como lo haría el operador. */
export async function espacioNuevo(page) {
  const antes = await page.locator('.ws-id span[title]').getAttribute('title');
  await page.getByRole('button', { name: 'Nuevo espacio' }).click();
  // Por el texto y no por el nombre: el Modal de shared/ui.tsx aún no enlaza su título (pendiente anotado en T0c).
  const dialogo = page.getByRole('dialog').filter({ hasText: 'Nuevo espacio de trabajo' });
  await expect(dialogo).toBeVisible();
  await dialogo.getByRole('button', { name: 'Crear' }).click();
  await expect(dialogo).toBeHidden();
  await expect(page.locator('.ws-id span[title]')).not.toHaveAttribute('title', antes ?? '');
}

/** Carpeta de la evidencia de un flujo, dentro de la de su SHA. */
export function carpetaDe(flujo) {
  const dir = join(EVIDENCIA, flujo);
  mkdirSync(dir, { recursive: true });
  return dir;
}

/** Captura de pantalla con nombre: la revisión manual de la tarea mira estas. */
export async function captura(page, flujo, nombre) {
  const ruta = join(carpetaDe(flujo), `${nombre}.png`);
  await page.screenshot({ path: ruta, fullPage: true });
  return ruta;
}

/**
 * axe-core sobre la página tal como está, con las reglas de WCAG 2.2 AA. Guarda todas las infracciones (también las
 * leves, para la revisión) y falla con las graves y las críticas, nombrando la regla y cuántos nodos la incumplen.
 */
export async function revisarAxe(page, flujo, nombre, testInfo) {
  const r = await new AxeBuilder({ page }).withTags(ETIQUETAS_WCAG).analyze();
  const resumen = r.violations.map((v) => ({ id: v.id, impacto: v.impact, ayuda: v.help, url: v.helpUrl,
    nodos: v.nodes.map((n) => ({ destino: n.target.join(' '), resumen: n.failureSummary })) }));
  const ruta = join(carpetaDe(flujo), `axe-${nombre}.json`);
  writeFileSync(ruta, JSON.stringify({ url: page.url(), motor: r.testEngine, infracciones: resumen,
    aprobadas: r.passes.length, incompletas: r.incomplete.length }, null, 2));
  await testInfo.attach(`axe-${nombre}`, { path: ruta, contentType: 'application/json' });
  const graves = resumen.filter((v) => GRAVES.has(v.impacto)).map((v) => `${v.id} (${v.impacto}, ${v.nodos.length} nodos): ${v.ayuda}`);
  expect(graves, `axe en ${flujo}/${nombre}: ${ruta}`).toEqual([]);
}

/** Al terminar un recorrido: sin salidas a la red y sin errores en la consola. */
export function sinRedNiErrores(externas, errores) {
  expect(externas, 'peticiones que salían de la máquina').toEqual([]);
  expect(errores, 'errores de la página o de la consola').toEqual([]);
}

/** Pulsa Tab hasta que el foco llegue a lo que cumple ``cumple`` (o falla tras ``max`` pulsaciones). */
export async function tabularHasta(page, cumple, max = 80) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab');
    if (await page.evaluate(cumple)) return i + 1;
  }
  throw new Error(`El foco no llegó con ${max} pulsaciones de Tab.`);
}

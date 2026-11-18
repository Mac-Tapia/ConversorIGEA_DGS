/**
 * 111 T20 a T22 (RF-20 a RF-22) — el espacio de ingeniería en navegador real, sobre el espacio sintético sorteado de
 * `preparar.mjs` (la semilla sale en el registro), en claro y en oscuro (los dos proyectos de la configuración).
 *
 * T20 (RF-20): seleccionar en la tabla, en el plano y en el inspector; las otras vistas lo siguen, el plano lo resalta
 *   y lo encuadra entero, y Escape quita la selección en todas.
 * T21 (RF-21): un hallazgo de tensión y uno de sobrecarga (con un perfil de umbrales estrechos cargado desde la web)
 *   llevan al elemento en el plano y al inspector con su valor, umbral, norma (la que da el servidor desde la biblioteca;
 *   la que falta, con su motivo), caso y motor.
 * T22 (RF-22): plano, tabla e inspector a la vez en 1366×900 y 1920×1080; los separadores se mueven con el teclado y el
 *   reparto se recuerda al volver a abrir el espacio; ninguna vista se quita.
 * axe sin infracciones graves ni críticas en cada estado; el marco del plano (sandbox sin origen) queda fuera de axe.
 */
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { comprobar_sin_citas, expect, test, type Page } from './sin_red';

// Las variables globales del guion del marco del plano (adaptadores/pagina_plano.py), leídas desde `evaluate`.
/* eslint-disable @typescript-eslint/no-explicit-any */
declare const map: any;
declare const porCodigo: Record<string, any> | undefined;
declare const resaltado: unknown;
/* eslint-enable @typescript-eslint/no-explicit-any */

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
type Loc = import('@playwright/test').Locator;

async function api<T>(page: Page, ruta: string, init?: { method?: string; data?: unknown }): Promise<T> {
  const url = `${process.env.CSG_E2E_BASE}/api/workspaces/${encodeURIComponent(process.env.CSG_E2E_ESPACIO!)}${ruta}`;
  const r = init?.method === 'POST' ? await page.request.post(url, { data: init.data }) : await page.request.get(url);
  expect(r.ok(), `${ruta}: ${r.status()}`).toBeTruthy();
  return (await r.json()) as T;
}

async function sinInfraccionesGraves(page: Page, estado: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(WCAG).exclude('iframe.map-frame').analyze();
  const graves = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id);
  expect(graves, `axe en «${estado}»`).toEqual([]);
}

async function tabularHasta(page: Page, destino: Loc, max = 120): Promise<void> {
  for (let i = 0; i < max; i++) {
    if (await destino.evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  throw new Error('el foco no llegó a su destino con Tab');
}

/** Si al cargar la web enseña el diálogo de la conversión que preparó el espacio (según cuándo terminó), el operador lo
 *  cierra con el teclado antes de seguir: con él abierto el foco no sale del diálogo. */
async function cerrarDialogo(page: Page): Promise<void> {
  const dialogo = page.getByRole('dialog');
  if (!(await dialogo.isVisible())) return;
  await page.keyboard.press('Escape');
  if (await dialogo.isVisible()) await dialogo.getByRole('button', { name: 'Cerrar' }).press('Enter');
  await expect(dialogo).toBeHidden();
}

async function abrirPestana(page: Page): Promise<Loc> {
  await page.goto(process.env.CSG_E2E_ENTRADA!, { waitUntil: 'networkidle' });
  await cerrarDialogo(page);
  // Como el operador: las pestañas tienen foco itinerante (F-11, patrón WAI-ARIA): un solo Tab llega a la activa y
  // las flechas mueven el foco a las demás; Intro abre.
  const lista = page.getByRole('tablist', { name: 'Módulos' });
  const pestana = lista.getByRole('tab', { name: 'Plano de la red' });
  await tabularHasta(page, lista.locator('[role="tab"][tabindex="0"]'));
  const total = await lista.getByRole('tab').count();
  for (let i = 0; i < total && !(await pestana.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press('ArrowRight');
  }
  await expect(pestana, 'las flechas no llevan el foco a «Plano de la red»').toBeFocused();
  await page.keyboard.press('Enter');
  // La región del plano (su section aria-labelledby), única: «section.card» con ese título casaba también con el
  // contenedor de las pestañas, que lo contiene.
  const seccion = page.getByRole('region', { name: 'Plano de la red' });
  await expect(seccion).toBeVisible();
  // La página del plano avisa «listo» a la pestaña; hasta entonces no se le puede hablar.
  await expect.poll(async () => page.frameLocator('iframe.map-frame').locator('#mapa').count()).toBe(1);
  return seccion;
}

/** Lo que tiene resaltado y encuadrado la página del plano, leído dentro de su marco. */
async function estadoDelPlano(page: Page, codigo: string) {
  const marco = page.frames().find((f) => f.url().includes('/plano/pagina'));
  expect(marco, 'el marco del plano').toBeTruthy();
  // El guion del marco declara «const map», «const porCodigo» y «let resaltado»: viven en su ámbito global, pero no
  // son propiedades de globalThis (con «globalThis.map» la prueba leía siempre false). La función se compila en ese
  // ámbito, así que se nombran tal cual.
  return marco!.evaluate((c) => {
    const tabla = typeof porCodigo === 'undefined' ? undefined : porCodigo;
    const mapa = typeof map === 'undefined' ? undefined : map;
    const capa = tabla?.[c];
    const visible = capa && mapa ? (capa.getBounds ? mapa.getBounds().contains(capa.getBounds()) : mapa.getBounds().contains(capa.getLatLng())) : false;
    return { resaltado: typeof resaltado !== 'undefined' && resaltado === capa && Boolean(capa), visible };
  }, codigo);
}

test.describe.configure({ mode: 'serial' });

test('111 T20 — la selección enlazada entre la tabla, el plano y el inspector, con encuadre, y Escape la quita', async ({ page }, info) => {
  test.setTimeout(300_000);
  console.log(`[111 T20] semilla ${process.env.CSG_E2E_SEMILLA} · ${info.project.name}`);
  const seccion = await abrirPestana(page);
  const tabla = seccion.getByRole('grid', { name: 'Elementos del alimentador' });
  const inspector = seccion.locator('.plano-espacio-inspector');

  // Desde la tabla, con el teclado: el foco en la tabla, una fila con las flechas e Intro.
  await tabularHasta(page, tabla);
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  const filaElegida = tabla.locator('tr[aria-selected="true"]');
  await expect(filaElegida).toHaveCount(1);
  const codigo = (await filaElegida.locator('td').first().innerText()).trim();
  await expect(inspector).toContainText(codigo);
  await expect.poll(() => estadoDelPlano(page, codigo)).toEqual({ resaltado: true, visible: true });
  await sinInfraccionesGraves(page, 'selección desde la tabla');

  // Desde el inspector: el nodo «hasta» de un tramo se selecciona desde él, y la tabla y el plano lo siguen.
  const nodo = inspector.getByRole('button').filter({ hasNotText: 'Quitar la selección' }).last();
  if (await nodo.count()) {
    const otro = (await nodo.innerText()).trim();
    await tabularHasta(page, nodo);
    await page.keyboard.press('Enter');
    await expect(tabla.locator('tr[aria-selected="true"]')).toContainText(otro);
    await expect.poll(() => estadoDelPlano(page, otro)).toEqual({ resaltado: true, visible: true });
  }

  // Desde el plano: tocar un trazo en el marco lo selecciona en la tabla y el inspector, y el plano lo encuadra.
  const enPlano = await page.frames().find((f) => f.url().includes('/plano/pagina'))!.evaluate(() => {
    const p = porCodigo ?? {};                                      // la del guion del marco (ver estadoDelPlano)
    const c = Object.keys(p).find((k) => p[k].getBounds);
    p[c!].fire('click');
    return c!;
  });
  await expect(inspector).toContainText(enPlano);
  await expect(tabla.locator('tr[aria-selected="true"]')).toContainText(enPlano);
  await expect.poll(() => estadoDelPlano(page, enPlano)).toEqual({ resaltado: true, visible: true });

  // Escape quita la selección en todas las vistas.
  await tabularHasta(page, tabla);
  await page.keyboard.press('Escape');
  await expect(seccion.getByRole('status')).toHaveText('Selección quitada.');
  await expect(inspector).toContainText('Elija un elemento en el plano, en la tabla o con el buscador.');
  await expect(tabla.locator('tr[aria-selected="true"]')).toHaveCount(0);
  await expect.poll(async () => (await estadoDelPlano(page, enPlano)).resaltado).toBe(false);
});

test('111 T21 — de un hallazgo de tensión y de uno de sobrecarga al elemento, con valor, umbral, norma, caso y motor',
  async ({ page }, info) => {
    test.setTimeout(400_000);
    const seccion = await abrirPestana(page);
    // Umbrales desde la web (perfil ficticio con «estudios») que incumple cualquier red sorteada: la sintética queda a
    // 0,999999-1 p.u. y con la banda 0,9999-1,00001 el hallazgo de tensión dependía de la semilla. El perfil exige que
    // 1 p.u. quede dentro, así que la banda es 1 ± 1e-9: la fuente (1 p.u.) cumple y cualquier barra con caída no; y
    // todo tramo con corriente pasa del 0,0001 %. Hay hallazgos de los dos tipos con cualquier semilla.
    const perfil = join(info.outputDir, 'perfil_umbrales_estrechos.json');
    mkdirSync(info.outputDir, { recursive: true });                  // Playwright la crea solo al guardar un artefacto
    writeFileSync(perfil, JSON.stringify({ perfil: 'ficticia', estudios: { tension_min_pu: 0.999999999, tension_max_pu: 1.000000001,
      cargabilidad_max_pct: 0.0001 } }), 'utf8');
    const tarjeta = page.locator('section.card').filter({ has: page.getByRole('heading', { name: 'Perfil de la empresa' }) });
    await tarjeta.getByLabel('Perfil (JSON)').setInputFiles(perfil);
    await tarjeta.getByRole('button', { name: 'Cargar perfil' }).click();
    await expect(tarjeta).toContainText('Perfil activo en');

    const caso = `Hallazgos (${info.project.name})`;
    await seccion.getByLabel('Caso', { exact: true }).fill(caso);
    await seccion.getByRole('button', { name: 'Nueva variación' }).click();
    await seccion.getByRole('button', { name: 'Estudiar', exact: true }).click();
    await expect(seccion.getByText('Estudie la variación para ver sus resultados.')).toBeHidden({ timeout: 300_000 });

    // Por su rol, como en plano.spec.ts: «getByLabel('Alimentador')» casaba también con la rejilla y el marco.
    const alimentador = await seccion.getByRole('combobox', { name: /^Alimentador\b/ }).inputValue();
    const lista = await api<{ variaciones: { id: string; caso: string }[] }>(page, `/plano/variaciones?${new URLSearchParams({ alimentador })}`);
    const id = lista.variaciones.find((v) => v.caso === caso)!.id;
    const capas = await api<{ capas: Record<string, { elementos: { codigo: string; incumple: null | { norma?: { acto?: string; falta?: string; criterio_empresa?: string } } }[] }> }>(
      page, `/plano/resultados?${new URLSearchParams({ variacion: id })}`);
    const inspector = seccion.locator('.plano-espacio-inspector');
    for (const capa of ['tension', 'cargabilidad']) {
      const e = capas.capas[capa].elementos.find((x) => x.incumple);
      expect(e, `un hallazgo de ${capa}`).toBeTruthy();
      const zona = seccion.getByRole('region', { name: capa === 'tension' ? 'Tensión por barra' : 'Cargabilidad por tramo' });
      const boton = zona.getByRole('button', { name: e!.codigo, exact: true }).first();
      await tabularHasta(page, boton, 400);
      await page.keyboard.press('Enter');
      const hallazgo = inspector.getByRole('region', { name: 'Hallazgo' });
      await expect(hallazgo).toBeVisible();
      const norma = e!.incumple!.norma!;
      // La norma (o su falta) es la que da el servidor desde la biblioteca, tal cual.
      await expect(hallazgo).toContainText(norma.criterio_empresa ?? norma.falta ?? norma.acto!);
      await expect(hallazgo).toContainText(caso);
      await expect(hallazgo).toContainText('motor abierto (pandapower)');
      await expect.poll(() => estadoDelPlano(page, e!.codigo)).toEqual({ resaltado: true, visible: true });
      await sinInfraccionesGraves(page, `hallazgo de ${capa}`);
    }
    await comprobar_sin_citas(page, 'el espacio de ingeniería');
  });

for (const [ancho, alto] of [[1366, 900], [1920, 1080]] as const) {
  test(`111 T22 — plano, tabla e inspector a la vez en ${ancho}×${alto}, con el reparto recordado`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: ancho, height: alto });
    const seccion = await abrirPestana(page);
    const vistas = ['.plano-espacio-mapa', '.plano-espacio-tabla', '.plano-espacio-inspector'].map((s) => seccion.locator(s));
    for (const v of vistas) {
      const caja = await v.boundingBox();
      expect(caja && caja.width > 150 && caja.height > 100, 'cada vista con su sitio en la pantalla').toBeTruthy();
    }
    // Las tres vistas a la vez, una junto a otra: el plano a la izquierda de la tabla y del inspector.
    const [mapa, tabla, insp] = await Promise.all(vistas.map((v) => v.boundingBox()));
    expect(mapa!.x + mapa!.width <= tabla!.x + 1 && tabla!.y + tabla!.height <= insp!.y + 1).toBeTruthy();

    const separador = seccion.getByRole('separator', { name: 'Ancho del plano' });
    const antes = Number(await separador.getAttribute('aria-valuenow'));
    await tabularHasta(page, separador);
    await page.keyboard.press('ArrowLeft');
    await page.keyboard.press('ArrowLeft');
    await expect(separador).toHaveAttribute('aria-valuenow', String(Math.max(25, antes - 10)));
    await page.reload({ waitUntil: 'networkidle' });
    const otra = await abrirPestana(page);
    await expect(otra.getByRole('separator', { name: 'Ancho del plano' })).toHaveAttribute('aria-valuenow', String(Math.max(25, antes - 10)));
    // Se deja como estaba para el siguiente recorrido.
    const sep = otra.getByRole('separator', { name: 'Ancho del plano' });
    await tabularHasta(page, sep);
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    await sinInfraccionesGraves(page, `espacio de ingeniería ${ancho}×${alto}`);
  });
}

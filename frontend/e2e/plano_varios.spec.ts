/**
 * 111 T24 a T26 (RF-24 a RF-26) — el plano con varios alimentadores en navegador real, sobre el espacio sintético
 * sorteado de `preparar.mjs`, en claro y en oscuro.
 *
 * T24 (RF-24): «Ver también» añade un alimentador; el plano lo dibuja con otro color, su capa sale en el selector y la
 *   leyenda dice qué color es cada uno.
 * T25 (RF-25): la pestaña dice cuántos puntos de transferencia hay entre los elegidos (los mismos que la página).
 * T26 (RF-26): las tres capas de etiquetas están en el selector y apagadas; al encender la del código de la SED y
 *   acercarse, se ven; lejos, se dice que hay que acercarse.
 * axe sin infracciones graves ni críticas en la pestaña; el marco del plano (sandbox sin origen) queda fuera de axe.
 */
import AxeBuilder from '@axe-core/playwright';
import { comprobar_sin_citas, expect, test, type Page } from './sin_red';

/* eslint-disable @typescript-eslint/no-explicit-any */
declare const map: any;
declare const datos: any;
declare const porCodigo: Record<string, any>;
declare const grupos: Record<string, any>;
declare const ZOOM_ETIQUETAS: number;
/* eslint-enable @typescript-eslint/no-explicit-any */

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

async function cerrarDialogo(page: Page): Promise<void> {
  const dialogo = page.getByRole('dialog');
  if (!(await dialogo.isVisible())) return;
  await page.keyboard.press('Escape');
  if (await dialogo.isVisible()) await dialogo.getByRole('button', { name: 'Cerrar' }).press('Enter');
  await expect(dialogo).toBeHidden();
}

function marco(page: Page) {
  const f = page.frames().find((x) => x.url().includes('/plano/pagina'));
  expect(f, 'el marco del plano').toBeTruthy();
  return f!;
}

test.describe.configure({ mode: 'serial' });

test('111:RF-24 a RF-26 varios alimentadores con su color, sus transferencias y las etiquetas', async ({ page }) => {
  await page.goto(process.env.CSG_E2E_ENTRADA!, { waitUntil: 'networkidle' });
  await cerrarDialogo(page);
  await page.getByRole('tablist', { name: 'Módulos' }).getByRole('tab', { name: 'Plano de la red' }).click();
  const seccion = page.getByRole('region', { name: 'Plano de la red' });
  await expect(seccion).toBeVisible();
  const principal = await seccion.getByRole('combobox', { name: /^Alimentador\b/ }).inputValue();

  // T24: «Ver también» con casillas; el principal no se ofrece.
  await seccion.locator('summary', { hasText: /^Ver también/ }).click();
  const casillas = seccion.getByRole('group', { name: 'Ver también' }).getByRole('checkbox');
  expect(await casillas.count(), 'el espacio sintético necesita dos alimentadores o más').toBeGreaterThan(0);
  await expect(seccion.getByRole('checkbox', { name: principal, exact: true })).toHaveCount(0);
  const otro = (await casillas.first().evaluate((el) => el.parentElement?.textContent ?? '')).trim();
  await casillas.first().check();
  await expect(seccion.getByText('Ver también (1)')).toBeVisible();
  await expect.poll(async () => page.frames().find((x) => x.url().includes('/plano/pagina')
    && x.url().includes(`alimentador=${encodeURIComponent(otro)}`)) !== undefined).toBe(true);
  await expect.poll(async () => page.frameLocator('iframe.map-frame').locator('#alimentadores:not([hidden])').count()).toBe(1);
  const leyenda = page.frameLocator('iframe.map-frame').locator('#alimentadores');
  await expect(leyenda).toContainText(principal);
  await expect(leyenda).toContainText(otro);

  const estado = await marco(page).evaluate(() => {
    const colores: Record<string, string[]> = {};
    for (const v of datos.vistas) {
      colores[v.alimentador] = [...new Set(v.tramos.map((t: { codigo: string }) => porCodigo[t.codigo]?.options?.color)
        .filter(Boolean))] as string[];
    }
    const nombres = Object.keys(grupos);
    return { colores, nombres, transferencias: (datos.transferencias ?? []).length,
      etiquetas: ['etiqueta_sed', 'etiqueta_kva', 'etiqueta_seccion'].map((k) => map.hasLayer(grupos[k])) };
  });
  const [c1, c2] = [estado.colores[principal], estado.colores[otro]];
  expect(c1.length, 'un color por alimentador').toBe(1);
  expect(c2.length, 'un color por alimentador').toBe(1);
  expect(c1[0], 'los dos alimentadores con el mismo color').not.toBe(c2[0]);
  await expect(page.frameLocator('iframe.map-frame').locator('.leaflet-control-layers-overlays', { hasText: 'Tramos' })).toContainText(otro);

  // T25: la pestaña lista los mismos puntos de transferencia que la página.
  await expect(seccion.getByText(`Puntos de transferencia (${estado.transferencias})`)).toBeVisible();

  // T26: las etiquetas empiezan apagadas; al encender la del código de la SED y acercarse, se ven.
  expect(estado.etiquetas).toEqual([false, false, false]);
  const capas = page.frameLocator('iframe.map-frame').locator('.leaflet-control-layers', { hasText: 'Tramos' });
  // La lista de «Ver también» no puede tapar el plano: Escape la cierra (pulsar en el plano, también).
  await page.keyboard.press('Escape');
  await expect(seccion.locator('details.selector-alimentadores')).not.toHaveAttribute('open', '');
  // Con el teclado: con el ratón, al desplazar la vista hasta la casilla el ratón sale del control y Leaflet lo pliega.
  await page.mouse.move(0, 0);
  const botonCapas = capas.locator('.leaflet-control-layers-toggle');
  await botonCapas.focus();
  await botonCapas.press('Enter');
  const casillaSed = capas.getByRole('checkbox', { name: 'Etiquetas: código de la SED' });
  await casillaSed.focus();
  await casillaSed.press('Space');
  await expect(casillaSed).toBeChecked();
  await marco(page).evaluate(() => map.setZoom(ZOOM_ETIQUETAS - 2, { animate: false }));
  await expect(page.frameLocator('iframe.map-frame').locator('#aviso-etiquetas')).toBeVisible();
  await marco(page).evaluate(() => {
    const sed = datos.vistas.flatMap((v: any) => v.sed.map((s: any) => v.barras.find((b: any) => b.codigo === s.barra)))
      .find((b: any) => b && b.lat != null);
    map.setView([sed.lat, sed.lon], ZOOM_ETIQUETAS + 2, { animate: false });
  });
  await expect(page.frameLocator('iframe.map-frame').locator('#aviso-etiquetas')).toBeHidden();
  await expect.poll(async () => page.frameLocator('iframe.map-frame').locator('.etiqueta:visible').count()).toBeGreaterThan(0);

  const r = await new AxeBuilder({ page }).withTags(WCAG).exclude('iframe.map-frame').analyze();
  expect(r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([]);
  await comprobar_sin_citas(page, 'plano con varios alimentadores');
});

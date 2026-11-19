/**
 * 111 T23 (RF-23, RF-2, RF-20) — el unifilar del alimentador en navegador real, con el teclado, sobre el espacio
 * sintético sorteado de `preparar.mjs` (la semilla sale en el registro): la vista «Unifilar» enseña cada barra del
 * plano con su mismo código y desde su cabecera; una selección con el buscador se resalta en el unifilar; volver a
 * «Plano» deja el plano; y las huellas de los vértices de la fuente no cambian (el unifilar es un esquema). axe sin
 * infracciones graves ni críticas en claro y en oscuro. Sin red (`sin_red.ts`) y sin citas a la vista.
 */
import AxeBuilder from '@axe-core/playwright';
import { createHash } from 'node:crypto';
import { expect, test, type Locator, type Page } from './sin_red';

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

type Vista = { alimentador: string; fuente: string; tramos: { codigo: string; desde: string; hasta: string; vertices: number[][] }[];
  unifilar: { fuente: string | null; barras: { codigo: string; nivel: number }[]; sin_alcanzar: string[] } };

async function api<T>(page: Page, ruta: string): Promise<T> {
  const espacio = encodeURIComponent(process.env.CSG_E2E_ESPACIO!);
  const r = await page.request.get(`${process.env.CSG_E2E_BASE}/api/workspaces/${espacio}${ruta}`);
  expect(r.ok(), `${ruta}: ${r.status()}`).toBeTruthy();
  return (await r.json()) as T;
}

async function vistaDe(page: Page, alimentador: string): Promise<Vista> {
  const d = await api<{ vistas: Vista[] }>(page, `/plano?${new URLSearchParams({ alimentador })}`);
  expect(d.vistas.length, 'la API da la vista del alimentador').toBe(1);
  return d.vistas[0];
}

const huella = (v: Vista) => createHash('sha256')
  .update(JSON.stringify(v.tramos.map((t) => [t.codigo, t.vertices]).sort((a, b) => String(a[0]).localeCompare(String(b[0])))))
  .digest('hex');

/** Pulsa Tab hasta que el foco cumpla `cumple`, como el operador: con Mayús+Tab si el destino (`hacia`) está antes del
 *  foco en el documento. Solo hacia delante, volver a «Plano» tras el buscador daba la vuelta a toda la página y, con
 *  el alimentador de algunas semillas y lo que dejan las specs anteriores, no llegaba en 80 pulsaciones. */
async function tabularHasta(page: Page, cumple: () => Promise<boolean>, max = 80, hacia?: Locator): Promise<void> {
  const atras = hacia ? await hacia.evaluate((el) => !!document.activeElement
    && (el.compareDocumentPosition(document.activeElement) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0) : false;
  for (let i = 0; i < max; i++) {
    if (await cumple()) return;
    await page.keyboard.press(atras ? 'Shift+Tab' : 'Tab');
  }
  throw new Error('el foco no llegó a su destino con Tab');
}
const enfocado = (loc: Locator) => () => loc.evaluate((el) => el === document.activeElement);

/** Como en plano_espacio (111-T20): si la web enseña el diálogo de la conversión que preparó el espacio, el operador
 *  lo cierra con el teclado; con él abierto el foco no sale del diálogo. */
async function cerrarDialogo(page: Page): Promise<void> {
  const dialogo = page.getByRole('dialog');
  if (!(await dialogo.isVisible())) return;
  await page.keyboard.press('Escape');
  if (await dialogo.isVisible()) await dialogo.getByRole('button', { name: 'Cerrar' }).press('Enter');
  await expect(dialogo).toBeHidden();
}

async function sinInfraccionesGraves(page: Page, estado: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(WCAG).exclude('iframe.map-frame').analyze();
  const graves = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.length} nodo(s)`);
  expect(graves, `axe en «${estado}»`).toEqual([]);
}

test('111 T23 — el unifilar con los códigos del plano, la misma selección y sin tocar la red, con el teclado',
  async ({ page }, info) => {
    test.setTimeout(300_000);
    console.log(`[111 T23] semilla ${process.env.CSG_E2E_SEMILLA} · ${info.project.name}`);
    await page.goto(process.env.CSG_E2E_ENTRADA!, { waitUntil: 'networkidle' });
    await cerrarDialogo(page);

    // A «Plano de la red» como el operador: Tab a la pestaña activa, flechas e Intro (F-11, patrón WAI-ARIA).
    const lista = page.getByRole('tablist', { name: 'Módulos' });
    const pestana = lista.getByRole('tab', { name: 'Plano de la red' });
    await tabularHasta(page, enfocado(lista.locator('[role="tab"][tabindex="0"]')), 120);
    const total = await lista.getByRole('tab').count();
    for (let i = 0; i < total && !(await enfocado(pestana)()); i++) await page.keyboard.press('ArrowRight');
    await expect(pestana).toBeFocused();
    await page.keyboard.press('Enter');
    const seccion = page.getByRole('region', { name: 'Plano de la red' });
    await expect(seccion).toBeVisible();

    const alimentador = await seccion.getByRole('combobox', { name: /^Alimentador\b/ }).inputValue();
    const vista = await vistaDe(page, alimentador);
    const antes = huella(vista);
    expect(vista.unifilar.fuente, 'el unifilar empieza en la cabecera del alimentador').toBe(vista.fuente);

    // A la vista «Unifilar» con el teclado.
    const unifilar = seccion.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Unifilar', exact: true });
    await tabularHasta(page, enfocado(unifilar), 80, unifilar);
    await page.keyboard.press('Enter');
    await expect(unifilar).toHaveAttribute('aria-pressed', 'true');
    const dibujo = seccion.getByRole('img', { name: `Unifilar del alimentador ${alimentador}` });
    await expect(dibujo).toBeVisible();
    await expect(seccion.locator('iframe.map-frame')).toHaveCount(0);

    // Cada barra del plano, con su mismo código, en el unifilar (111:RF-2).
    const codigos = await dibujo.locator('circle[data-codigo]').evaluateAll((els) => els.map((e) => e.getAttribute('data-codigo')));
    expect(new Set(codigos)).toEqual(new Set(vista.unifilar.barras.map((b) => b.codigo)));
    await sinInfraccionesGraves(page, 'unifilar');

    // La misma selección (111:RF-20): elegir un tramo con el buscador lo resalta en el unifilar.
    const barras = new Set(vista.unifilar.barras.map((b) => b.codigo));
    const tramo = vista.tramos.find((t) => barras.has(t.desde) && barras.has(t.hasta))?.codigo;
    expect(tramo, 'el alimentador sorteado trae tramos').toBeTruthy();
    const buscar = seccion.getByLabel('Buscar por código');
    await tabularHasta(page, enfocado(buscar), 80, buscar);
    await page.keyboard.type(tramo!);
    const hallado = seccion.locator('#plano-hallados').getByRole('button', { name: tramo!, exact: true });
    await tabularHasta(page, enfocado(hallado), 80, hallado);
    await page.keyboard.press('Enter');
    await expect(seccion.getByRole('status').first()).toHaveText(`${tramo} seleccionado.`);
    await expect(dibujo.locator(`[data-codigo="${tramo}"]`).first()).toHaveClass(/unifilar-elegido/);

    // Volver a «Plano» deja el plano, y la red del operador no cambió.
    const planoBoton = seccion.getByRole('group', { name: 'Vista' }).getByRole('button', { name: 'Plano', exact: true });
    await tabularHasta(page, enfocado(planoBoton), 80, planoBoton);
    await page.keyboard.press('Enter');
    await expect(seccion.locator('iframe.map-frame')).toBeVisible();
    expect(huella(await vistaDe(page, alimentador)), 'el unifilar tocó los vértices de la fuente').toBe(antes);
  });

/**
 * 111 T16 (RF-1 a RF-4, RF-10 a RF-14, RF-16 a RF-19) — el editor sobre el plano en navegador real, solo con el teclado,
 * sobre el espacio sintético sorteado de `preparar.mjs` (la semilla sale en el registro).
 *
 * 1. Maniobra → flujo con el motor abierto → resultados sobre el plano: buscar una maniobra por su código, abrir una
 *    variación del caso, cambiar su estado y estudiar; la pestaña pinta los resultados y dice con qué motor.
 * 2. Comparación de dos casos: un segundo caso estudiado sin cambios, y la comparación del A con el B.
 * Las huellas de los vértices de la fuente son las mismas antes y después (la variación no toca la red del operador).
 * axe sin infracciones graves ni críticas en cada estado, en claro y en oscuro (los dos proyectos de la configuración);
 * el plano va en un `<iframe sandbox>` sin origen propio, que axe no puede abrir: su alternativa con teclado (buscador,
 * tabla e inspector) es lo que se revisa. Sin red (`sin_red.ts`) y sin citas a la vista.
 */
import AxeBuilder from '@axe-core/playwright';
import { createHash } from 'node:crypto';
import { comprobar_sin_citas, expect, test, type Page } from './sin_red';

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

function espacio(): string {
  return process.env.CSG_E2E_ESPACIO!;
}

async function api<T>(page: Page, ruta: string): Promise<T> {
  const r = await page.request.get(`${process.env.CSG_E2E_BASE}/api/workspaces/${encodeURIComponent(espacio())}${ruta}`);
  expect(r.ok(), `${ruta}: ${r.status()}`).toBeTruthy();
  return (await r.json()) as T;
}

type Vista = { alimentador: string; tramos: { codigo: string; vertices: number[][] }[];
  maniobras?: { codigo: string; estado: string }[] };

/** La huella de los vértices de los tramos de la fuente, tal como los da la API del plano. */
async function huellaDeVertices(page: Page, alimentador: string): Promise<string> {
  const d = await api<{ vistas: Vista[] }>(page, `/plano?${new URLSearchParams({ alimentador })}`);
  const tramos = d.vistas.flatMap((v) => v.tramos.map((t) => [t.codigo, t.vertices] as const))
    .sort(([a], [b]) => a.localeCompare(b));
  expect(tramos.length, 'la vista trae tramos con vértices').toBeGreaterThan(0);
  return createHash('sha256').update(JSON.stringify(tramos)).digest('hex');
}

async function sinInfraccionesGraves(page: Page, estado: string): Promise<void> {
  const r = await new AxeBuilder({ page }).withTags(WCAG).exclude('iframe.map-frame').analyze();
  const graves = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.length} nodo(s)`);
  expect(graves, `axe en «${estado}»`).toEqual([]);
}

/** Pulsa Tab hasta que el foco cumpla `cumple` (sin ratón), como lo haría el operador: con Mayús+Tab si el destino
 *  (`hacia`) está antes del foco en el documento (el inspector va encima de la barra de la variación). */
async function tabularHasta(page: Page, cumple: () => Promise<boolean>, max = 60,
                            hacia?: import('@playwright/test').Locator): Promise<void> {
  const atras = hacia ? await hacia.evaluate((el) => !!document.activeElement
    && (el.compareDocumentPosition(document.activeElement) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0) : false;
  for (let i = 0; i < max; i++) {
    if (await cumple()) return;
    await page.keyboard.press(atras ? 'Shift+Tab' : 'Tab');
  }
  throw new Error('el foco no llegó a su destino con Tab');
}

const enfocado = (loc: import('@playwright/test').Locator) => () => loc.evaluate((el) => el === document.activeElement);
/** El foco con el teclado hasta `loc`, hacia delante o hacia atrás según dónde esté en el documento. */
//  Hasta 200 pulsaciones: si un repintado deja el foco en el cuerpo, se vuelve a recorrer la página desde arriba.
const irA = (page: Page, loc: import('@playwright/test').Locator, max = 200) => tabularHasta(page, enfocado(loc), max, loc);

/** Escribe en un campo con el teclado: lo enfoca con Tab desde el anterior y reemplaza su texto. */
async function escribir(page: Page, campo: import('@playwright/test').Locator, texto: string): Promise<void> {
  await irA(page, campo);
  await page.keyboard.press('Control+A');
  await page.keyboard.type(texto);
}

async function estudiar(page: Page, seccion: import('@playwright/test').Locator): Promise<void> {
  const boton = seccion.getByRole('button', { name: 'Estudiar', exact: true });
  await irA(page, boton);
  await page.keyboard.press('Enter');
  // Al acabar el trabajo, la pestaña pide las capas: el aviso de «sin resultados» desaparece. Si no son pintables, la
  // prueba lo dice después con su motivo (de la API).
  await expect(seccion.getByText('Estudie la variación para ver sus resultados.')).toBeHidden({ timeout: 170_000 });
}

test('111 T16 — maniobra, flujo con el motor abierto, resultados sobre el plano y comparación de dos casos, con el teclado',
  async ({ page }, info) => {
    test.setTimeout(600_000);
    console.log(`[111 T16] semilla ${process.env.CSG_E2E_SEMILLA} · ${info.project.name}`);
    await page.goto(process.env.CSG_E2E_ENTRADA!, { waitUntil: 'networkidle' });
    // Si la web enseña el diálogo de la conversión que preparó el espacio, el operador lo cierra con el teclado: con él
    // abierto, el foco no sale del diálogo.
    const dialogo = page.getByRole('dialog');
    if (await dialogo.isVisible()) {
      await page.keyboard.press('Escape');
      if (await dialogo.isVisible()) await dialogo.getByRole('button', { name: 'Cerrar' }).press('Enter');
      await expect(dialogo).toBeHidden();
    }

    // La pestaña del plano, con el teclado y como el operador: las pestañas tienen foco itinerante (F-11, patrón WAI-ARIA
    // de pestañas): un solo Tab llega a la activa y las flechas mueven el foco a las demás; Intro abre.
    const lista = page.getByRole('tablist', { name: 'Módulos' });
    const pestana = lista.getByRole('tab', { name: 'Plano de la red' });
    await irA(page, lista.locator('[role="tab"][tabindex="0"]'), 120);
    const total = await lista.getByRole('tab').count();
    for (let i = 0; i < total && !(await enfocado(pestana)()); i++) await page.keyboard.press('ArrowRight');
    await expect(pestana, 'las flechas no llevan el foco a «Plano de la red»').toBeFocused();
    await page.keyboard.press('Enter');
    // La región del plano (su section aria-labelledby), única: «section.card» con ese título casaba también con el
    // contenedor de las pestañas, que lo contiene.
    const seccion = page.getByRole('region', { name: 'Plano de la red' });
    await expect(seccion).toBeVisible();

    // El selector del alimentador por su rol: «getByLabel('Alimentador')» busca por subcadena y casaba también con la
    // rejilla «Elementos del alimentador» y el marco «Plano del alimentador»; y su rótulo envuelve el <select>, así que
    // su texto lleva el de las opciones y «exact» tampoco casaría.
    const alimentador = await seccion.getByRole('combobox', { name: /^Alimentador\b/ }).inputValue();
    const datos = await api<{ vistas: Vista[]; motor: { texto: string } }>(page, `/plano?${new URLSearchParams({ alimentador })}`);
    const maniobra = datos.vistas.flatMap((v) => v.maniobras ?? [])[0];
    expect(maniobra, `el alimentador ${alimentador} del espacio sintético trae alguna maniobra`).toBeTruthy();
    const antes = await huellaDeVertices(page, alimentador);
    await expect(seccion.getByText(datos.motor.texto, { exact: false })).toBeVisible();
    await sinInfraccionesGraves(page, 'plano abierto');

    // 1. Buscar la maniobra por su código y elegirla desde la lista de hallados.
    await escribir(page, seccion.getByLabel('Buscar por código'), maniobra.codigo);
    const hallado = seccion.locator('#plano-hallados').getByRole('button', { name: maniobra.codigo, exact: true });
    await irA(page, hallado);
    await page.keyboard.press('Enter');
    await expect(seccion.getByRole('status')).toHaveText(`${maniobra.codigo} seleccionado.`);

    // Una variación del caso con su nombre (único por proyecto: claro y oscuro corren sobre el mismo espacio).
    const casoA = `Maniobra ${maniobra.codigo} (${info.project.name})`;
    await escribir(page, seccion.getByLabel('Caso', { exact: true }), casoA);
    const nueva = seccion.getByRole('button', { name: 'Nueva variación' });
    await irA(page, nueva);
    await page.keyboard.press('Enter');
    await expect(seccion.getByRole('status')).toHaveText(`Variación abierta sobre ${alimentador}.`);

    // Cambiar el estado de la maniobra en la variación (no en la red del operador).
    const cambiar = seccion.getByRole('button', { name: /^Cambiar estado: (abrir|cerrar)$/ });
    const destino = (await cambiar.innerText()).endsWith('abrir') ? 'abierto' : 'cerrado';
    await irA(page, cambiar);
    await page.keyboard.press('Enter');
    await expect(seccion.getByRole('status')).toHaveText(`${maniobra.codigo}: ${destino}.`);
    await sinInfraccionesGraves(page, 'maniobra en la variación');

    // El flujo con el motor abierto, como trabajo; sus resultados se pintan sobre el plano y dicen el motor.
    await estudiar(page, seccion);
    const variaciones = await api<{ variaciones: { id: string; caso: string }[]; estudiadas: string[] }>(
      page, `/plano/variaciones?${new URLSearchParams({ alimentador })}`);
    const idA = variaciones.variaciones.find((v) => v.caso === casoA)?.id;
    expect(idA && variaciones.estudiadas.includes(idA), 'la variación de la maniobra quedó estudiada').toBeTruthy();
    const capas = await api<{ pintable: boolean; motor_texto: string; motivo?: string }>(
      page, `/plano/resultados?${new URLSearchParams({ variacion: idA! })}`);
    expect(capas.pintable, capas.motivo ?? 'resultados pintables').toBeTruthy();
    await expect(seccion.getByText(capas.motor_texto, { exact: false }).first()).toBeVisible();
    await sinInfraccionesGraves(page, 'resultados sobre el plano');

    // 2. Un segundo caso, sin cambios, también estudiado; y la comparación del A con el B.
    const casoB = `Sin cambios (${info.project.name})`;
    await escribir(page, seccion.getByLabel('Caso', { exact: true }), casoB);
    await irA(page, nueva);
    await page.keyboard.press('Enter');
    await expect(seccion.getByRole('status')).toHaveText(`Variación abierta sobre ${alimentador}.`);
    await estudiar(page, seccion);

    const a = seccion.getByLabel('Caso A');
    const b = seccion.getByLabel('Caso B');
    await expect(a).toBeVisible({ timeout: 30_000 });
    for (const [selector, caso] of [[a, casoA], [b, casoB]] as const) {
      await irA(page, selector);
      // Con las flechas hasta la opción del caso: sin ratón y sin «selectOption».
      for (let i = 0; i < 40 && !(await selector.evaluate((s: HTMLSelectElement) => s.selectedOptions[0]?.text)).startsWith(caso); i++) {
        await page.keyboard.press('ArrowDown');
      }
      expect(await selector.evaluate((s: HTMLSelectElement) => s.selectedOptions[0]?.text)).toBe(caso);
    }
    const comparar = seccion.getByRole('button', { name: 'Comparar', exact: true });
    await irA(page, comparar);
    await page.keyboard.press('Enter');
    const lista2 = await api<{ variaciones: { id: string; caso: string }[] }>(
      page, `/plano/variaciones?${new URLSearchParams({ alimentador })}`);
    const idB = lista2.variaciones.find((v) => v.caso === casoB)?.id;
    const comparacion = await api<{ comparable: boolean; motivo?: string }>(
      page, `/plano/comparar?${new URLSearchParams({ a: idA!, b: idB! })}`);
    expect(comparacion.comparable, comparacion.motivo ?? 'los dos casos se comparan').toBeTruthy();
    // La tabla de la comparación nombra los dos casos en sus columnas.
    const tabla = seccion.getByRole('table').filter({ has: page.getByRole('columnheader', { name: casoA }) });
    await expect(tabla.getByRole('columnheader', { name: casoB })).toBeVisible();
    await sinInfraccionesGraves(page, 'comparación de dos casos');

    // La red de la fuente, intacta: las mismas huellas de los vértices antes y después.
    expect(await huellaDeVertices(page, alimentador), 'huellas de los vértices de la fuente').toBe(antes);
    await comprobar_sin_citas(page, 'la pestaña del plano');
  });

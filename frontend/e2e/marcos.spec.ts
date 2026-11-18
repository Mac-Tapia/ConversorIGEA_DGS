/**
 * 086 T75 (RF-21) — los marcos los decide la puerta, en navegador real, sobre el espacio sintético de `preparar.mjs`.
 *
 * 1. Dentro de la web: el plano de la red y la vista previa del alimentador, las páginas que la interfaz enmarca, se
 *    ven en un `<iframe>` de la propia web (mismo origen): el documento carga con su contenido.
 * 2. Desde otro origen (una página servida en `http://localhost:9`, que no es el de la web): las mismas rutas no se
 *    dejan enmarcar. Sin la cookie de la sesión (SameSite=Strict) la puerta responde 401, y también esa respuesta niega
 *    el marco: el navegador no pinta nada de la web dentro.
 * La cabecera de cada caso (X-Frame-Options y frame-ancestors) se comprueba aparte en tests/test_seguridad_web.py.
 */
import { expect, test, type Page } from './sin_red';

const base = () => process.env.CSG_E2E_BASE!;
const espacio = () => process.env.CSG_E2E_ESPACIO!;
const OTRO_ORIGEN = 'http://localhost:9';

async function rutasEnmarcables(page: Page): Promise<{ nombre: string; url: string; marca: string }[]> {
  const w = `${base()}/api/workspaces/${encodeURIComponent(espacio())}`;
  const feeders = (await (await page.request.get(`${w}/feeders`)).json()).feeders.map((f: { feeder: string }) => f.feeder);
  expect(feeders.length, 'el espacio sintético trae alimentadores').toBeGreaterThan(0);
  const salidas: { path: string }[] = await (await page.request.get(`${w}/outputs`)).json();
  const previa = salidas.map((s) => s.path).find((p) => p.toLowerCase().endsWith('.html'));
  expect(previa, 'la conversión con vista previa dejó su página HTML').toBeTruthy();
  return [
    { nombre: 'plano de la red', url: `${w}/plano/pagina?${new URLSearchParams({ alimentador: feeders[0] })}`, marca: '#mapa' },
    { nombre: 'vista previa del alimentador', url: `${w}/files/${previa!.split('/').map(encodeURIComponent).join('/')}`, marca: 'body *' },
  ];
}

/** Mete un iframe con `src` en la página y espera a que el navegador termine con él. */
async function enmarcar(page: Page, src: string): Promise<import('@playwright/test').Frame | null> {
  await page.evaluate((s) => new Promise<void>((ok) => {
    const f = document.createElement('iframe');
    f.id = 'marco-de-prueba';
    f.setAttribute('sandbox', 'allow-scripts');
    f.style.width = '900px';
    f.style.height = '600px';
    f.addEventListener('load', () => ok(), { once: true });
    setTimeout(() => ok(), 15_000);
    f.src = s;
    document.body.appendChild(f);
  }), src);
  const elemento = await page.$('#marco-de-prueba');
  return elemento ? elemento.contentFrame() : null;
}

/** Lo que pinta el marco: un documento de la web con su contenido, o nada (bloqueado por la puerta). */
async function contenido(marco: import('@playwright/test').Frame | null, marca: string): Promise<number> {
  if (!marco) return 0;
  try {
    return await marco.locator(marca).count();
  } catch {
    return 0;   // un marco bloqueado queda en una página de error del navegador: no hay documento de la web
  }
}

test('086 T75 — la web enseña dentro sus dos mapas y otro origen no puede enmarcarlos', async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto(process.env.CSG_E2E_ENTRADA!, { waitUntil: 'networkidle' });
  const rutas = await rutasEnmarcables(page);

  // 1. Mismo origen: la web enmarca sus páginas y se ven.
  for (const r of rutas) {
    const marco = await enmarcar(page, r.url);
    await expect.poll(() => contenido(marco, r.marca), { message: `${r.nombre} dentro de la web` }).toBeGreaterThan(0);
    await page.evaluate(() => document.getElementById('marco-de-prueba')?.remove());
  }

  // 2. Otro origen: una página de prueba en localhost:9 con los mismos marcos. La ruta propia va antes que la de
  //    sin_red.ts (Playwright atiende primero la última registrada) y nada sale de la máquina.
  const otra = await page.context().newPage();
  await otra.route(`${OTRO_ORIGEN}/**`, (ruta) => ruta.fulfill({ status: 200, contentType: 'text/html',
    body: '<!doctype html><html lang="es"><head><title>Otro origen</title></head><body><p>otro origen</p></body></html>' }));
  await otra.goto(`${OTRO_ORIGEN}/`);
  for (const r of rutas) {
    const marco = await enmarcar(otra, r.url);
    // Dejamos tiempo de sobra para que, si la puerta lo permitiera, el documento cargase.
    await otra.waitForTimeout(1500);
    expect(await contenido(marco, r.marca), `${r.nombre} enmarcado desde otro origen`).toBe(0);
    await otra.evaluate(() => document.getElementById('marco-de-prueba')?.remove());
  }
  await otra.close();
});

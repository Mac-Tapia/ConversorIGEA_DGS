/**
 * F10 Libros nuevos reconocidos solos (104 T6, RF-1, RF-20, RF-23): en un navegador real, con la web arrancada y la
 * vigilancia encendida (su propia web, `CSG_LIBROS_NUEVOS=1` con un intervalo corto), un libro de clientes que llega a la
 * carpeta del espacio aparece reconocido en «Novedades de los libros» sin pulsar nada, y el dataset del espacio se
 * regenera solo. Libros sintéticos de tests/e2e_libros_sinteticos.py, sin datos de ninguna empresa. axe en cada estado.
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test as base, expect } from '@playwright/test';
import { captura, revisarAxe, sinRedNiErrores } from './comun.mjs';
import { carpetaLibrosE2E, puertoLibrosE2E, pythonServidor } from './entorno.mjs';

const FLUJO = 'F10_libros_nuevos';
const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const ORIGEN = `http://127.0.0.1:${puertoLibrosE2E()}`;
const LOCALES = new Set(['127.0.0.1', 'localhost', '[::1]']);

// La misma guarda que comun.mjs (sin red y sin errores), sobre la web de los libros nuevos.
const test = base.extend({
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
  errores: async ({ page }, use) => {
    const lista = [];
    page.on('pageerror', (e) => lista.push(`pageerror: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') lista.push(`console: ${m.text()}`); });
    await use(lista);
  },
});

function libros(orden, carpeta) {
  const salida = execFileSync(pythonServidor(RAIZ), [join(RAIZ, 'tests', 'e2e_libros_sinteticos.py'), orden, carpeta],
    { cwd: RAIZ, env: { ...process.env, PYTHONPATH: join(RAIZ, 'src'), PYTHONUTF8: '1' }, encoding: 'utf8' });
  return JSON.parse(salida.trim().split('\n').pop());
}

test('F10 libros nuevos: el libro que llega a la carpeta se reconoce y avisa sin pulsar nada, y el dataset se regenera',
  async ({ page, externas, errores }, testInfo) => {
    test.setTimeout(300_000);
    const token = JSON.parse(readFileSync(join(carpetaLibrosE2E(), 'sesiones', `${puertoLibrosE2E()}.json`), 'utf8')).token;
    await page.goto(`${ORIGEN}/?acceso=${encodeURIComponent(token)}`);
    await expect(page.getByRole('heading', { name: 'ConverterSmartGrid', level: 1 })).toBeVisible({ timeout: 60_000 });

    // El espacio con sus libros de septiembre, su cabecera, sus medidores y sus suministros (como los asignaría el
    // operador en «Demanda medida»); el índice de clientes y el de cabecera, hechos.
    const carpeta = join(testInfo.outputDir, 'libros');
    const rutas = libros('preparar', carpeta);
    // Como la web: todo lo que cambia algo lleva su Origin (la seguridad de la web lo exige; sin él, 403). Si una
    // petición falla, la prueba lo dice con su cuerpo, no con el «undefined» de lo que venía detrás.
    const enviar = async (ruta, datos) => {
      const r = await page.request.post(`${ORIGEN}${ruta}`, { headers: { Origin: ORIGEN }, ...(datos ? { data: datos } : {}) });
      expect(r.ok(), `POST ${ruta}: ${r.status()} ${await r.text()}`).toBeTruthy();
      return r.json();
    };
    const wid = (await enviar('/api/workspaces')).id;
    for (const tipo of ['clientes', 'suministros', 'cabecera', 'medidores']) {
      await enviar(`/api/workspaces/${wid}/demanda/${tipo}/path`, { path: rutas[tipo] });
    }
    for (const tipo of ['clientes', 'cabecera']) {
      const job = await enviar(`/api/workspaces/${wid}/demanda/${tipo}/indexar`);
      await expect.poll(async () => (await (await page.request.get(`${ORIGEN}/api/jobs/${job.id}`)).json()).status,
        { timeout: 120_000 }).toBe('done');
    }
    await page.goto(`${ORIGEN}/?espacio=${wid}`);
    await page.getByRole('tab', { name: 'Cargas en DIgSILENT' }).click();
    const novedades = page.locator('details.novedades');
    await expect(novedades).toBeVisible({ timeout: 60_000 });
    await revisarAxe(page, FLUJO, '0_sin_libros_nuevos', testInfo);

    // Llega el libro de octubre a la carpeta. Nadie pulsa nada: la vigilancia lo ve en su intervalo y lo avisa.
    libros('octubre', carpeta);
    const aviso = novedades.locator('li.novedad').filter({ hasText: 'Llegó octubre 2026 de clientes importantes' });
    await expect(aviso).toHaveCount(1, { timeout: 180_000 });
    await expect(aviso).toContainText('3 clientes');
    await expect(aviso).toContainText('333');
    await captura(page, FLUJO, '1_libro_nuevo_avisado');
    await revisarAxe(page, FLUJO, '1_libro_nuevo_avisado', testInfo);

    // El dataset del espacio se regenera solo con el libro nuevo, sin entrenar nada.
    await expect.poll(async () => (await (await page.request.get(`${ORIGEN}/api/workspaces/${wid}/demanda/libros-nuevos`)).json())
      .dataset?.estado, { timeout: 180_000 }).toBe('al_dia');
    const estado = await (await page.request.get(`${ORIGEN}/api/workspaces/${wid}/demanda/libros-nuevos`)).json();
    expect(estado.dataset.libros_incluidos).toContain('clientes/2026/1026clientes.xlsx');
    sinRedNiErrores(externas, errores);
  });

/**
 * F-11 en el navegador (Plan Maestro V1, spec 086): la web se maneja sin ratón. Salto al contenido, pestañas con
 * flechas, Intro y su panel enlazado, separador del Registro con teclado y con una pulsación, foco visible y
 * objetivos de al menos 24 px en la cabecera, las pestañas y el Registro. Deja capturas para la revisión manual.
 */
import { test, expect, captura, revisarAxe, sinRedNiErrores, carpetaDe } from './comun.mjs';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

const FLUJO = 'F11_teclado';

test('F-11 el primer Tab enseña «Ir al contenido» y lleva el foco al contenido', async ({ web: page, externas, errores }) => {
  // Recién cargada, el foco parte del principio del documento.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'ConverterSmartGrid', level: 1 })).toBeVisible({ timeout: 60_000 });
  await page.keyboard.press('Tab');
  const saltar = page.getByRole('link', { name: 'Ir al contenido' });
  await expect(saltar).toBeFocused();
  await expect(saltar).toBeInViewport();
  await captura(page, FLUJO, '0_saltar');
  await page.keyboard.press('Enter');
  await expect(page.locator('#contenido')).toBeFocused();
  sinRedNiErrores(externas, errores);
});

test('F-11 pestañas: un solo Tab, flechas que mueven el foco sin abrir, Intro que abre y panel enlazado',
  async ({ web: page, externas, errores }, testInfo) => {
    const lista = page.getByRole('tablist', { name: 'Módulos' });
    const pestanas = lista.getByRole('tab');
    const n = await pestanas.count();
    expect(n, 'hay al menos dos pestañas sin entregas cargadas').toBeGreaterThan(1);
    await expect(lista.locator('[role="tab"][tabindex="0"]')).toHaveCount(1);
    const elegida = lista.locator('[aria-selected="true"]');
    await elegida.focus();
    const antes = await elegida.getAttribute('id');
    await page.keyboard.press('ArrowRight');
    const enfocada = page.locator(':focus');
    await expect(enfocada).toHaveAttribute('role', 'tab');
    expect(await enfocada.getAttribute('id')).not.toBe(antes);
    await expect(lista.locator('[aria-selected="true"]')).toHaveAttribute('id', antes ?? '');
    // El foco se ve (2.4.7): el contorno no es «none» ni de grosor cero.
    const contorno = await enfocada.evaluate((el) => { const s = getComputedStyle(el); return [s.outlineStyle, s.outlineWidth]; });
    expect(contorno[0]).not.toBe('none');
    expect(parseFloat(contorno[1])).toBeGreaterThanOrEqual(2);
    await captura(page, FLUJO, '1_foco_en_pestana');
    await page.keyboard.press('Enter');
    const id = await enfocada.getAttribute('id');
    await expect(page.locator(`#${id}`)).toHaveAttribute('aria-selected', 'true');
    const panel = page.locator(`[role="tabpanel"][aria-labelledby="${id}"]`);
    await expect(panel).toBeVisible();
    await expect(page.locator(`#${id}`)).toHaveAttribute('aria-controls', (await panel.getAttribute('id')) ?? '');
    // Fin e Inicio van a los extremos, con vuelta.
    await page.keyboard.press('End');
    await expect(pestanas.nth(n - 1)).toBeFocused();
    await page.keyboard.press('ArrowRight');
    await expect(pestanas.first()).toBeFocused();
    await page.keyboard.press('Home');
    await expect(pestanas.first()).toBeFocused();
    await revisarAxe(page, FLUJO, '1_pestanas', testInfo);
    sinRedNiErrores(externas, errores);
  });

test('F-11 el separador del Registro se mueve con flechas y se pliega con una pulsación, sin arrastrar',
  async ({ web: page, externas, errores }) => {
    const separador = page.getByRole('separator', { name: 'Altura del Registro' });
    // Orden de tabulación (2.4.3): el separador va justo antes del Registro.
    await page.getByPlaceholder('Buscar en el registro…').focus();
    await page.keyboard.press('Shift+Tab');
    await expect(separador).toBeFocused();
    const altura = async () => Number(await separador.getAttribute('aria-valuenow'));
    const h0 = await altura();
    await page.keyboard.press('ArrowUp');
    await expect.poll(altura).toBe(Math.min(h0 + 20, Number(await separador.getAttribute('aria-valuemax'))));
    await page.keyboard.press('Home');
    await expect.poll(altura).toBe(Number(await separador.getAttribute('aria-valuemin')));
    await page.keyboard.press('End');
    const maxima = await altura();
    // 2.5.7: una pulsación, sin mover el puntero, lo pliega; otra lo devuelve.
    await separador.click();
    await expect.poll(altura).toBe(Number(await separador.getAttribute('aria-valuemin')));
    await separador.click();
    await expect.poll(altura).toBe(maxima);
    await captura(page, FLUJO, '2_registro');
    sinRedNiErrores(externas, errores);
  });

test('F-11 los objetivos de la cabecera, las pestañas y el Registro miden al menos 24 px (2.5.8)',
  async ({ web: page, externas, errores }, testInfo) => {
    const medidas = await page.evaluate(() => {
      const zonas = ['.topbar', '[role="tablist"]', '.log-head', '[role="separator"]'];
      const objetivos = zonas.flatMap((z) => [...document.querySelectorAll(z)].flatMap((raiz) =>
        [raiz, ...raiz.querySelectorAll('button, a[href], input, select, textarea, [role="tab"], [tabindex="0"]')]))
        .filter((el, i, todos) => todos.indexOf(el) === i && el.matches('button, a[href], input, select, textarea, [role], [tabindex="0"]'));
      return objetivos.map((el) => {
        // Para un control oculto dentro de una etiqueta (el interruptor o la casilla de «Seguir»), cuenta la etiqueta.
        const caja = (el.closest('label') ?? el).getBoundingClientRect();
        const ext = el.matches('[role="separator"]') ? getComputedStyle(el, '::before') : null;
        const alto = ext ? caja.height - parseFloat(ext.top) - parseFloat(ext.bottom) : caja.height;
        return { que: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} «${(el.textContent ?? '').trim().slice(0, 30)}»`,
          ancho: Math.round(caja.width), alto: Math.round(alto), visible: caja.width > 0 && caja.height > 0 };
      }).filter((m) => m.visible);
    });
    writeFileSync(join(carpetaDe(FLUJO), 'objetivos.json'), JSON.stringify(medidas, null, 2));
    await testInfo.attach('objetivos', { path: join(carpetaDe(FLUJO), 'objetivos.json'), contentType: 'application/json' });
    const pequenos = medidas.filter((m) => m.alto < 24 || m.ancho < 24).map((m) => `${m.que}: ${m.ancho}×${m.alto}`);
    expect(pequenos).toEqual([]);
    sinRedNiErrores(externas, errores);
  });

test.describe('F-11 tema oscuro', () => {
  test.use({ colorScheme: 'dark' });
  test('F-11 con el sistema en oscuro, axe no encuentra infracciones graves (contraste incluido)',
    async ({ web: page, externas, errores }, testInfo) => {
      await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe('dark');
      await captura(page, FLUJO, '3_oscuro');
      await revisarAxe(page, FLUJO, '3_oscuro', testInfo);
      for (const nombre of ['Cargas en DIgSILENT', 'Asistente']) {
        const pestana = page.getByRole('tab', { name: new RegExp(nombre) });
        if (!(await pestana.count())) continue;
        await pestana.click();
        await revisarAxe(page, FLUJO, `3_oscuro_${nombre.split(' ')[0].toLowerCase()}`, testInfo);
      }
      sinRedNiErrores(externas, errores);
    });
});

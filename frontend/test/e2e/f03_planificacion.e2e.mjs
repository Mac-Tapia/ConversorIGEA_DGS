/**
 * F03 Planificación regulatoria (Plan Maestro V1, §31.6; F-12), con 072:RF-42 y RF-43: el corto plazo, el PIDE y el
 * largo plazo tienen su pestaña y «Cargas en DIgSILENT» ya no repite su elección. Por cada tipo que da el servidor
 * (ninguno fijo en la prueba): su pestaña con el tipo fijo, su ficha, el año de presentación con su aviso si no vale y
 * sus pasos hasta la sección que toca. Sin DIgSILENT ni red. axe en cada estado.
 */
import { test, expect, captura, revisarAxe, sinRedNiErrores } from './comun.mjs';

const FLUJO = 'F03_planificacion';
/** La pestaña de cada tipo (App.tsx; modulosPlaneamiento.test.mjs fija las mismas). */
const PESTANA = { corto_plazo: 'Corto plazo', pide: 'PIDE', largo_plazo: 'Largo plazo' };

test('F03 planificación: cada tipo del servidor en su pestaña, con su ficha, su año y sus pasos; «Cargas» no lo repite',
  async ({ web: page, externas, errores }, testInfo) => {
    // Lo que el servidor ofrece, leído de la misma API que usa la página (con la cookie de la sesión).
    const respuesta = await page.request.get('/api/planeamiento/tipos');
    expect(respuesta.ok(), `GET /api/planeamiento/tipos: ${respuesta.status()}`).toBeTruthy();
    const tipos = await respuesta.json();
    expect(tipos.tipos.length, 'el servidor ofrece algún tipo de análisis').toBeGreaterThan(0);

    // 072:RF-43: «Cargas en DIgSILENT» sigue entera, sin el selector de los tipos que ya son pestañas.
    await page.getByRole('tab', { name: 'Cargas en DIgSILENT' }).click();
    await expect(page.getByRole('radiogroup', { name: 'Tipo de análisis' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '1 · Proyecto de DIgSILENT' })).toBeVisible();
    await revisarAxe(page, FLUJO, '0_cargas_sin_selector', testInfo);

    for (const t of tipos.tipos) {
      const pestana = PESTANA[t.clave];
      expect(pestana, `el tipo ${t.clave} del servidor no tiene pestaña`).toBeTruthy();
      await page.getByRole('tab', { name: pestana, exact: true }).click();
      // El tipo va fijo: su título como encabezado, sin ofrecer cambiarlo, y su ficha.
      await expect(page.getByRole('heading', { name: t.titulo, exact: true })).toBeVisible();
      await expect(page.getByRole('radiogroup', { name: 'Tipo de análisis' })).toHaveCount(0);
      await expect(page.getByText(t.descripcion, { exact: false }).first()).toBeVisible();

      if (t.clave !== 'corto_plazo') {
        const anio = page.getByRole('spinbutton', { name: /Año de presentación/ }).first();
        await anio.fill('123456');
        await revisarAxe(page, FLUJO, `1_${t.clave}_anio_invalido`, testInfo);
        await captura(page, FLUJO, `1_${t.clave}_anio_invalido`);
        const rango = tipos.anio_presentacion_rango;
        await anio.fill(rango ? String(rango.min) : String(new Date().getFullYear() + 1));
        await expect(anio).not.toHaveAttribute('aria-invalid', 'true');
      }

      // Cada paso lleva a su sección, con el prefijo de su pestaña, y le da el foco (2.4.3).
      const irAlPaso = page.getByRole('button', { name: 'Ir al paso' });
      if (await irAlPaso.count()) {
        await irAlPaso.first().click();
        await expect(page.locator(`[id^="${t.clave}-paso-"]:focus`)).toHaveCount(1);
      }
      await captura(page, FLUJO, `2_${t.clave}_pasos`);
      await revisarAxe(page, FLUJO, `2_${t.clave}_pasos`, testInfo);
    }
    sinRedNiErrores(externas, errores);
  });

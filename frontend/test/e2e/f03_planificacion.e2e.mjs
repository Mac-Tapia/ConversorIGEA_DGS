/**
 * F03 Planificación regulatoria (Plan Maestro V1, §31.6; F-12): elegir el tipo de análisis con el teclado entre los
 * que da el servidor (ninguno fijo en la prueba), ver su ficha, escribir el año de presentación con su aviso si no
 * vale y seguir sus pasos hasta la sección que toca. Sin DIgSILENT ni red. axe en cada estado.
 */
import { test, expect, captura, revisarAxe, sinRedNiErrores } from './comun.mjs';

const FLUJO = 'F03_planificacion';

test('F03 planificación: los tipos del servidor se eligen con flechas, con su ficha, su año y sus pasos',
  async ({ web: page, externas, errores }, testInfo) => {
    // Lo que el servidor ofrece, leído de la misma API que usa la página (con la cookie de la sesión).
    const respuesta = await page.request.get('/api/planeamiento/tipos');
    expect(respuesta.ok(), `GET /api/planeamiento/tipos: ${respuesta.status()}`).toBeTruthy();
    const tipos = await respuesta.json();
    await page.getByRole('tab', { name: 'Cargas en DIgSILENT' }).click();
    const titulos = tipos.tipos.map((t) => t.titulo);
    expect(titulos.length, 'el servidor ofrece algún tipo de análisis').toBeGreaterThan(0);

    const grupo = page.getByRole('radiogroup', { name: 'Tipo de análisis' });
    await expect(grupo.getByRole('radio')).toHaveText(titulos);
    // Ninguno elegido de antemano (072:RF-29).
    await expect(grupo.locator('[aria-checked="true"]')).toHaveCount(0);
    await revisarAxe(page, FLUJO, '0_sin_tipo', testInfo);

    // Con las flechas se recorre y se elige, como un grupo de opciones nativo (WCAG 2.1.1).
    await grupo.getByRole('radio').first().focus();
    await page.keyboard.press('Space');
    await expect(grupo.getByRole('radio').first()).toHaveAttribute('aria-checked', 'true');
    if (titulos.length > 1) {
      await page.keyboard.press('ArrowRight');
      await expect(grupo.getByRole('radio').nth(1)).toHaveAttribute('aria-checked', 'true');
      await expect(grupo.getByRole('radio').nth(1)).toBeFocused();
      await page.keyboard.press('ArrowLeft');
      await expect(grupo.getByRole('radio').first()).toHaveAttribute('aria-checked', 'true');
    }

    // Un tipo con año de presentación (el primero que no sea de corto plazo, si el servidor lo ofrece).
    const conAnio = tipos.tipos.find((t) => t.clave !== 'corto_plazo');
    if (conAnio) {
      await grupo.getByRole('radio', { name: conAnio.titulo, exact: true }).click();
      await expect(page.getByText(conAnio.descripcion, { exact: false }).first()).toBeVisible();
      const anio = page.getByRole('spinbutton', { name: /Año de presentación/ });
      await anio.fill('123456');
      await revisarAxe(page, FLUJO, '1_anio_invalido', testInfo);
      await captura(page, FLUJO, '1_anio_invalido');
      const rango = tipos.anio_presentacion_rango;
      const valido = rango ? String(rango.min) : String(new Date().getFullYear() + 1);
      await anio.fill(valido);
      await expect(anio).not.toHaveAttribute('aria-invalid', 'true');
    }

    // Cada paso lleva a su sección y le da el foco (2.4.3).
    const irAlPaso = page.getByRole('button', { name: 'Ir al paso' });
    if (await irAlPaso.count()) {
      await irAlPaso.first().click();
      await expect(page.locator('[id^="paso-"]:focus')).toHaveCount(1);
    }
    await captura(page, FLUJO, '2_tipo_y_pasos');
    await revisarAxe(page, FLUJO, '2_tipo_y_pasos', testInfo);
    sinRedNiErrores(externas, errores);
  });

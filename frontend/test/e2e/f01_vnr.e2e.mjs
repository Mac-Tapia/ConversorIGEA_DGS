/**
 * F01 VNR universal (Plan Maestro V1, §31.6; F-12): elegir la entrada VNR-GIS con el teclado, subir un paquete,
 * cargarlo y ver sus alimentadores, sin suponer el CRS ni la empresa y sin salir a la red. axe en cada estado.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, captura, revisarAxe, sinRedNiErrores } from './comun.mjs';
import { ALIMENTADORES, escribirPaquete } from './vnr_sintetico.mjs';

const FLUJO = 'F01_vnr';

test('F01 VNR: paquete sintético cargado por teclado, con sus alimentadores y sin infracciones graves de axe',
  async ({ web: page, externas, errores }, testInfo) => {
    await revisarAxe(page, FLUJO, '0_inicio', testInfo);

    // 1. La alternativa de entrada es un grupo de opciones: las flechas la cambian (WCAG 2.1.1).
    const grupo = page.getByRole('radiogroup', { name: 'Alternativa de entrada' });
    const opciones = grupo.getByRole('radio');
    await expect(opciones).toHaveCount(3);
    const vnr = grupo.getByRole('radio', { name: 'VNR-GIS' });
    await opciones.first().focus();
    for (let i = 0; i < 3 && (await vnr.getAttribute('aria-checked')) !== 'true'; i++) {
      await page.keyboard.press('ArrowRight');
      // Cada flecha cambia la opción en el servidor: se espera a que el grupo vuelva a estar activo antes de la siguiente.
      await page.waitForTimeout(300);
      await expect(grupo.getByRole('radio', { disabled: true })).toHaveCount(0);
    }
    await expect(vnr).toHaveAttribute('aria-checked', 'true');
    await expect(vnr).toBeFocused();
    await expect(page.getByText('Paquete oficial VNR-GIS')).toBeVisible();
    await revisarAxe(page, FLUJO, '1_modo_vnr', testInfo);

    // 2. El paquete va a su casilla; el servidor lo reconoce por su contenido.
    const paquete = escribirPaquete(join(testInfo.outputDir, 'VNR_sintetico.zip'));
    const casilla = page.locator('.slot').filter({ hasText: 'Paquete o base VNR-GIS' });
    await casilla.locator('input[type="file"]').setInputFiles(paquete);
    await expect(casilla.locator('.slot-name')).toHaveText('VNR_sintetico.zip');
    await expect(page.getByText(/Paquete VNR-GIS listo/)).toBeVisible();
    await captura(page, FLUJO, '2_paquete_asignado');

    // 3. Cargar es un trabajo: el resumen llega en un diálogo que se cierra con Escape y devuelve el foco.
    const cargar = page.getByRole('button', { name: 'Cargar / listar alimentadores' });
    await cargar.focus();
    await page.keyboard.press('Enter');
    const resumen = page.getByRole('dialog').filter({ hasText: 'Alimentadores leídos' });
    await expect(resumen).toBeVisible({ timeout: 120_000 });
    await expect(resumen).toContainText(`Alimentadores leídos: ${ALIMENTADORES.length}`);
    await revisarAxe(page, FLUJO, '3_resumen_carga', testInfo);
    await page.keyboard.press('Escape');
    await expect(resumen).toBeHidden();

    // 4. Los alimentadores del paquete, todos y solo ellos, en la tabla.
    // En el paquete sintético el nombre y el código del alimentador coinciden: dos celdas de la misma fila.
    for (const a of ALIMENTADORES) await expect(page.getByRole('cell', { name: a, exact: true }).first()).toBeVisible();
    // Con la entrega cargada aparecen las pestañas que la necesitan; siguen siendo pestañas de teclado.
    await expect(page.getByRole('tab', { name: 'Resultados' })).toBeVisible();
    await captura(page, FLUJO, '4_alimentadores');
    await revisarAxe(page, FLUJO, '4_alimentadores', testInfo);
    sinRedNiErrores(externas, errores);
  });

test('F01 VNR: un fichero que no es un paquete se rechaza con un mensaje claro, sin traza ni código HTTP',
  async ({ web: page, externas, errores }, testInfo) => {
    await page.getByRole('radio', { name: 'VNR-GIS' }).click();
    const roto = join(testInfo.outputDir, 'no_es_un_paquete.zip');
    mkdirSync(testInfo.outputDir, { recursive: true }); // Playwright la crea solo al adjuntar; aquí se escribe antes
    writeFileSync(roto, 'esto no es un zip');
    const casilla = page.locator('.slot').filter({ hasText: 'Paquete o base VNR-GIS' });
    await casilla.locator('input[type="file"]').setInputFiles(roto);
    // O lo rechaza la subida (aviso) o lo marca la casilla, o lo dice al cargar; en los tres casos, en español.
    const mensaje = page.locator('.toast, .slot .alert, [role="alert"], dialog[open]').filter({ hasText: /\S/ }).first();
    try {
      await expect(mensaje).toBeVisible({ timeout: 15_000 });
    } catch {
      // La subida lo aceptó: entonces lo tiene que decir la carga.
      await page.getByRole('button', { name: 'Cargar / listar alimentadores' }).click();
      await expect(mensaje).toBeVisible({ timeout: 120_000 });
    }
    const texto = await mensaje.innerText();
    expect(texto).not.toMatch(/Traceback|Error 500|Internal Server Error|undefined|\[object Object\]/);
    await captura(page, FLUJO, '9_paquete_invalido');
    await revisarAxe(page, FLUJO, '9_paquete_invalido', testInfo);
    // El error esperado no es un fallo de la página: solo cuentan los de JavaScript, no la respuesta 4xx de la API.
    sinRedNiErrores(externas, errores.filter((e) => !/status of 4\d\d/.test(e)));
  });

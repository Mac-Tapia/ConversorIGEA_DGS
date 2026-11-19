/**
 * F04 Agente/IA (Plan Maestro V1, §31.6; F-12): escribir una solicitud, recibir la respuesta con su plan y, si el plan
 * escribe en DIgSILENT o en disco, que espere la confirmación del operador antes de ejecutar nada. Todo en esta
 * máquina y sin red. axe en cada estado.
 *
 * Necesita el modelo del intérprete en el servidor. Si la máquina no lo tiene, CSG_E2E_SIN_MODELO=1 acepta en su
 * lugar un error claro en español; sin esa variable, una orden sin respuesta es un fallo.
 */
import { test, expect, captura, revisarAxe, sinRedNiErrores } from './comun.mjs';

const FLUJO = 'F04_asistente';
const SIN_MODELO = process.env.CSG_E2E_SIN_MODELO === '1';
const ILEGIBLE = /Traceback|Error 500|Internal Server Error|undefined|\[object Object\]/;

/** Escribe la orden por teclado (Ctrl+Intro la envía) y devuelve la tarjeta de su respuesta ya interpretada. */
async function ordenar(page, texto) {
  const caja = page.getByRole('textbox', { name: 'Orden' });
  await caja.fill(texto);
  await caja.press('Control+Enter');
  const tarjeta = page.locator('article').filter({ hasText: texto }).first();
  await expect(tarjeta).toBeVisible();
  await expect(tarjeta).not.toContainText('Interpretando la orden…', { timeout: 150_000 });
  return tarjeta;
}

/** 027:RF-73, RF-75: la memoria del espacio se abre, enseña sus turnos y, si los hay, se olvida. */
async function memoria(page, testInfo, ordenes) {
  await page.getByText('Memoria de la conversación', { exact: true }).click();
  const panel = page.locator('details').filter({ has: page.getByText('Memoria de la conversación', { exact: true }) });
  await expect(panel).toContainText(/\d+ turno\(s\)/);
  expect(await panel.innerText()).not.toMatch(ILEGIBLE);
  for (const o of ordenes) await expect(panel).toContainText(o);
  await revisarAxe(page, FLUJO, '3_memoria', testInfo);
  if (ordenes.length) {
    await panel.getByRole('button', { name: 'Olvidar la conversación', exact: true }).click();
    await expect(panel).toContainText('0 turno(s)');
  }
}

test('F04 asistente: una consulta se responde sin pedir confirmación y una orden que escribe la espera',
  async ({ web: page, externas, errores }, testInfo) => {
    await page.getByRole('tab', { name: /Asistente/ }).click();
    await expect(page.getByRole('textbox', { name: 'Orden' })).toBeVisible();
    await revisarAxe(page, FLUJO, '0_consola', testInfo);

    const consulta = await ordenar(page, '¿cómo se calibra una barra sin medidor?');
    const fallo = consulta.locator('.alert-error');
    if (await fallo.count()) {
      const texto = await fallo.first().innerText();
      expect(texto).not.toMatch(ILEGIBLE);
      expect(SIN_MODELO, `la consulta no se interpretó: «${texto}» (CSG_E2E_SIN_MODELO=1 si la máquina no tiene modelo)`).toBe(true);
      await captura(page, FLUJO, '1_sin_modelo');
      await memoria(page, testInfo, []);
      sinRedNiErrores(externas, errores);
      return;
    }
    // Una consulta solo lee: ningún botón de confirmar ni trabajo lanzado por ella.
    await expect(consulta.getByRole('button', { name: 'Confirmar y ejecutar' })).toHaveCount(0);
    await captura(page, FLUJO, '1_consulta');
    await revisarAxe(page, FLUJO, '1_consulta', testInfo);

    // Una orden que escribiría en DIgSILENT no se ejecuta sola: espera a «Confirmar y ejecutar» (o dice qué falta).
    const orden = await ordenar(page, 'calibra el sistema de prueba con julio de 2026');
    const confirmar = orden.getByRole('button', { name: 'Confirmar y ejecutar' });
    if (await confirmar.count()) {
      await expect(confirmar).toBeVisible();
      await expect(orden).not.toContainText('Trabajo «');
    } else {
      // Sin plan listo (falta el sistema o el periodo): lo dice en una frase, y no hay trabajo.
      await expect(orden).not.toContainText('Trabajo «');
      expect(await orden.innerText()).not.toMatch(ILEGIBLE);
    }
    await captura(page, FLUJO, '2_orden_que_escribe');
    await revisarAxe(page, FLUJO, '2_orden_que_escribe', testInfo);
    await memoria(page, testInfo, ['¿cómo se calibra una barra sin medidor?', 'calibra el sistema de prueba con julio de 2026']);
    sinRedNiErrores(externas, errores);
  });

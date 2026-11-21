/**
 * F04 Agente/IA (Plan Maestro V1, §31.6; F-12): escribir una solicitud, recibir la respuesta con su plan y, si el plan
 * escribe en DIgSILENT o en disco, que espere la confirmación del operador antes de ejecutar nada. Todo en esta
 * máquina y sin red. axe en cada estado.
 *
 * Necesita el modelo del intérprete en el servidor. Si la máquina no lo tiene, CSG_E2E_SIN_MODELO=1 acepta en su
 * lugar un error claro en español; sin esa variable, una orden sin respuesta es un fallo.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, captura, revisarAxe, sinRedNiErrores } from './comun.mjs';

const FLUJO = 'F04_asistente';
const SIN_MODELO = process.env.CSG_E2E_SIN_MODELO === '1';
const ILEGIBLE = /Traceback|Error 500|Internal Server Error|undefined|\[object Object\]/;

/** Escribe la orden por teclado (Ctrl+Intro la envía) y devuelve la tarjeta de su respuesta ya interpretada. */
async function ordenar(page, texto) {
  const caja = page.getByRole('textbox', { name: 'Orden' });
  await caja.fill(texto);
  // Un diálogo modal abierto deja inerte la página: la orden no llegaría a la caja. Que falle aquí, con su porqué.
  await expect(caja, 'la caja «Orden» no recibió la orden (¿queda un diálogo abierto?)').toHaveValue(texto);
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
  await expect(panel).toContainText(/\d+\s+turnos?/);
  expect(await panel.innerText()).not.toMatch(ILEGIBLE);
  for (const o of ordenes) await expect(panel).toContainText(o);
  await revisarAxe(page, FLUJO, '3_memoria', testInfo);
  if (ordenes.length) {
    await panel.getByRole('button', { name: 'Olvidar la conversación', exact: true }).click();
    await expect(panel).toContainText(/(^|[^0-9])0\s+turnos(?![a-z])/);
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

    // Las entradas (026:RF-42) van en su propio recorrido, más abajo: aquí, sin modelo, nunca se llegaba a ellas.
    await memoria(page, testInfo, ['¿cómo se calibra una barra sin medidor?', 'calibra el sistema de prueba con julio de 2026']);
    sinRedNiErrores(externas, errores);
  });

// 027:RF-72 (T33) y 026:RF-48 (T22): «Ver las etapas» del proyecto entero no necesita el intérprete: los módulos sin su
// dato (PIT, VAD, VNR) se saltan con su motivo y el asistente propone la siguiente etapa con el porqué.
test('F04 asistente: el proyecto entero enseña los módulos que se saltan con su motivo y el camino propuesto',
  async ({ web: page, externas, errores }, testInfo) => {
    await page.getByRole('tab', { name: /Asistente/ }).click();
    const titulo = page.getByText('Proyecto desde cero (el agente hace todas las etapas)', { exact: true });
    await titulo.click();
    const panel = page.locator('details').filter({ has: titulo });
    await panel.getByRole('textbox', { name: 'Sistema eléctrico' }).fill('Sistema de prueba');
    await panel.getByRole('textbox', { name: 'Periodo' }).fill('2026-07');
    await panel.getByRole('button', { name: 'Ver las etapas', exact: true }).click();
    for (const modulo of ['pit', 'vad', 'vnr']) {
      const fila = panel.locator('li').filter({ has: page.locator('b', { hasText: new RegExp(`^${modulo}$`) }) });
      await expect(fila).toContainText(/se omitirá: \S/);
    }
    await expect(panel).toContainText(/Siguiente etapa|Nada que hacer/);
    expect(await panel.innerText()).not.toMatch(ILEGIBLE);
    await captura(page, FLUJO, '4_proyecto_entero');
    await revisarAxe(page, FLUJO, '4_proyecto_entero', testInfo);
    sinRedNiErrores(externas, errores);
  });

// 026:RF-42 (T16): las entradas desde el asistente, en su propio recorrido para que siempre llegue a ellas: la orden la
// reconoce su frase, también sin el modelo del intérprete (la consulta de arriba sí lo necesita). Cada fichero de esta
// máquina espera «Confirmar y ejecutar», no lanza nada antes y, tras el clic, queda en su casilla por la misma subida que
// la pestaña de entradas; lo que la casilla rechaza no entra y la vigente se queda; el libro de la empresa entra en sus
// fuentes con su clase y su año; sin ruta, o de la nube, el plan dice qué falta (de la nube elige el operador en el
// selector de su cuenta) y no ofrece confirmar.
const RED_TXT = ['[NODE]', 'FORMAT_NODE=NodeID,X,Y', 'N1,0,0', '[SECTION]', 'FORMAT_SECTION=SectionID', ''].join('\n');

/** La orden, confirmada, hasta que su trabajo termina; devuelve la tarjeta. */
async function confirmarOrden(page, texto, esperado) {
  const tarjeta = await ordenar(page, texto);
  const confirmar = tarjeta.getByRole('button', { name: 'Confirmar y ejecutar', exact: true });
  await expect(confirmar).toBeVisible();
  await expect(tarjeta).not.toContainText('Trabajo «');
  expect(await tarjeta.innerText()).not.toMatch(ILEGIBLE);
  await confirmar.click();
  await expect(tarjeta).toContainText(esperado, { timeout: 120_000 });
  await expect(tarjeta.getByRole('button', { name: 'Confirmar y ejecutar', exact: true })).toHaveCount(0);
  return tarjeta;
}

/** La orden que no está lista: dice lo que falta y no ofrece confirmar ni lanza nada. */
async function sinConfirmar(page, texto, falta) {
  const tarjeta = await ordenar(page, texto);
  await expect(tarjeta).toContainText(falta);
  await expect(tarjeta.getByRole('button', { name: 'Confirmar y ejecutar', exact: true })).toHaveCount(0);
  await expect(tarjeta).not.toContainText('Trabajo «');
  expect(await tarjeta.innerText()).not.toMatch(ILEGIBLE);
  return tarjeta;
}

test('F04 asistente: cada fichero de la máquina entra en su casilla tras confirmar y el libro de la empresa en sus fuentes',
  async ({ web: page, externas, errores }, testInfo) => {
    // Los ficheros «de la máquina», en la carpeta de salida de este recorrido (Playwright la vacía en cada corrida).
    const carpeta = testInfo.outputPath('entradas');
    mkdirSync(carpeta, { recursive: true });
    const ficheros = { red: 'red_f04.txt', loads: 'carga_f04.txt', equipment: 'equipos_f04.txt' };
    for (const nombre of Object.values(ficheros)) writeFileSync(join(carpeta, nombre), RED_TXT);
    const base = join(carpeta, 'base_f04.mdb');
    writeFileSync(base, Buffer.concat([Buffer.from('\x00\x01\x00\x00Standard Jet DB\x00', 'latin1'), Buffer.alloc(64)]));
    const libro = join(carpeta, 'sicodi_f04.xlsx');
    writeFileSync(libro, 'libro sintetico de prueba');
    await page.getByRole('tab', { name: /Asistente/ }).click();
    const espacio = await page.locator('.ws-id span[title]').getAttribute('title');
    const casillas = async () => (await (await page.request.get(`/api/workspaces/${espacio}`)).json()).inputs ?? {};

    await confirmarOrden(page, `asigna "${join(carpeta, ficheros.red)}" a la casilla de la red`,
      '«red_f04.txt» entró en la casilla «RED');
    await captura(page, FLUJO, '5_asignar_red');
    await revisarAxe(page, FLUJO, '5_asignar_red', testInfo);
    await confirmarOrden(page, `pon "${join(carpeta, ficheros.loads)}" en la entrada de las cargas`,
      '«carga_f04.txt» entró en la casilla «CARGA');
    await confirmarOrden(page, `asigna "${join(carpeta, ficheros.equipment)}" a la casilla de los equipos`,
      '«equipos_f04.txt» entró en la casilla «EQUIPOS');
    const tras = await casillas();
    for (const [casilla, nombre] of Object.entries(ficheros)) {
      expect(String(tras[casilla]?.path ?? ''), `la casilla ${casilla}`).toMatch(new RegExp(`${nombre.replace('.', '\\.')}$`));
    }

    // Lo que la casilla no admite no entra: la orden se confirma, su trabajo falla con su motivo y la red sigue siendo la
    // de antes.
    const rechazo = await ordenar(page, `asigna "${base}" a la casilla de la red`);
    await rechazo.getByRole('button', { name: 'Confirmar y ejecutar', exact: true }).click();
    await expect(rechazo.locator('.alert-error')).toContainText('base Access', { timeout: 120_000 });
    expect(await rechazo.innerText()).not.toMatch(ILEGIBLE);
    expect(String((await casillas()).red?.path ?? '')).toMatch(/red_f04\.txt$/);
    // El trabajo fallido abre además su diálogo de error (081:RF-24), modal: el operador lo lee y lo acepta antes de
    // escribir la orden siguiente (ordenar() comprueba que la caja la recibe).
    const dialogo = page.getByRole('dialog', { name: 'Asistente · asignar_entrada — error' });
    await expect(dialogo).toBeVisible();
    await expect(dialogo).toContainText('base Access');
    expect(await dialogo.innerText()).not.toMatch(ILEGIBLE);
    await captura(page, FLUJO, '5_asignar_rechazada');
    await dialogo.getByRole('button', { name: 'Aceptar', exact: true }).click();
    await expect(dialogo).toHaveCount(0);

    // El libro de la empresa, a sus fuentes con su clase y su año.
    await confirmarOrden(page, `sube el sicodi "${libro}" del 2025 a las fuentes de la empresa`,
      'quedó en las fuentes de la empresa como el SICODI del 2025');
    const fuentes = (await (await page.request.get(`/api/workspaces/${espacio}/fuentes?clase=sicodi`)).json()).fuentes ?? [];
    expect(fuentes.map((f) => [f.nombre, f.periodo, f.vigente])).toContainEqual(['sicodi_f04.xlsx', '2025', true]);

    // Sin la ruta del fichero, o desde la nube, no hay nada que confirmar: el plan dice qué falta.
    await sinConfirmar(page, 'asigna el fichero CARGA.txt de esta maquina a la casilla de cargas', 'su ruta entre comillas');
    await sinConfirmar(page, 'asigna desde google drive el libro a la casilla de la red', 'selector');
    await captura(page, FLUJO, '5_asignar_sin_confirmar');
    await revisarAxe(page, FLUJO, '5_asignar_sin_confirmar', testInfo);
    sinRedNiErrores(externas, errores);
  });

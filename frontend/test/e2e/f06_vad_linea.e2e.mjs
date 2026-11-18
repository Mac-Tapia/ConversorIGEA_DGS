/**
 * F06 Estudio VAD de punta a punta (108 T30, RF-26): en un navegador real, crear el estudio, subir un caso sintético de
 * dos sistemas, armar la línea del VAD y el Informe Definitivo, todo por la pestaña. La línea enseña el estado de cada
 * paso, con el motivo del que no tiene entrada; el Informe Definitivo da cada documento escrito o su hueco nombrado, y
 * cada documento escrito se descarga. El caso sale del registro del TdR real con valores de sus propias fórmulas
 * (tests/e2e_vad_caso.py): ningún dato de una empresa. Sin DIgSILENT ni red; axe en cada estado.
 */
import { execFileSync } from 'node:child_process';
import { rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, captura, comprobar_sin_citas, revisarAxe, sinRedNiErrores } from './comun.mjs';
import { pythonServidor } from './entorno.mjs';

const FLUJO = 'F06_vad_linea';
const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const TDR = 'rcd-174-2025-os-cd';
// Los pasos de la línea (vad/linea.py): la empresa modelo desde la red y el caso, y lo que se encadena tras ella.
const PASOS = ['modelo_rural', 'dimensionamiento', 'costo_estandar', 'resultados', 'pide', 'calidad', 'explotacion',
  'tablas', 'informes'];
// El caso trae resultados de S1 y S2, la explotación de S1 y nada del PIDE, la calidad, la red ni el sustento.
const CON_ENTRADA = { resultados: /^(OK|INCOMPLETO)$/, explotacion: /^OK$/, tablas: /^OK$/, informes: /^OK$/ };

// El perfil sintético que carga el recorrido: se quita al terminar, pase o falle, para no dejarlo a los demás.
let rutaPerfil = null;
test.afterEach(() => {
  if (rutaPerfil) rmSync(rutaPerfil, { force: true });
  rutaPerfil = null;
});

/** Cierra el resumen de un trabajo largo si se abrió al terminar (Escape, como el operador). */
async function cerrarResumen(page) {
  const abierto = page.locator('dialog[open]');
  await abierto.first().waitFor({ state: 'visible', timeout: 3_000 }).catch(() => undefined);
  if (await abierto.count()) {
    await page.keyboard.press('Escape');
    await expect(abierto).toHaveCount(0);
  }
}

test('F06 VAD: un caso de dos sistemas recorre la línea por la pestaña hasta el Informe Definitivo',
  async ({ web: page, externas, errores }, testInfo) => {
    test.setTimeout(600_000);
    const caso = join(testInfo.outputDir, 'caso_vad_dos_sistemas.zip');
    execFileSync(pythonServidor(RAIZ), [join(RAIZ, 'tests', 'e2e_vad_caso.py'), caso],
      { cwd: RAIZ, env: { ...process.env, PYTHONPATH: join(RAIZ, 'src'), PYTHONUTF8: '1' } });

    // 0. El estudio es de la empresa del perfil: el operador carga uno en «Perfil de la empresa», aquí el de la empresa
    // ficticia de config/perfiles (sin datos de ninguna real). La web de
    // los recorridos guarda su carpeta entre corridas, así que al terminar se quita y nada cambia para los demás.
    const antes = await (await page.request.get('/api/perfil')).json();
    expect(antes.existe, 'la web de los recorridos empieza sin perfil de empresa').toBeFalsy();
    const perfil = join(testInfo.outputDir, 'perfil_sintetico.json');
    writeFileSync(perfil, JSON.stringify({ perfil: 'ficticia' }), 'utf8');
    const tarjeta = page.locator('section.card').filter({ has: page.getByRole('heading', { name: 'Perfil de la empresa' }) });
    await tarjeta.getByLabel('Perfil (JSON)').setInputFiles(perfil);
    await tarjeta.getByRole('button', { name: 'Cargar perfil' }).click();
    await expect(tarjeta).toContainText('Perfil activo en');
    rutaPerfil = (await (await page.request.get('/api/perfil')).json()).ruta;

    // 1. La pestaña, sin estudio todavía.
    await page.getByRole('tab', { name: 'Estudio VAD' }).click();
    await expect(page.getByText('Aún no hay un estudio del VAD en este espacio.')).toBeVisible();
    await revisarAxe(page, FLUJO, '0_sin_estudio', testInfo);

    // 2. Crear el estudio: grupo, periodo y versión del TdR, como el operador.
    await page.getByLabel('Grupo').fill('1');
    await page.getByLabel('Periodo').fill('2041-2045');
    await page.getByLabel('Versión del TdR').fill(TDR);
    await page.getByRole('button', { name: 'Crear estudio' }).click();
    const empresa = page.getByRole('region', { name: 'Empresa modelo' });
    await expect(empresa).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Estudio' })).toContainText('G1 2041-2045');

    // 3. El caso de dos sistemas a su casilla y armar: es un trabajo del motor.
    await empresa.locator('input[type="file"]').setInputFiles(caso);
    await expect(empresa).toContainText('caso_vad_dos_sistemas.zip');
    await revisarAxe(page, FLUJO, '1_caso_elegido', testInfo);
    await empresa.getByRole('button', { name: 'Armar la empresa modelo' }).click();
    const linea = page.getByRole('region', { name: 'Línea del VAD' });
    await expect(linea).toBeVisible({ timeout: 300_000 });
    await cerrarResumen(page);

    // 4. Los dos sistemas de la empresa modelo y cada paso de la línea con su estado; sin entrada, su motivo.
    for (const s of ['S1', 'S2']) {
      await expect(empresa.getByRole('listitem').filter({ hasText: new RegExp(`^${s} · `) })).toHaveCount(1);
    }
    const pasos = linea.getByRole('listitem');
    await expect(pasos).toHaveCount(PASOS.length);
    for (const p of PASOS) {
      const fila = pasos.filter({ hasText: new RegExp(`^${p} · `) });
      await expect(fila, `el paso ${p} en la pestaña`).toHaveCount(1);
      const [, estado, motivo = ''] = (await fila.innerText()).split(' · ');
      if (CON_ENTRADA[p]) expect(estado, `estado de ${p}`).toMatch(CON_ENTRADA[p]);
      else {
        expect(estado, `${p} sin su entrada en el caso`).toBe('SIN_ENTRADA');
        expect(motivo.trim(), `motivo de ${p}`).not.toBe('');
      }
    }
    await captura(page, FLUJO, '2_linea');
    await revisarAxe(page, FLUJO, '2_linea', testInfo);

    // 5. El Informe Definitivo: sin observaciones pendientes, se arma desde la pestaña.
    const informe = page.getByRole('region', { name: 'Informe Definitivo' });
    const armar = informe.getByRole('button', { name: 'Armar el Informe Definitivo' });
    await expect(armar).toBeEnabled();
    await armar.click();
    const documentos = informe.getByRole('listitem');
    await expect(documentos.first()).toBeVisible({ timeout: 300_000 });
    await cerrarResumen(page);

    // 6. Cada documento escrito (se descarga) o su hueco nombrado, tal como lo dejó el servidor.
    const wid = await page.locator('.ws-id span[title]').getAttribute('title');
    const lista = await (await page.request.get(`/api/workspaces/${wid}/vad/estudios`)).json();
    const eid = lista.estudios[0].id;
    const detalle = await (await page.request.get(`/api/workspaces/${wid}/vad/${eid}`)).json();
    const docs = detalle.informe_definitivo.documentos;
    expect(docs.length, 'el Informe Definitivo nombra sus documentos').toBeGreaterThan(0);
    await expect(documentos).toHaveCount(docs.length);
    let escritos = 0;
    for (const doc of docs) {
      if (doc.ruta_relativa) {
        const nombre = doc.ruta_relativa.split('/').pop();
        // El documento se nombra junto a su botón: con solo «Guardar en…» el operador no sabría cuál es cuál.
        const fila = documentos.filter({ hasText: doc.documento });
        await expect(fila.getByRole('button', { name: `Guardar ${nombre} en una carpeta` })).toBeVisible();
        const ruta = doc.ruta_relativa.split('/').map(encodeURIComponent).join('/');
        const r = await page.request.get(`/api/workspaces/${wid}/files/${ruta}?download=1`);
        expect(r.status(), `descarga de ${doc.ruta_relativa}`).toBe(200);
        expect((await r.body()).length, `${doc.ruta_relativa} no está vacío`).toBeGreaterThan(0);
        escritos += 1;
      } else {
        expect(doc.motivo, `hueco nombrado de ${doc.documento}`).toBeTruthy();
        await expect(documentos.filter({ hasText: `${doc.documento}: ${doc.motivo}` })).toHaveCount(1);
      }
    }
    expect(escritos, 'la línea deja escritos documentos del Informe Definitivo').toBeGreaterThan(0);
    // El libro de las tablas que dejó la línea ya no es un hueco del Informe Definitivo.
    expect(detalle.informe_definitivo.huecos.join('\n')).not.toContain('sin el libro de las tablas de resultados');
    await captura(page, FLUJO, '3_informe_definitivo');
    await revisarAxe(page, FLUJO, '3_informe_definitivo', testInfo);
    await comprobar_sin_citas(page, 'la pestaña del VAD');
    sinRedNiErrores(externas, errores);
  });

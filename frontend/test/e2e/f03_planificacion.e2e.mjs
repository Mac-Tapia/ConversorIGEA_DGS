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
// 100:RF-12: la pestaña de un estudio puede anunciar «Sin validar» o «No disponible» tras su nombre.
const pestanaDe = (page, nombre) => page.getByRole('tab', { name: new RegExp(`^${nombre}( Sin validar| No disponible)?$`) });

test('F03 planificación: cada tipo del servidor en su pestaña, con su ficha, su año y sus pasos; «Cargas» no lo repite',
  async ({ web: page, externas, errores }, testInfo) => {
    // Lo que el servidor ofrece, leído de la misma API que usa la página (con la cookie de la sesión).
    const respuesta = await page.request.get('/api/planeamiento/tipos');
    expect(respuesta.ok(), `GET /api/planeamiento/tipos: ${respuesta.status()}`).toBeTruthy();
    const tipos = await respuesta.json();
    expect(tipos.tipos.length, 'el servidor ofrece algún tipo de análisis').toBeGreaterThan(0);

    // 072:RF-43: «Cargas en DIgSILENT» sigue entera, sin el selector de los tipos que ya son pestañas.
    await page.getByRole('tab', { name: 'Cargas en DIgSILENT', exact: true }).click();
    await expect(page.getByRole('radiogroup', { name: 'Tipo de análisis' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '1 · Proyecto de DIgSILENT' })).toBeVisible();
    await revisarAxe(page, FLUJO, '0_cargas_sin_selector', testInfo);

    for (const t of tipos.tipos) {
      const pestana = PESTANA[t.clave];
      expect(pestana, `el tipo ${t.clave} del servidor no tiene pestaña`).toBeTruthy();
      await pestanaDe(page, pestana).click();
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

test('F03 072:RF-45 el proyecto de DIgSILENT elegido en Cargas vale en Corto plazo y PIDE, y queda en el espacio',
  async ({ web: page, externas, errores }, testInfo) => {
    // Sin DIgSILENT en esta prueba: solo la lista guardada de «Leer proyectos» se da hecha (lo que leería DIgSILENT).
    // Elegir y guardar el proyecto va al servidor de verdad (PUT /options, workspace.json).
    const inventario = { folder: 'ConverterSmartGrid', projects: [
      { name: 'P1', path: 'Prueba/P1', feeders: ['F1', 'F2'] }, { name: 'P2', path: 'Prueba/P2', feeders: ['F3'] }] };
    await page.route('**/powerfactory/projects', (r) => (r.request().method() === 'GET' ? r.fulfill({ json: inventario }) : r.continue()));
    const wid = await page.locator('.ws-id span[title]').getAttribute('title');
    // Las pestañas ya montadas pidieron la lista antes de la ruta: se recarga para que todas la lean con ella.
    await page.reload({ waitUntil: 'networkidle' });
    await expect(page.locator('.ws-id span[title]')).toHaveAttribute('title', wid ?? '');
    const panel = () => page.locator('[role="tabpanel"]:not([hidden])');
    const proyecto = () => panel().getByLabel(/^Proyecto \(/);
    const opciones = async () => (await (await page.request.get(`/api/workspaces/${wid}`)).json()).options;

    await page.getByRole('tab', { name: 'Cargas en DIgSILENT', exact: true }).click();
    await expect(proyecto()).toBeVisible();
    await proyecto().selectOption('Prueba/P2');
    await expect.poll(async () => (await opciones()).pf_proyecto_elegido, { message: 'el servidor guarda el proyecto' }).toBe('Prueba/P2');
    expect((await opciones()).pf_alimentadores_elegidos).toEqual(['F3']);

    // Las otras pestañas lo tienen elegido, sin volver a elegirlo.
    for (const nombre of ['Corto plazo', 'PIDE']) {
      await pestanaDe(page, nombre).click();
      await expect(proyecto(), `${nombre}: el proyecto del espacio`).toHaveValue('Prueba/P2');
    }
    // Y sigue tras recargar la página: es del espacio, no del navegador.
    await page.reload({ waitUntil: 'networkidle' });
    await pestanaDe(page, 'PIDE').click();
    await expect(proyecto(), 'tras recargar').toHaveValue('Prueba/P2');
    await captura(page, FLUJO, '3_proyecto_compartido');
    await revisarAxe(page, FLUJO, '3_proyecto_compartido', testInfo);
    sinRedNiErrores(externas, errores);
  });

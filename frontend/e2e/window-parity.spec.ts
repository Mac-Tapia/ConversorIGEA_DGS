import { expect, test, type APIRequestContext } from '@playwright/test';
import { readFile } from 'node:fs/promises';

type Fixture = { files: Record<string, string> };

async function waitForJob(request: APIRequestContext, jobId: string) {
  await expect.poll(async () => {
    const response = await request.get(`/api/jobs/${jobId}`);
    return (await response.json()).status;
  }, { timeout: 30_000 }).toBe('done');
}

test('todas las ventanas web conservan el flujo operativo', async ({ page, request }) => {
  const fixtureResponse = await request.get('/__e2e__/fixture');
  expect(fixtureResponse.ok()).toBeTruthy();
  const fixture = await fixtureResponse.json() as Fixture;

  const createResponse = await request.post('/api/workspaces');
  expect(createResponse.ok()).toBeTruthy();
  const workspace = await createResponse.json();

  for (const [slot, path] of Object.entries(fixture.files)) {
    const upload = await request.post(`/api/workspaces/${workspace.id}/inputs/${slot}`, {
      multipart: { file: { name: path.split(/[\\/]/).pop()!, mimeType: 'text/plain', buffer: await readFile(path) } },
    });
    expect(upload.ok()).toBeTruthy();
  }

  const loadResponse = await request.post(`/api/workspaces/${workspace.id}/load`);
  expect(loadResponse.ok()).toBeTruthy();
  await waitForJob(request, (await loadResponse.json()).id);

  await page.addInitScript((workspaceId) => {
    localStorage.setItem('igea-dgs.workspace', workspaceId);
  }, workspace.id);
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Conversor IGEA/CYMDIST → DGS' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Entrada de datos/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Opciones de conversión' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Alimentadores/ })).toBeVisible();

  // Al reabrir el espacio, el registro recupera el trabajo de carga terminado y
  // muestra el mismo resumen operativo que veria el usuario tras pulsar Cargar.
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Aceptar' }).click();

  const tabs = ['Resultados', 'Cargas de SED', 'SED nuevas', 'Catálogo de parámetros', 'Sistema completo'];
  for (const name of tabs) await expect(page.getByRole('tab', { name })).toBeVisible();

  await page.getByRole('tab', { name: 'Cargas de SED' }).click();
  await expect(page.getByRole('heading', { name: 'Inventario de cargas' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Alimentador', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'AL01', exact: true }).first()).toBeVisible();

  await page.getByRole('checkbox', { name: 'Seleccionar AL01' }).check();
  await page.getByRole('tab', { name: 'SED nuevas' }).click();
  await expect(page.getByText(/Plantilla de creación de/)).toBeVisible();
  await page.getByRole('tab', { name: 'Catálogo de parámetros' }).click();
  await expect(page.getByRole('heading', { name: /Generar catálogo y auditar/ })).toBeVisible();
  await page.getByRole('tab', { name: 'Sistema completo' }).click();
  await expect(page.getByRole('heading', { name: 'Red unida en una sola grid' })).toBeVisible();
  await page.getByRole('tab', { name: 'Resultados' }).click();

  const slowJobResponse = await request.post(`/__e2e__/workspaces/${workspace.id}/slow-job`);
  expect(slowJobResponse.ok()).toBeTruthy();
  await expect(page.getByText('Trabajo de prueba E2E', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Registro' })).toBeVisible();
  await waitForJob(request, (await slowJobResponse.json()).id);
});

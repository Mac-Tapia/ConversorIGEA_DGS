import { expect, test, type APIRequestContext } from '@playwright/test';
import { basename } from 'node:path';

const FEEDERS = ['NA203', 'NA205', 'PE104', 'CA101'];
const inputs = {
  txt: {
    red: process.env.IGEA_RED,
    loads: process.env.IGEA_LOADS,
    equipment: process.env.IGEA_EQUIPMENT,
  },
  mdb: {
    mdb: process.env.IGEA_MDB,
    equipment_mdb: process.env.IGEA_EQUIPMENT_MDB,
  },
} as const;

async function waitForJob(request: APIRequestContext, jobId: string) {
  let final: Record<string, unknown> | undefined;
  await expect.poll(async () => {
    const response = await request.get(`/api/jobs/${jobId}`);
    final = await response.json();
    return final?.status;
  }, { timeout: 180_000 }).toBe('done');
  return final!;
}

for (const mode of ['txt', 'mdb'] as const) {
  test(`interfaz React opera con entrada real ${mode.toUpperCase()}`, async ({ page, request }) => {
    const paths = inputs[mode];
    test.skip(Object.values(paths).some((path) => !path), 'Faltan rutas reales en variables IGEA_*');

    const created = await request.post('/api/workspaces');
    expect(created.ok()).toBeTruthy();
    const workspace = await created.json();
    expect((await request.put(`/api/workspaces/${workspace.id}/options`, {
      data: { input_mode: mode, workers: 2, hoja: 'AUTO', include_geography: true, strict: true },
    })).ok()).toBeTruthy();

    for (const [slot, path] of Object.entries(paths)) {
      const assigned = await request.post(`/api/workspaces/${workspace.id}/inputs/${slot}/path`, {
        data: { path },
      });
      expect(assigned.ok()).toBeTruthy();
      const body = await assigned.json();
      expect(body.workspace.inputs[slot].sha256).toMatch(/^[a-f0-9]{64}$/);
    }

    const load = await request.post(`/api/workspaces/${workspace.id}/load`);
    expect(load.ok()).toBeTruthy();
    await waitForJob(request, (await load.json()).id);
    const conversion = await request.post(`/api/workspaces/${workspace.id}/convert`, {
      data: { feeders: FEEDERS, all: false },
    });
    expect(conversion.ok()).toBeTruthy();
    const result = await waitForJob(request, (await conversion.json()).id);
    expect((result.result as { summary: { ok: number; failed: number } }).summary).toMatchObject({ ok: 4, failed: 0 });

    await page.addInitScript((workspaceId) => {
      localStorage.setItem('igea-dgs.workspace', workspaceId);
    }, workspace.id);
    await page.goto('/');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Aceptar' }).click();
    await expect(dialog).toBeHidden();

    await expect(page.getByRole('radio', {
      name: mode === 'txt' ? 'Tres TXT de IGEA/CYMDIST' : 'Base Access (.mdb)',
    })).toHaveAttribute('aria-checked', 'true');
    for (const path of Object.values(paths)) {
      await expect(page.getByText(basename(path!), { exact: true })).toBeVisible();
    }
    await expect(page.getByText('lienzo adaptativo a escala real')).toBeVisible();

    await page.getByRole('tab', { name: 'Cargas de SED' }).click();
    await page.locator('.inventory-filters select').first().selectOption('NA203');
    const table = page.getByRole('table', { name: 'Inventario de cargas' });
    await expect(table.getByRole('cell', { name: 'NA203', exact: true }).first()).toBeVisible();
    await expect(table.getByRole('columnheader', { name: 'Name', exact: true })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: 'SED', exact: true })).toBeVisible();
  });
}


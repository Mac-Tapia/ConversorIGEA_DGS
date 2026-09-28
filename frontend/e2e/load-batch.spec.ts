import { expect, test } from '@playwright/test';


test('actualiza AL209 e IN111 con plantilla, dry-run, apply y auditoría', async ({ page, request }) => {
  const created = await request.post('/api/workspaces');
  expect(created.ok()).toBeTruthy();
  const base = await created.json();
  const workspaceId = base.id as string;
  const workspace = {
    ...base,
    loaded: true,
    loaded_at: Date.now() / 1000,
    totals: { feeders: 2, convertible_feeders: 2, stub_feeders: 0, sections: 4, customer_loads: 2, switches: 0 },
    missing_inputs: [],
    jobs: [],
  };
  const feederRows = ['AL209', 'IN111'].map((feeder) => ({
    feeder, network_id: `NETWORK_${feeder}`, nominal_kv: 22.9,
    sections: 2, loads: 1, switches: 0, convertible: true, conversion: null,
  }));

  await page.route(`**/api/workspaces/${workspaceId}`, (route) => route.fulfill({ json: workspace }));
  await page.route(`**/api/workspaces/${workspaceId}/feeders`, (route) => route.fulfill({ json: { loaded: true, feeders: feederRows } }));
  await page.route(`**/api/workspaces/${workspaceId}/outputs`, (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/workspaces/${workspaceId}/electrical-inventory**`, (route) => route.fulfill({
    json: { total: 0, offset: 0, limit: 100, filters: { feeder: null, status: null, search: null }, rows: [] },
  }));
  await page.route(`**/api/workspaces/${workspaceId}/load-batch-plan`, (route) => route.fulfill({
    json: {
      token: 'token-e2e', kind: 'cargas_lote', plan_file: 'plan.json', plan_sha256: 'hash', batch_id: 'batch-e2e',
      feeders: ['AL209', 'IN111'], summary_by_feeder: { AL209: { updates: 1 }, IN111: { updates: 1 } },
      ignored_sheets: [], blocked_feeders: {}, row_errors: [], applicable: true,
    },
  }));
  await page.route(`**/api/workspaces/${workspaceId}/load-batch-plans/token-e2e/rows**`, (route) => route.fulfill({
    json: {
      total: 2, offset: 0, limit: 100, filters: { feeder: null, status: null },
      rows: [
        { feeder: 'AL209', network_id: 'NETWORK_AL209', sed_code: 'SE_AL', status: 'actualizar', plini_mw: 0.02, qlini_mvar: 0.006, coslini: 0.958 },
        { feeder: 'IN111', network_id: 'NETWORK_IN111', sed_code: 'SE_IN', status: 'actualizar', plini_mw: 0.03, qlini_mvar: 0.009, coslini: 0.958 },
      ],
    },
  }));
  const job = (id: string, apply: boolean) => ({
    id, kind: apply ? 'load-batch-apply' : 'load-batch-dry-run', title: id,
    workspace_id: workspaceId, lane: 'powerfactory', status: 'done', progress: null,
    result: {
      status: 'PASS', run_id: id, report: `cargas/${id}/result.json`,
      artifacts: { 'result.json': `cargas/${id}/result.json`, 'result.csv': `cargas/${id}/result.csv` },
    },
    error: null, created_at: 0, started_at: 0, finished_at: 0, cancel_requested: false,
  });
  await page.route(`**/load-batch-plans/token-e2e/dry-run`, (route) => route.fulfill({ status: 202, json: job('dry-e2e', false) }));
  await page.route(`**/load-batch-plans/token-e2e/apply`, (route) => route.fulfill({ status: 202, json: job('apply-e2e', true) }));

  await page.addInitScript((id) => localStorage.setItem('igea-dgs.workspace', id), workspaceId);
  await page.goto('/');
  await page.getByRole('tab', { name: 'Cargas de SED' }).click();
  await page.getByRole('button', { name: 'Seleccionar todos' }).click();
  await expect(page.getByRole('link', { name: 'Descargar Excel' })).toHaveAttribute('href', /feeder=AL209.*feeder=IN111/);

  await page.locator('.load-batch input[type="file"]').setInputFiles({
    name: 'cargas.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('mock'),
  });
  await expect(page.getByRole('table', { name: 'Vista previa de cargas' })).toContainText('SE_AL');
  await expect(page.getByRole('button', { name: 'Aplicar en DigSILENT' })).toBeDisabled();
  await page.getByRole('button', { name: 'Ejecutar dry-run' }).click();
  await expect(page.getByText('DRY-RUN PASS')).toBeVisible();
  await page.getByRole('button', { name: 'Aplicar en DigSILENT' }).click();
  await expect(page.getByRole('link', { name: 'result.csv' })).toBeVisible();
});

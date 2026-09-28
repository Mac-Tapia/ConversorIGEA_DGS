import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Ctx, type AppCtx } from '../context';
import type { FeederRow, Job } from '../types';
import { LoadBatchPanel } from './LoadBatchPanel';


const feeders = ['AL209', 'IN111'].map((feeder) => ({
  feeder,
  network_id: `NETWORK_${feeder}`,
  nominal_kv: 22.9,
  sections: 3,
  loads: 2,
  switches: 1,
  convertible: true,
  conversion: null,
})) as FeederRow[];

function response(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function context(startJob?: AppCtx['startJob']): AppCtx {
  return {
    ws: { id: 'workspace1', loaded: true },
    feeders,
    selected: ['AL209'],
    setSelected: vi.fn(),
    active: {},
    jobs: {},
    pf: { available: true },
    run: async <T,>(fn: () => Promise<T>) => fn(),
    startJob: startJob ?? (async () => undefined),
  } as unknown as AppCtx;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});


describe('LoadBatchPanel', () => {
  it('selects one many or all feeders and downloads one consolidated template', async () => {
    const user = userEvent.setup();
    render(<Ctx.Provider value={context()}><LoadBatchPanel /></Ctx.Provider>);

    expect(screen.getByRole('checkbox', { name: 'AL209' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Seleccionar todos' }));
    expect(screen.getByRole('checkbox', { name: 'IN111' })).toBeChecked();
    const excel = screen.getByRole('link', { name: 'Descargar Excel' });
    expect(excel.getAttribute('href')).toContain('feeder=AL209');
    expect(excel.getAttribute('href')).toContain('feeder=IN111');
  });

  it('uploads repeated feeders, shows server totals and gates apply with dry-run', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.includes('/rows')) return response({
        total: 600, offset: 0, limit: 100, filters: { feeder: null, status: null },
        rows: [{ feeder: 'AL209', network_id: 'NETWORK_AL209', sed_code: 'SE01', status: 'actualizar' }],
      });
      return response({
        token: 'token1', kind: 'cargas_lote', plan_file: 'plan.json', plan_sha256: 'abc',
        batch_id: 'batch1', feeders: ['AL209', 'IN111'],
        summary_by_feeder: { AL209: { updates: 1 }, IN111: { updates: 1 } },
        ignored_sheets: [], blocked_feeders: {}, row_errors: [], applicable: true,
      });
    }));
    const done = {
      id: 'job1', status: 'done', lane: 'powerfactory', result: { status: 'PASS', artifacts: {} },
    } as Job;
    const startJob = vi.fn(async (fn: () => Promise<Job>) => {
      await fn();
      return done;
    });
    const user = userEvent.setup();
    const { container } = render(
      <Ctx.Provider value={context(startJob)}><LoadBatchPanel /></Ctx.Provider>,
    );
    await user.click(screen.getByRole('button', { name: 'Seleccionar todos' }));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['x'], 'cargas.xlsx'));

    expect(await screen.findByText('1–100 de 600')).toBeVisible();
    const form = calls.find((call) => call.url.includes('/load-batch-plan'))?.init?.body as FormData;
    expect(form.getAll('feeder')).toEqual(['AL209', 'IN111']);
    expect(screen.getByRole('button', { name: 'Aplicar en DigSILENT' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Ejecutar dry-run' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Aplicar en DigSILENT' })).toBeEnabled());
  });
});

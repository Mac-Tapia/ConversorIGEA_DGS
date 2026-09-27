import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Ctx, type AppCtx } from '../context';
import type { LoadInventoryPage, LoadInventoryRow } from '../types';
import { LoadInventoryTable } from './LoadInventoryTable';
import { LoadsTab } from './Modules';


const baseRow: LoadInventoryRow = {
  name: 'SE50033',
  class_name: 'ElmLod',
  grid: 'NA203_NA205',
  alimentador: 'NA203',
  network_id: 'NETWORK_NA203',
  sed: 'SE50033',
  section_id: 'S1',
  device_number: 'D1',
  terminal_substation: 'SE50033',
  terminal: 'SE50033_BT',
  kw: 150,
  kvar: 30,
  kva: 200,
  power_factor: 0.98,
  voltage_mt_kv: 22.9,
  voltage_bt_kv: 0.22,
  transformer_kva: 200,
  uk_pct: 4,
  copper_losses_kw: 2.35,
  core_losses_kw: 0.38,
  vector_group: 'Dyn5',
  status: 'OK',
  diagnostic: '',
  provenance: { network_id: 'NETWORK_NA203', section_id: 'S1', device_number: 'D1' },
};

function page(rows: LoadInventoryRow[], total = rows.length, offset = 0): LoadInventoryPage {
  return {
    total,
    offset,
    limit: 100,
    filters: { feeder: null, status: null, search: null },
    rows,
  };
}

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});


describe('LoadInventoryTable', () => {
  it('shows Name Grid Alimentador SED and electrical columns', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(page([baseRow]))));

    render(<LoadInventoryTable workspaceId="abcdef12" selectedFeeders={['NA203']} />);

    const table = await screen.findByRole('table', { name: 'Inventario de cargas' });
    for (const heading of ['Name', 'Grid', 'Alimentador', 'SED', 'kW', 'kvar', 'kVA', 'MT kV', 'BT kV', 'Uk %']) {
      expect(within(table).getByRole('columnheader', { name: heading })).toBeInTheDocument();
    }
    expect(within(table).getByText('SE50033_BT')).toBeInTheDocument();
    expect(within(table).getByText('NA203')).toBeInTheDocument();
  });

  it('sends feeder status search offset and limit to the API', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => jsonResponse(page([])));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<LoadInventoryTable workspaceId="abcdef12" selectedFeeders={['NA203']} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await user.selectOptions(screen.getByLabelText('Estado de trazabilidad'), 'AMBIGUO');
    await user.type(screen.getByRole('searchbox', { name: 'Buscar carga o SED' }), 'SE50033');

    await waitFor(() => {
      const url = String(fetchMock.mock.calls.at(-1)?.[0]);
      expect(url).toContain('feeder=NA203');
      expect(url).toContain('status=AMBIGUO');
      expect(url).toContain('search=SE50033');
      expect(url).toContain('offset=0');
      expect(url).toContain('limit=100');
    });
  });

  it('renders NO_IDENTIFICADO AMBIGUO and DESCONECTADO visibly', async () => {
    const rows = ['NO_IDENTIFICADO', 'AMBIGUO', 'DESCONECTADO'].map((status, index) => ({
      ...baseRow,
      name: `SE5003${index + 4}`,
      device_number: `D${index + 2}`,
      status: status as LoadInventoryRow['status'],
      diagnostic: `diagnóstico ${status}`,
    }));
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(page(rows))));

    render(<LoadInventoryTable workspaceId="abcdef12" selectedFeeders={[]} />);

    const table = await screen.findByRole('table', { name: 'Inventario de cargas' });
    for (const status of ['NO_IDENTIFICADO', 'AMBIGUO', 'DESCONECTADO']) {
      expect(within(table).getByText(status)).toBeVisible();
    }
  });

  it('changes page without loading all rows', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost');
      const offset = Number(url.searchParams.get('offset') ?? 0);
      return jsonResponse(page([{ ...baseRow, name: offset ? 'SE50133' : 'SE50033' }], 101, offset));
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<LoadInventoryTable workspaceId="abcdef12" selectedFeeders={[]} />);
    const table = await screen.findByRole('table', { name: 'Inventario de cargas' });
    expect(within(table).getAllByText('SE50033')[0]).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Siguiente' }));

    expect(await screen.findByText('SE50133')).toBeVisible();
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain('offset=100');
  });

  it('keeps the existing load template workflow mounted', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(page([]))));
    const context = {
      ws: { id: 'abcdef12', loaded: true },
      selected: ['NA203'],
      feeders: [],
      active: {},
      pf: null,
      run: async <T,>(fn: () => Promise<T>) => fn(),
      startJob: async () => undefined,
    } as unknown as AppCtx;

    render(<Ctx.Provider value={context}><LoadsTab /></Ctx.Provider>);

    expect(await screen.findByRole('heading', { name: 'Inventario de cargas' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '1 · Descargar plantilla de NA203' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Excel' })).toBeEnabled();
  });
});

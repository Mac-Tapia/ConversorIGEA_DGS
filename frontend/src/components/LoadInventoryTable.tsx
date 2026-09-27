import { useEffect, useMemo, useState } from 'react';

import { api, fmtNum } from '../api';
import type { LoadInventoryFilters, LoadInventoryPage, LoadInventoryStatus } from '../types';
import { Pill } from './ui';

const PAGE_SIZE = 100;
const EMPTY: LoadInventoryPage = {
  total: 0,
  offset: 0,
  limit: PAGE_SIZE,
  filters: { feeder: null, status: null, search: null },
  rows: [],
};

function tone(status: LoadInventoryStatus): 'ok' | 'warn' | 'error' | 'muted' {
  if (status === 'OK') return 'ok';
  if (status === 'NO_IDENTIFICADO') return 'muted';
  if (status === 'AMBIGUO') return 'warn';
  return 'error';
}

export function LoadInventoryTable({
  workspaceId,
  selectedFeeders,
  feeders = [],
}: {
  workspaceId: string;
  selectedFeeders: string[];
  feeders?: string[];
}) {
  const selectedOne = selectedFeeders.length === 1 ? selectedFeeders[0] : '';
  const [feeder, setFeeder] = useState(selectedOne);
  const [status, setStatus] = useState<LoadInventoryStatus | ''>('');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<LoadInventoryPage>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setFeeder(selectedOne);
    setOffset(0);
  }, [selectedOne]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const filters = useMemo<LoadInventoryFilters>(() => ({
    feeder: feeder || undefined,
    status: status || undefined,
    search: search || undefined,
  }), [feeder, status, search]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    api.electricalInventory(workspaceId, filters, offset, PAGE_SIZE)
      .then((result) => { if (active) setPage(result); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [workspaceId, filters, offset]);

  const available = useMemo(
    () => Array.from(new Set([...feeders, ...selectedFeeders])).sort(),
    [feeders, selectedFeeders],
  );
  const from = page.total ? page.offset + 1 : 0;
  const to = Math.min(page.offset + page.rows.length, page.total);

  return (
    <section className="inventory-panel" aria-labelledby="load-inventory-title">
      <div className="module-heading">
        <div>
          <h3 id="load-inventory-title">Inventario de cargas</h3>
          <p className="muted small">Relación auditable Name → SED → alimentador de origen. Grid no sustituye a Alimentador.</p>
        </div>
        <div className="row">
          <a className="btn btn-sm btn-ghost" href={api.electricalInventoryExportUrl(workspaceId, 'csv', filters)}>CSV</a>
          <a className="btn btn-sm btn-ghost" href={api.electricalInventoryExportUrl(workspaceId, 'json', filters)}>JSON</a>
        </div>
      </div>
      <div className="inventory-filters">
        <label>Alimentador
          <select value={feeder} disabled={Boolean(selectedOne)} onChange={(event) => { setFeeder(event.target.value); setOffset(0); }}>
            <option value="">Todos</option>
            {available.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label>Estado de trazabilidad
          <select value={status} onChange={(event) => { setStatus(event.target.value as LoadInventoryStatus | ''); setOffset(0); }}>
            <option value="">Todos</option>
            <option value="OK">OK</option>
            <option value="NO_IDENTIFICADO">NO_IDENTIFICADO</option>
            <option value="AMBIGUO">AMBIGUO</option>
            <option value="DESCONECTADO">DESCONECTADO</option>
          </select>
        </label>
        <label>Buscar carga o SED
          <input type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
        </label>
      </div>
      {error && <p className="alert alert-error">No se pudo cargar el inventario: {error}</p>}
      <div className="table-wrap inventory-table-wrap">
        <table className="table" aria-label="Inventario de cargas">
          <thead><tr>
            <th>Name</th><th>Grid</th><th>Alimentador</th><th>SED</th><th>Terminal</th>
            <th className="num">kW</th><th className="num">kvar</th><th className="num">kVA</th>
            <th className="num">MT kV</th><th className="num">BT kV</th><th className="num">Uk %</th><th>Estado</th>
          </tr></thead>
          <tbody>
            {page.rows.map((row) => (
              <tr key={`${row.network_id}:${row.section_id}:${row.device_number}`} title={row.diagnostic || undefined}>
                <td className="strong">{row.name}</td><td>{row.grid}</td><td>{row.alimentador || '—'}</td>
                <td>{row.sed || '—'}</td><td>{row.terminal || '—'}</td>
                <td className="num">{fmtNum(row.kw, 1)}</td><td className="num">{fmtNum(row.kvar, 1)}</td>
                <td className="num">{fmtNum(row.kva, 1)}</td><td className="num">{fmtNum(row.voltage_mt_kv, 2)}</td>
                <td className="num">{fmtNum(row.voltage_bt_kv, 2)}</td><td className="num">{fmtNum(row.uk_pct, 2)}</td>
                <td><Pill tone={tone(row.status)}>{row.status}</Pill></td>
              </tr>
            ))}
            {!loading && !page.rows.length && <tr><td colSpan={12} className="empty">No hay cargas que coincidan con los filtros.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="inventory-pagination">
        <span className="muted">{loading ? 'Cargando…' : `${from}–${to} de ${page.total}`}</span>
        <span className="spacer" />
        <button className="btn btn-sm" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Anterior</button>
        <button className="btn btn-sm" disabled={loading || offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Siguiente</button>
      </div>
    </section>
  );
}

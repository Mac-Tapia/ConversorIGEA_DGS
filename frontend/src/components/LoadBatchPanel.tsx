import { useEffect, useMemo, useState } from 'react';

import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type { LoadBatchPlan, LoadBatchResult, LoadBatchRowsPage } from '../types';
import { FileDrop, Pill } from './ui';


const PAGE_SIZE = 100;

export function LoadBatchPanel() {
  const { ws, feeders, selected, run, startJob, jobs, active } = useApp();
  const available = useMemo(
    () => feeders.filter((item) => item.convertible).map((item) => item.feeder).sort(),
    [feeders],
  );
  const [chosen, setChosen] = useState<string[]>(() => {
    const initial = selected.filter((name) => available.includes(name));
    return initial.length ? initial : available.slice(0, 1);
  });
  const [plan, setPlan] = useState<LoadBatchPlan | null>(null);
  const [page, setPage] = useState<LoadBatchRowsPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [feederFilter, setFeederFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dryJobId, setDryJobId] = useState('');
  const [applyJobId, setApplyJobId] = useState('');
  const [dryApproved, setDryApproved] = useState(false);
  const [lastResult, setLastResult] = useState<LoadBatchResult | null>(null);

  const setAll = () => {
    setChosen(available);
    setPlan(null);
    setDryApproved(false);
  };
  const toggle = (name: string) => {
    setChosen((current) => current.includes(name)
      ? current.filter((item) => item !== name)
      : [...current, name].sort());
    setPlan(null);
    setDryApproved(false);
  };

  useEffect(() => {
    if (!plan) return;
    let live = true;
    api.loadBatchRows(ws.id, plan.token, offset, PAGE_SIZE, feederFilter, statusFilter)
      .then((value) => { if (live) setPage(value); })
      .catch(() => { if (live) setPage(null); });
    return () => { live = false; };
  }, [ws.id, plan, offset, feederFilter, statusFilter]);

  useEffect(() => {
    const job = dryJobId ? jobs[dryJobId] : undefined;
    if (job?.status === 'done' && job.result?.status === 'PASS') {
      setDryApproved(true);
      setLastResult(job.result as LoadBatchResult);
    }
  }, [dryJobId, jobs]);

  useEffect(() => {
    const job = applyJobId ? jobs[applyJobId] : undefined;
    if (job?.status === 'done' && job.result) setLastResult(job.result as LoadBatchResult);
  }, [applyJobId, jobs]);

  const upload = async (file: File) => {
    if (!chosen.length) return;
    const value = await run(() => api.loadBatchPlan(ws.id, chosen, file));
    if (!value) return;
    setPlan(value);
    setOffset(0);
    setFeederFilter('');
    setStatusFilter('');
    setDryApproved(false);
    setLastResult(null);
  };

  const dryRun = async () => {
    if (!plan) return;
    const job = await startJob(() => api.dryRunLoadBatch(ws.id, plan.token));
    if (!job) return;
    setDryJobId(job.id);
    if (job.status === 'done' && job.result?.status === 'PASS') {
      setDryApproved(true);
      setLastResult(job.result as LoadBatchResult);
    }
  };

  const apply = async () => {
    if (!plan || !dryApproved) return;
    const job = await startJob(() => api.applyLoadBatch(ws.id, plan.token));
    if (!job) return;
    setApplyJobId(job.id);
    if (job.status === 'done' && job.result) setLastResult(job.result as LoadBatchResult);
  };

  return (
    <section className="load-batch" aria-labelledby="load-batch-title">
      <div className="module-heading">
        <div>
          <h3 id="load-batch-title">Actualización masiva de cargas</h3>
          <p className="muted">Una plantilla para uno o varios alimentadores. La identidad usada es Alimentador + NetworkID + SED.</p>
        </div>
        <div className="row">
          <button className="btn btn-ghost" onClick={setAll}>Seleccionar todos</button>
          <button className="btn btn-ghost" onClick={() => setChosen([])}>Ninguno</button>
        </div>
      </div>

      <div className="feeder-checks" aria-label="Alimentadores de la plantilla">
        {available.map((name) => (
          <label key={name} className="check-card">
            <input type="checkbox" checked={chosen.includes(name)} onChange={() => toggle(name)} />
            <span>{name}</span>
          </label>
        ))}
      </div>

      <div className="steps">
        <div className="step-box">
          <h3>1 · Descargar plantilla consolidada</h3>
          <div className="row">
            <a className={`btn ${!chosen.length ? 'disabled' : ''}`}
              aria-disabled={!chosen.length}
              href={chosen.length ? api.loadBatchTemplateUrl(ws.id, chosen, 'xlsx') : undefined}>
              Descargar Excel
            </a>
            <a className={`btn btn-ghost ${!chosen.length ? 'disabled' : ''}`}
              aria-disabled={!chosen.length}
              href={chosen.length ? api.loadBatchTemplateUrl(ws.id, chosen, 'csv') : undefined}>
              Descargar CSV
            </a>
          </div>
          <small className="muted">Cada hoja corresponde a un alimentador. En CSV, la columna Alimentador es obligatoria si hay más de uno.</small>
        </div>
        <div className="step-box">
          <h3>2 · Subir Excel o CSV</h3>
          <FileDrop compact accept=".xlsx,.csv" disabled={!chosen.length} onFiles={([file]) => upload(file)}>
            <span>Soltar archivo o <u>elegir</u></span>
          </FileDrop>
          <small className="muted">kW=kvar=kVA=FP=0 (o todos vacíos) significa SIN DATOS. Solo accion=poner_cero escribe P=Q=0.</small>
        </div>
      </div>

      {plan && (
        <div className="batch-plan">
          <div className="module-heading">
            <div>
              <h3>3 · Revisar plan</h3>
              <p className="muted">Lote {plan.batch_id} · {page?.total ?? 0} filas</p>
            </div>
            <Pill tone={plan.applicable ? 'ok' : 'error'}>{plan.applicable ? 'APLICABLE' : 'BLOQUEADO'}</Pill>
          </div>
          <div className="stats">
            {Object.entries(plan.summary_by_feeder).map(([name, summary]) => (
              <div className="stat" key={name}>
                <span className="stat-value">{String(summary.updates ?? 0)}</span>
                <span className="stat-label">{name} · actualizar</span>
              </div>
            ))}
          </div>
          {plan.row_errors.length > 0 && (
            <div className="alert alert-error"><strong>Errores del archivo</strong>
              <ul>{plan.row_errors.slice(0, 20).map((error) => <li key={error}>{error}</li>)}</ul>
            </div>
          )}
          <div className="inventory-filters">
            <label>Alimentador
              <select value={feederFilter} onChange={(event) => { setFeederFilter(event.target.value); setOffset(0); }}>
                <option value="">Todos</option>
                {plan.feeders.map((name) => <option key={name}>{name}</option>)}
              </select>
            </label>
            <label>Estado
              <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setOffset(0); }}>
                <option value="">Todos</option>
                <option value="actualizar">Actualizar</option>
                <option value="desconocida">Desconocida</option>
                <option value="sin_datos">Sin datos</option>
                <option value="omitida">Omitida</option>
              </select>
            </label>
          </div>
          <div className="table-wrap table-short">
            <table className="table" aria-label="Vista previa de cargas">
              <thead><tr><th>Alimentador</th><th>NetworkID</th><th>SED</th><th>Estado</th><th className="num">P MW</th><th className="num">Q Mvar</th><th className="num">FP</th></tr></thead>
              <tbody>
                {(page?.rows ?? []).map((row) => (
                  <tr key={`${row.feeder}:${row.sed_code}:${row.status}`}>
                    <td>{row.feeder}</td><td>{row.network_id}</td><td>{row.sed_code}</td><td>{row.status}</td>
                    <td className="num">{fmtNum(row.plini_mw, 6)}</td>
                    <td className="num">{fmtNum(row.qlini_mvar, 6)}</td>
                    <td className="num">{fmtNum(row.coslini, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="inventory-pagination">
            <button className="btn btn-ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Anterior</button>
            <span className="muted">{page ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, page.total)} de ${page.total}` : 'Cargando…'}</span>
            <button className="btn btn-ghost" disabled={!page || offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Siguiente</button>
          </div>
          <div className="actions batch-actions">
            <button className="btn btn-pf" disabled={!plan.applicable || Boolean(active.powerfactory)} onClick={dryRun}>Ejecutar dry-run</button>
            <button className="btn btn-pf" disabled={!dryApproved || Boolean(active.powerfactory)} onClick={apply}>Aplicar en DigSILENT</button>
            {dryApproved && <Pill tone="ok">DRY-RUN PASS</Pill>}
          </div>
          {lastResult?.artifacts && (
            <div className="artifact-links" aria-label="Auditoría de cargas">
              <strong>Auditoría:</strong>
              {Object.entries(lastResult.artifacts).map(([name, path]) => (
                <a className="link" key={name} href={api.fileUrl(ws.id, path, true)}>{name}</a>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

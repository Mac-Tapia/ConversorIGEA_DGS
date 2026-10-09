import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import type {
  DiagnosisResponse, ReconstructionDecision, ReconstructionReport, ReconstructionResponse,
} from '../types';
import { Pill } from './ui';

type EvidenceFilter = 'all' | 'catalog_match' | 'engineering_assumption';

const showValue = (value: unknown) => {
  if (value == null || value === '') return '∅';
  return typeof value === 'string' ? value : JSON.stringify(value);
};

/** Reconstrucción en curso que, si acaba bien, sigue con la conversión de su selección. */
interface Pending {
  jobId: string;
  targets: string[];
  all: boolean;
}

export function ReconstructionPanel() {
  const { ws, feeders, selected, active, jobs, run, startJob } = useApp();
  const [report, setReport] = useState<ReconstructionReport | null>(null);
  const [filter, setFilter] = useState<EvidenceFilter>('all');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const all = selected.length === 0;
  const targets = all ? [] : selected;
  const stale = ws.loaded_run_id !== ws.active_run_id;
  const disabled = Boolean(active.engine) || busy || Boolean(pending) || stale || !ws.loaded;

  // Diagnosticar y reconstruir son trabajos (spec 001, RF-8): el resultado que se
  // muestra es el del último que terminó bien en este espacio, como en «Lote».
  const diagnosis = useMemo(() => Object.values(jobs)
    .filter((j) => j.workspace_id === ws.id && (j.kind === 'diagnose' || j.kind === 'reconstruct')
      && j.status === 'done')
    .sort((a, b) => (a.finished_at ?? 0) - (b.finished_at ?? 0))
    .pop()?.result as DiagnosisResponse | ReconstructionResponse | undefined, [jobs, ws.id]);

  const decisions = useMemo(() => (report?.decisions ?? []).filter(
    (decision) => filter === 'all' || decision.level === filter,
  ), [report, filter]);

  const pendingJob = pending ? jobs[pending.jobId] : undefined;
  useEffect(() => {
    if (!pending || !pendingJob) return;
    if (pendingJob.status === 'queued' || pendingJob.status === 'running') return;
    setPending(null);
    // Cancelada o fallida: no se convierte, y el dataset anterior sigue activo (RF-9).
    if (pendingJob.status !== 'done') return;
    void (async () => {
      const loaded = await run(() => api.reconstructionReport(ws.id));
      if (loaded) setReport(loaded);
      await startJob(() => api.convert(ws.id, pending.targets, pending.all));
    })();
  }, [pending, pendingJob, run, startJob, ws.id]);

  const diagnose = () => startJob(() => api.diagnose(ws.id, targets, all));

  const reconstructAndConvert = async () => {
    const job = await startJob(() => api.reconstruct(ws.id, targets, all));
    if (job) setPending({ jobId: job.id, targets, all });
  };

  const viewChanges = async () => {
    setBusy(true);
    try {
      const loaded = await run(() => api.reconstructionReport(ws.id));
      if (loaded) setReport(loaded);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="reconstruction-panel">
      <div className="reconstruction-head">
        <div>
          <b>Diagnóstico y reconstrucción auditable</b>
          <p className="muted small">
            Alcance: {all ? `todos (${feeders.length})` : `${selected.length} seleccionado(s)`}.
            Los originales y sus SHA-256 no se modifican.
          </p>
        </div>
        <div className="row">
          <button className="btn btn-sm" disabled={disabled} onClick={diagnose}>Diagnosticar</button>
          <button className="btn btn-sm btn-primary" disabled={disabled} onClick={reconstructAndConvert}>
            Reconstruir y convertir
          </button>
          <button className="btn btn-sm" disabled={disabled || !ws.reconstruction} onClick={viewChanges}>
            Ver cambios
          </button>
        </div>
      </div>

      {stale && <p className="alert alert-error">La ejecución cargada ya no es la activa. Vuelva a cargar las entradas.</p>}
      {diagnosis && (
        <div className="reconstruction-summary">
          {diagnosis.feeders.map((row) => (
            <div className="reconstruction-feeder" key={row.network_id}>
              <span className="strong">{row.feeder}</span>
              <Pill tone={row.assumption_count ? 'warn' : row.repair_count ? 'info' : 'ok'}>{row.readiness}</Pill>
              <span>calidad: {row.source_quality}</span>
              <span>cambios: {row.repair_count}</span>
              <span>supuestos: {row.assumption_count}</span>
              <span>catálogos: {row.catalog_sources.join(', ') || '—'}</span>
              <span>convergencia: {row.convergence_state ?? 'pendiente'}</span>
            </div>
          ))}
        </div>
      )}

      {report && (
        <div className="reconstruction-report">
          <div className="toolbar">
            <span className="mono">reporte {report.report_sha256.slice(0, 12)}…</span>
            {(['all', 'catalog_match', 'engineering_assumption'] as const).map((value) => (
              <button key={value} className={`chip ${filter === value ? 'on' : ''}`} onClick={() => setFilter(value)}>
                {value === 'all' ? 'Todos' : value === 'catalog_match' ? 'Catálogo' : 'Supuestos'}
              </button>
            ))}
            <a className="link" href={api.fileUrl(ws.id, 'reconstruction_report.json', true)}>Descargar JSON</a>
          </div>
          <div className="table-wrap table-short">
            <table className="table">
              <thead><tr><th>Elemento</th><th>Campo</th><th>Antes</th><th>Después</th><th>Evidencia</th></tr></thead>
              <tbody>
                {decisions.map((decision: ReconstructionDecision, index) => (
                  <tr key={`${decision.entity_type}-${decision.entity_id}-${decision.field}-${index}`}>
                    <td><span className="strong">{decision.entity_id}</span><br /><span className="muted small">{decision.entity_type}</span></td>
                    <td>{decision.field}<br /><span className="muted small">{decision.rule}</span></td>
                    <td className="mono reconstruction-value">{showValue(decision.original_value)}</td>
                    <td className="mono reconstruction-value">{showValue(decision.applied_value)}</td>
                    <td>
                      <Pill tone={decision.level === 'catalog_match' ? 'info' : 'warn'}>{decision.level}</Pill>
                      <div className="small">{Math.round(decision.confidence * 100)} % · {decision.reason}</div>
                      {decision.candidates.length > 0 && <div className="muted small">candidatos: {decision.candidates.join(', ')}</div>}
                    </td>
                  </tr>
                ))}
                {decisions.length === 0 && <tr><td colSpan={5} className="empty">No hay cambios para este filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

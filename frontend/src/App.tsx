import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from './api';
import { Ctx, type AppCtx } from './context';
import { FeedersPanel } from './components/FeedersPanel';
import { InputsPanel } from './components/InputsPanel';
import { JobBar } from './components/JobBar';
import { LoteTab } from './components/LoteTab';
import { LogPanel } from './components/LogPanel';
import { CatalogTab, LoadsTab, NewSedTab, ResultsTab, SystemTab } from './components/Modules';
import { OptionsPanel } from './components/OptionsPanel';
import { Modal, Pill, useConfirm, useToast } from './components/ui';
import type { Health, Job, PowerFactoryStatus } from './types';
import { useWorkspace } from './useWorkspace';

const TABS = [
  { id: 'results', label: 'Resultados', el: <ResultsTab /> },
  { id: 'loads', label: 'Cargas de SED', el: <LoadsTab /> },
  { id: 'newsed', label: 'SED nuevas', el: <NewSedTab /> },
  { id: 'lote', label: 'Cargas en DIgSILENT', el: <LoteTab /> },
  { id: 'catalog', label: 'Catálogo de parámetros', el: <CatalogTab /> },
  { id: 'system', label: 'Sistema completo', el: <SystemTab /> },
] as const;

const LOG_KEY = 'igea-dgs.log-height';

function readLogHeight(): number {
  try {
    const v = Number(localStorage.getItem(LOG_KEY));
    return v >= 80 ? v : 220;
  } catch {
    return 220;
  }
}

/** Resumen de un trabajo terminado, en el mismo tono que los diálogos de la GUI de escritorio. */
function JobSummary({ job, onClose }: { job: Job; onClose: () => void }) {
  const r = job.result;
  let body: ReactNode = <p>Terminado. El detalle está en el Registro.</p>;
  if (job.status === 'failed') {
    body = <><p className="alert alert-error">{job.error}</p><p className="muted">El detalle completo está en el Registro.</p></>;
  } else if (job.status === 'cancelled' && !r) {
    body = <p>Cancelado. Lo ya terminado se conserva; el alimentador en curso se descartó entero, nunca a medias.</p>;
  } else if (job.kind === 'load' && r) {
    const t = r.totals;
    body = <>
      <p>Alimentadores leídos: <b>{t.feeders}</b> · convertibles: <b>{t.convertible_feeders}</b> · stubs sin tramos: <b>{t.stub_feeders}</b></p>
      <p>Tramos / cargas / SW: {t.sections} / {t.customer_loads} / {t.switches}</p>
      <p>Se generarán <b>{r.conversion.expected_dgs_files}</b> archivos .dgs independientes (uno por alimentador convertible).</p>
      <p className={r.integrity.errors ? 'alert alert-warn' : ''}>Integridad: {r.integrity.errors} errores, {r.integrity.warnings} avisos.</p>
      {r.catalog_report?.critical && (
        <p className="alert alert-error">Solo el {Math.round(r.catalog_report.final_coverage * 100)} % de los tipos de línea está en el
          catálogo. El resto tomará la impedancia de DEFAULT sin que nada lo delate.</p>
      )}
    </>;
  } else if (job.kind === 'convert' && r) {
    const s = r.summary;
    body = <>
      {job.status === 'cancelled' && <p className="alert alert-warn">Lote cancelado: lo convertido se conserva.</p>}
      <div className="stats">
        <div className="stat"><span className="stat-value">{s.requested}</span><span className="stat-label">solicitados</span></div>
        <div className="stat stat-ok"><span className="stat-value">{s.ok}</span><span className="stat-label">OK</span></div>
        <div className="stat"><span className="stat-value">{s.skipped ?? 0}</span><span className="stat-label">omitidos</span></div>
        <div className={`stat ${s.failed ? 'stat-error' : ''}`}><span className="stat-value">{s.failed}</span><span className="stat-label">fallidos</span></div>
      </div>
      {(r.input_warnings ?? []).map((w: string) => <p key={w} className="alert alert-warn">{w}</p>)}
      <p className="muted">Manifiesto: batch_manifest.json. Descárguelo desde «Resultados».</p>
    </>;
  } else if (job.kind === 'powerfactory' && r) {
    body = <>
      <p>Solicitados: {r.requested} · OK: <b>{r.ok}</b> · Fallidos: <b>{r.failed}</b></p>
      <ul>{r.lines.map((l: string) => <li key={l}>{l}</li>)}</ul>
      <p className="muted">Reportes: *_powerfactory_acceptance.json / .txt en la salida.</p>
    </>;
  } else if ((job.kind === 'plan' || job.kind === 'system') && r) {
    body = r.returncode === 0
      ? <p>Terminado correctamente.{r.report ? ` Informe: ${r.report}.` : ''}</p>
      : r.returncode === 3
        ? <p className="alert alert-error">No se pudo conectar con PowerFactory. Ábralo y reintente.</p>
        : <p className="alert alert-warn">El proceso devolvió el código {r.returncode}. Causas frecuentes: PowerFactory no está abierto, u
          otro proceso tiene tomado su motor (solo admite uno a la vez). Detalle en el Registro.</p>;
  } else if (job.kind === 'catalog' && r) {
    body = <><p>{r.summary}</p><p>Descargue <b>{r.file}</b> en «Catálogo de parámetros», complete las columnas de ficha y vuelva a subirlo.</p></>;
  }
  const title = `${job.title}${job.status === 'failed' ? ' — error' : job.status === 'cancelled' ? ' — cancelado' : ''}`;
  return <Modal title={title} onClose={onClose} actions={<button className="btn btn-primary" autoFocus onClick={onClose}>Aceptar</button>}>{body}</Modal>;
}

export default function App() {
  const toast = useToast();
  const confirm = useConfirm();
  const [health, setHealth] = useState<Health | null>(null);
  const [pf, setPf] = useState<PowerFactoryStatus | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('results');
  const [summary, setSummary] = useState<Job | null>(null);
  const [logHeight, setLogHeight] = useState(readLogHeight);
  const drag = useRef<{ y: number; h: number } | null>(null);

  const onFinished = useCallback((job: Job) => {
    // Los trabajos cortos no merecen un diálogo; los largos sí, como en la GUI.
    if (['load', 'convert', 'powerfactory', 'plan', 'system', 'catalog'].includes(job.kind) || job.status === 'failed') {
      setSummary(job);
    }
  }, []);
  const w = useWorkspace(onFinished);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => toast('error', 'No responde la API', String(e.message ?? e)));
    api.powerfactory().then(setPf).catch(() => undefined);
  }, [toast]);

  // La selección se limpia de nombres que ya no existen (otra entrega cargada).
  useEffect(() => {
    const names = new Set(w.feeders.map((f) => f.feeder));
    setSelected((s) => (s.every((n) => names.has(n)) ? s : s.filter((n) => names.has(n))));
  }, [w.feeders]);

  const active = useMemo(() => {
    const out: AppCtx['active'] = {};
    for (const j of Object.values(w.jobs)) {
      if (j.workspace_id === w.state?.id && (j.status === 'queued' || j.status === 'running')) out[j.lane] = j;
    }
    return out;
  }, [w.jobs, w.state?.id]);

  const run = useCallback(async <T,>(fn: () => Promise<T>) => {
    try {
      return await fn();
    } catch (e) {
      toast('error', 'No se pudo completar', e instanceof Error ? e.message : String(e));
      return undefined;
    }
  }, [toast]);

  const startJob = useCallback(async (fn: () => Promise<Job>) => {
    const job = await run(fn);
    if (job) w.trackJob(job);
    return job;
  }, [run, w]);

  if (w.bootError) {
    return <div className="boot"><h1>No se pudo abrir el espacio de trabajo</h1><p>{w.bootError}</p>
      <p className="muted">¿Está arrancado el servidor? <code>python -m igea_dgs.web</code></p></div>;
  }
  if (!health || !w.state) return <div className="boot"><div className="spinner" /><p>Conectando con el conversor…</p></div>;

  const ctx: AppCtx = {
    ws: w.state, setWs: w.setState, health, pf, feeders: w.feeders, outputs: w.outputs, jobs: w.jobs,
    selected, setSelected, active, run, startJob, refresh: w.refresh,
  };
  const running = [active.engine, active.powerfactory].filter(Boolean) as Job[];
  const caps = health.capabilities;

  return (
    <Ctx.Provider value={ctx}>
      <div className="app" style={{ gridTemplateRows: `auto 1fr 6px ${logHeight}px` }}>
        <header className="topbar">
          <div className="brand">
            <span className="logo" aria-hidden>⚡</span>
            <div>
              <h1>Conversor IGEA/CYMDIST → DGS</h1>
              <span className="muted small">DIgSILENT PowerFactory · v{health.version}</span>
            </div>
          </div>
          <div className="caps">
            <Pill tone={caps.geography ? 'ok' : 'muted'} title="pyproj">GPS</Pill>
            <Pill tone={caps.xlsx ? 'ok' : 'muted'} title="pandas + openpyxl">Excel</Pill>
            <Pill tone={caps.access ? 'ok' : 'muted'} title="pyodbc">Access</Pill>
            <Pill tone={pf?.available ? 'ok' : 'muted'} title={pf ? `${pf.api_dir ?? 'sin API'} · ${pf.interpreter_reason}` : 'comprobando…'}>
              PowerFactory{pf?.api_version ? ` ${pf.api_version}` : ''}
            </Pill>
          </div>
          <div className="ws-id">
            <span className="muted small" title={w.state.id}>Espacio {w.state.id.slice(0, 6)}</span>
            <button className="btn btn-sm btn-ghost" disabled={running.length > 0} onClick={async () => {
              if (await confirm('Nuevo espacio de trabajo', <p>Empezará con las entradas vacías. El espacio actual se conserva en el servidor.</p>, 'Crear')) {
                setSelected([]);
                await run(w.newWorkspace);
              }
            }}>Nuevo espacio</button>
          </div>
        </header>

        <main className="content">
          <JobBar jobs={running} />
          <div className="grid">
            <div className="col-side">
              <InputsPanel />
              <OptionsPanel />
            </div>
            <div className="col-main">
              <FeedersPanel />
              {w.state.loaded && (
                <section className="card">
                  <nav className="tabs" role="tablist">
                    {TABS.map((t) => (
                      <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''}
                        onClick={() => setTab(t.id)}>{t.label}</button>
                    ))}
                  </nav>
                  {TABS.find((t) => t.id === tab)!.el}
                </section>
              )}
            </div>
          </div>
        </main>

        <div className="splitter" role="separator" aria-orientation="horizontal" aria-label="Redimensionar el Registro"
          onPointerDown={(e) => {
            drag.current = { y: e.clientY, h: logHeight };
            (e.target as HTMLElement).setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            const h = Math.min(window.innerHeight - 160, Math.max(80, drag.current.h - (e.clientY - drag.current.y)));
            setLogHeight(h);
          }}
          onPointerUp={() => {
            drag.current = null;
            try { localStorage.setItem(LOG_KEY, String(logHeight)); } catch { /* sin almacenamiento */ }
          }} />
        <LogPanel lines={w.log} onClear={() => w.setLog([])} connected={w.connected} />
      </div>
      {summary && <JobSummary job={summary} onClose={() => setSummary(null)} />}
    </Ctx.Provider>
  );
}

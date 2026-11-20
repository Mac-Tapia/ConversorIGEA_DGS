import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { plural } from '../shared/formato';
import { api, ApiError } from '../api/client';
import { AcercaDe } from './AcercaDe';
import { ArchivoInformes } from './ArchivoInformes';
import { CuentasNube } from './CuentasNube';
import { NubeEnEntradas } from './NubeEnEntradas';
import { Ctx, type AppCtx } from '../shared/context';
import { betaActiva } from '../shared/edicion';
import { Asistente } from '../features/asistente/Asistente';
import { ElegirDeLaNube } from '../features/nube/ElegirDeLaNube';
import { conectadas } from '../features/nube/logica';
import { PublicarExpediente } from '../features/nube/PublicarExpediente';
import { VistaPrevia } from '../features/powerfactory/EnviarInforme';
import { textoEstado } from '../features/powerfactory/enviarInformeLogica';
import { AccionesOperadorCtx, type AccionesOperador } from '../shared/accionesOperador';
import { AvisosDatos, EspacioNoDisponible } from './AvisosDatos';
import { EstudioVnr } from '../features/vnr/EstudioVnr';
import { EstudioPit } from '../features/pit/EstudioPit';
import { EstudioVad } from '../features/vad/EstudioVad';
import { BibliotecaNormativa } from '../features/normativa/BibliotecaNormativa';
import { CargasTab } from '../features/powerfactory/CargasTab';
import { EvolucionFijas } from '../features/clientesfijos/EvolucionFijas';
import { FeedersPanel } from '../features/conversion/FeedersPanel';
import { InputsPanel } from '../features/conversion/InputsPanel';
import { InstalacionesPowerFactoryModal, textoPildoraPf } from './InstalacionesPowerFactory';
import { JobBar } from './JobBar';
import { LogPanel } from './LogPanel';
import { MarcaBeta } from '../shared/MarcaBeta';
import { MarcaValidacion } from '../shared/MarcaValidacion';
import { refDePestana } from '../shared/matrizEstudios';
import { CatalogTab, ResultsTab, SystemTab } from '../features/conversion/Modules';
import { OptionsPanel } from '../features/conversion/OptionsPanel';
import { PerfilEmpresa } from '../features/conversion/PerfilEmpresa';
import { PlanoRed } from '../features/plano/PlanoRed';
import { Modal, Pill, useConfirm, useToast } from '../shared/ui';
import type { Health, Job, PowerFactoryStatus } from '../api/types';
import { useWorkspace } from '../shared/useWorkspace';
import { PanelPestana, PestanasModulos } from './Pestanas';
import { REGISTRO_INICIAL, REGISTRO_MIN, UMBRAL_PULSACION, alturaAlPulsar, alturaPorTecla, useFlechasEnGrupos } from './teclado';
import { avisosDeTrabajos, avisosPorPestana } from '../shared/pasoDeTrabajo';
import { ReferenciaSoporte, useVistos } from '../shared/AvisosTrabajo';

// ``entradas``: la pestaña necesita la entrega cargada. «Cargas en DIgSILENT» trabaja
// sobre un proyecto que ya está en DIgSILENT y se ve siempre (spec 008, RF-1).
const TABS = [
  { id: 'results', label: 'Resultados', el: <ResultsTab />, entradas: true },
  // Spec 111: el plano de la red con la entrega cargada; se añade junto a «Resultados» sin quitar ninguna.
  { id: 'plano', label: 'Plano de la red', el: <PlanoRed />, entradas: true },
  { id: 'cargas', label: 'Cargas en DIgSILENT', el: <CargasTab />, entradas: false },
  // Spec 105: con los libros de medición del espacio; no necesita la red cargada.
  { id: 'clientes_fijos', label: 'Evolución de clientes fijos', el: <EvolucionFijas />, entradas: false },
  // 108 T28: el VNR según la Guía (RCD 232-2017) desde el inventario VNR-GIS y el SICODI; no necesita la red cargada.
  { id: 'vnr', label: 'Estudio VNR', el: <EstudioVnr />, entradas: false },
  // 107 T13: el diagnóstico y el expediente del PIT por área de demanda; no necesita la red cargada.
  { id: 'pit', label: 'Estudio PIT', el: <EstudioPit />, entradas: false },
  // 108 T29: el estudio de costos del VAD (empresa modelo, observaciones e Informe Definitivo); no necesita la red cargada.
  { id: 'vad', label: 'Estudio VAD', el: <EstudioVad />, entradas: false },
  // 072 (módulos): el corto plazo, el PIDE y el largo plazo, cada uno en su pestaña como el VNR, el PIT y el VAD. Son la
  // MISMA «Cargas en DIgSILENT» con su tipo fijo y solo sus secciones; la pestaña «Cargas en DIgSILENT» sigue entera.
  { id: 'corto', label: 'Corto plazo', el: <CargasTab modulo="corto_plazo" />, entradas: false },
  { id: 'pide', label: 'PIDE', el: <CargasTab modulo="pide" />, entradas: false },
  { id: 'largo', label: 'Largo plazo', el: <CargasTab modulo="largo_plazo" />, entradas: false },
  // 107:RF-21: la biblioteca normativa general, la misma para toda empresa, estudio y módulo.
  { id: 'normativa', label: 'Biblioteca normativa', el: <BibliotecaNormativa />, entradas: false },
  { id: 'catalog', label: 'Catálogo de parámetros', el: <CatalogTab />, entradas: true },
  { id: 'system', label: 'Sistema completo', el: <SystemTab />, entradas: true },
  // Spec 026: la consola de órdenes no necesita la entrega cargada (puede pedir que se cargue).
  { id: 'asistente', label: 'Asistente', el: <Asistente />, entradas: false },
] as const;

const LOG_KEY = 'convertersmartgrid.log-height';

function readLogHeight(): number {
  try {
    const v = Number(localStorage.getItem(LOG_KEY));
    return v >= REGISTRO_MIN ? v : REGISTRO_INICIAL;
  } catch {
    return REGISTRO_INICIAL;
  }
}

function saveLogHeight(h: number): void {
  try { localStorage.setItem(LOG_KEY, String(h)); } catch { /* sin almacenamiento */ }
}

/** El tope del Registro: deja siempre a la vista la cabecera y algo del contenido. */
const alturaMaxima = () => Math.max(REGISTRO_MIN, window.innerHeight - 160);

/** Una capacidad del servidor: el estado se lee y se oye, no solo se ve por el color (WCAG 1.4.1). */
function Capacidad({ ok, etiqueta, detalle }: { ok: boolean; etiqueta: string; detalle: string }) {
  const estado = ok ? 'disponible' : 'no disponible';
  return <Pill tone={ok ? 'ok' : 'muted'} title={`${etiqueta}: ${estado} (${detalle})`}>
    <span aria-hidden="true">{ok ? '✓' : '–'}</span> {etiqueta}<span className="sr-only">: {estado}</span>
  </Pill>;
}

/** Resumen de un trabajo terminado. */
function JobSummary({ job, onClose }: { job: Job; onClose: () => void }) {
  const r = job.result;
  let body: ReactNode = <p>Terminado. El detalle está en el Registro.</p>;
  if (job.status === 'interrumpido') {
    body = <><p className="alert alert-warn">{job.error}</p><p className="muted">Su registro sigue disponible en el aviso de arriba.</p><ReferenciaSoporte traza={job.traza} /></>;
  } else if (job.status === 'failed') {
    body = <><p className="alert alert-error">{job.error}</p><p className="muted">El detalle completo está en el Registro.</p><ReferenciaSoporte traza={job.traza} /></>;
  } else if (job.status === 'cancelled' && !r) {
    body = <p>Cancelado. Lo ya terminado se conserva; el alimentador en curso se descartó entero, nunca a medias.</p>;
  } else if (job.kind === 'load' && r) {
    const t = r.totals;
    body = <>
      {/* 091:RF-29: llamaba convertibles solo a los que tienen tramos, y se convierten todos. */}
      <p>Alimentadores leídos: <b>{t.feeders}</b> · con tramos: <b>{t.convertible_feeders}</b> · sin tramos en la fuente: <b>{t.stub_feeders}</b></p>
      <p>Tramos / cargas / SW: {t.sections} / {t.customer_loads} / {t.switches}</p>
      <p>Se generarán <b>{r.conversion.expected_dgs_files}</b> archivos .dgs independientes, uno por alimentador leído.</p>
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
      <p>Solicitados: {r.requested} · OK: <b>{r.ok}</b> · Importados sin aceptar: <b>{r.sin_aceptar ?? 0}</b> · Fallidos: <b>{r.failed}</b></p>
      <ul>{r.lines.map((l: string) => <li key={l}>{l}</li>)}</ul>
      <p className="muted">Reportes: *_powerfactory_acceptance.json / .txt en la salida.</p>
    </>;
  } else if ((job.kind === 'cargas_simular' || job.kind === 'cargas_aplicar') && r) {
    const inf = r.informe;
    const n = (k: string) => inf.feeders.reduce((t: number, f: Record<string, unknown[]>) => t + (f[k]?.length ?? 0), 0);
    body = <>
      {inf.cancelado && <p className="alert alert-warn">Cancelado: el alimentador en curso terminó; los siguientes no se empezaron.</p>}
      {inf.modo === 'simular'
        ? <p>Simulación: se actualizarían <b>{n('actualizarian')}</b> {plural(n('actualizarian'), 'demanda', 'demandas')} y se crearían <b>{n('crearian')}</b> {plural(n('crearian'), 'carga', 'cargas')}. Nada se escribió.</p>
        : <p>Variación <b>{inf.variacion ?? '—'}</b>: <b>{n('actualizadas')}</b> {plural(n('actualizadas'), 'demanda actualizada', 'demandas actualizadas')}, <b>{n('creadas')}</b> {plural(n('creadas'), 'carga creada', 'cargas creadas')},
          {' '}<b>{n('fallos')}</b> {plural(n('fallos'), 'fallo', 'fallos')}.</p>}
      <p>Omitidas: {inf.sin_alimentador.length} sin coincidencia, {inf.ambiguas.length} ambiguas, {inf.no_creadas.length} cargas nuevas no creadas.</p>
      {inf.flujo && <p className={inf.flujo.converged ? '' : 'alert alert-error'}>Flujo de carga: {inf.flujo.converged ? 'converge' : 'no converge'}.</p>}
      <p className="muted">El detalle por alimentador está en la pestaña «Cargas en DIgSILENT».</p>
    </>;
  } else if ((job.kind === 'plan' || job.kind === 'system') && r) {
    body = r.returncode === 0
      ? <p>Terminado correctamente.{r.report ? ` Informe: ${r.report}.` : ''}</p>
      : r.returncode === 3
        // 091:RF-3: pedía abrirlo, y lo que hace falta es cerrarlo: la web lo abre por su cuenta.
        ? <p className="alert alert-error">No se pudo usar DIgSILENT: si está abierto a mano, ciérrelo y vuelva a intentarlo. El detalle está en el Registro.</p>
        : <p className="alert alert-warn">El proceso devolvió el código {r.returncode}. Causa frecuente: DIgSILENT abierto a mano u
          otro proceso con su motor (solo admite uno a la vez). Detalle en el Registro.</p>;
  } else if (job.kind === 'catalog' && r) {
    body = <><p>{r.summary}</p><p>Descargue <b>{r.file}</b> en «Catálogo de parámetros», complete las columnas de ficha y vuelva a subirlo.</p></>;
  }
  // 081:RF-24: un trabajo que terminó sin que todo quedara bien lo dice en su título, con la lista.
  const title = `${job.title}${job.status === 'failed' ? ' — error' : job.status === 'cancelled' ? ' — cancelado'
    : job.status === 'interrumpido' ? ' — interrumpido'
    : job.status === 'parcial' ? ' — parcial' : job.status === 'no_converge' ? ' — no converge' : ''}`;
  const pendientes = (r?.pendientes ?? []) as { alimentador: string; estado: string; motivo: string }[];
  return <Modal title={title} onClose={onClose} actions={<button className="btn btn-primary" autoFocus onClick={onClose}>Aceptar</button>}>
    {pendientes.length > 0 && <ul className="alert alert-warn">{pendientes.map((p) => (
      <li key={p.alimentador}><strong>{p.alimentador}</strong> {p.estado}: {p.motivo}</li>))}</ul>}
    {body}
  </Modal>;
}

/** 002:RF-19: la capa app da a la tarjeta de operador del asistente lo que usa de la nube y del correo. */
const ACCIONES_OPERADOR: AccionesOperador = { ElegirDeLaNube, PublicarExpediente, VistaPrevia, conectadas, textoEstado };

export default function App() {
  const toast = useToast();
  const confirm = useConfirm();
  const [health, setHealth] = useState<Health | null>(null);
  const [pf, setPf] = useState<PowerFactoryStatus | null>(null);
  const [verPf, setVerPf] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>(() => {
    const solicitado = new URLSearchParams(window.location.search).get('panel');
    return TABS.find((t) => t.id === solicitado)?.id ?? 'results';
  });
  const [summary, setSummary] = useState<Job | null>(null);
  const [logHeight, setLogHeight] = useState(readLogHeight);
  const drag = useRef<{ y: number; h: number; movido: boolean } | null>(null);
  // La altura antes de plegar el Registro con una pulsación (alternativa a arrastrar, WCAG 2.5.7).
  const antesDePlegar = useRef<number | null>(null);
  // 091:RF-7: las pestañas ya abiertas siguen montadas, ocultas: el proyecto elegido vivía en la suya y se perdía.
  const visitadas = useRef(new Set<string>());
  const espacioVisto = useRef('');

  const onFinished = useCallback((job: Job) => {
    // Los trabajos cortos no merecen un diálogo; los largos sí.
    if (['load', 'convert', 'powerfactory', 'plan', 'system', 'catalog'].includes(job.kind) || job.status === 'failed' || job.status === 'parcial' || job.status === 'no_converge' || job.status === 'interrumpido') {
      setSummary(job);
    }
  }, []);
  // 086:RF-47: tras reiniciar, el servidor es otro y puede decir otra cosa de la copia y de la edición.
  const leerHealth = useCallback(() => {
    api.health().then(setHealth).catch((e) => toast('error', 'No responde la API', String(e.message ?? e)));
  }, [toast]);
  const w = useWorkspace(onFinished, leerHealth);
  const vistos = useVistos();
  useFlechasEnGrupos();

  useEffect(() => {
    leerHealth();
    api.powerfactory().then(setPf).catch(() => undefined);
  }, [leerHealth]);

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
    try {
      const job = await fn();
      w.trackJob(job);
      return job;
    } catch (e) {
      toast('error', 'No se pudo completar', e instanceof Error ? e.message : String(e));
      // 086:RF-9: el servidor rechazó algo que la pantalla ofrecía: lo que se ve estaba viejo, y se pone al día.
      if (e instanceof ApiError && e.status === 400) void w.refresh().catch(() => undefined);
      return undefined;
    }
  }, [toast, w]);

  if (w.espacioNoAbre) return <EspacioNoDisponible {...w.espacioNoAbre} />;
  if (w.bootError) {
    // 086:RF-19: sin sesión el servidor sí está arrancado; el mensaje del servidor ya dice qué hacer.
    return <div className="boot"><h1>No se pudo abrir el espacio de trabajo</h1><p>{w.bootError}</p>
      {!w.bootError.includes('sesión') && <p className="muted">¿Está arrancado el servidor? <code>python -m convertersmartgrid.presentacion.web</code></p>}</div>;
  }
  if (!health || !w.state) return <div className="boot"><div className="spinner" /><p>Conectando con el conversor…</p></div>;

  const ctx: AppCtx = {
    ws: w.state, setWs: w.setState, health, pf, feeders: w.feeders, outputs: w.outputs, jobs: w.jobs,
    selected, setSelected, active, run, startJob, refresh: w.refresh, refreshHealth: leerHealth,
    librosNuevosSeq: w.librosNuevosSeq,
  };
  const running = [active.engine, active.powerfactory, active.asistente].filter(Boolean) as Job[];
  // RF-2: sin entradas, solo las pestañas que no las necesitan.
  // 086:RF-16: un asistente en beta apagado no se ofrece.
  const tabs = TABS.filter((t) => (w.state!.loaded || !t.entradas) && (t.id !== 'asistente' || betaActiva(health, 'asistente')));
  const actual = tabs.find((t) => t.id === tab) ?? tabs[0];
  const avisosPestana = avisosPorPestana(avisosDeTrabajos(w.jobs, w.state.id, vistos), tabs.map((t) => t.id));
  // 091:RF-8: en otro espacio solo se montan las que se abran en él.
  if (espacioVisto.current !== w.state.id) {
    espacioVisto.current = w.state.id;
    visitadas.current.clear();
  }
  visitadas.current.add(actual.id);
  const caps = health.capabilities;

  return (
    <Ctx.Provider value={ctx}>
    <AccionesOperadorCtx.Provider value={ACCIONES_OPERADOR}>
      <NubeEnEntradas>
      <a className="saltar" href="#contenido">Ir al contenido</a>
      <div className="app" style={{ gridTemplateRows: `auto 1fr 6px ${logHeight}px` }}>
        <header className="topbar">
          <div className="brand">
            <span className="logo" aria-hidden>⚡</span>
            <div>
              <h1>ConverterSmartGrid</h1>
              <span className="muted small">DIgSILENT PowerFactory · <AcercaDe version={health.version} /></span>
            </div>
          </div>
          <div className="caps">
            <Capacidad ok={Boolean(caps.geography)} etiqueta="GPS" detalle="pyproj" />
            <Capacidad ok={Boolean(caps.xlsx)} etiqueta="Excel" detalle="pandas + openpyxl" />
            <Capacidad ok={Boolean(caps.access)} etiqueta="Access" detalle="pyodbc" />
            {/* 103:RF-3: la instalación en uso; al pulsarla, las encontradas y la elección del operador. */}
            <button type="button" className="pill-boton" onClick={() => setVerPf(true)}
              title={pf ? `${pf.api_dir ?? 'sin API'}${pf.api_version ? ` · Python ${pf.api_version}` : ''} · ${pf.interpreter_reason} · pulse para elegir otra` : 'comprobando…'}>
              <Pill tone={pf?.available ? 'ok' : 'muted'}>
                <span aria-hidden="true">{pf?.available ? '✓' : '–'}</span> {textoPildoraPf(pf)}
                <span className="sr-only">{pf ? (pf.available ? ': disponible' : ': no disponible') : ': comprobando'}</span>
              </Pill>
            </button>
          </div>
          <div className="ws-id">
            <span className="muted small" title={w.state.id}>Espacio {w.state.id.slice(0, 6)}</span>
            <button className="btn btn-sm btn-ghost" disabled={running.length > 0}
              title={running.length > 0 ? 'Espere a que terminen los trabajos en curso' : undefined} onClick={async () => {
              if (await confirm('Nuevo espacio de trabajo', <p>Empezará con las entradas vacías. El espacio actual se conserva en el servidor.</p>, 'Crear')) {
                setSelected([]);
                await run(w.newWorkspace);
              }
            }}>Nuevo espacio</button>
          </div>
        </header>

        <main className="content" id="contenido" tabIndex={-1}>
          <AvisosDatos pestanas={tabs.map((t) => t.id)} />
          <JobBar jobs={running} />
          <div className="grid">
            <div className="col-side">
              <InputsPanel />
              <OptionsPanel />
              <ArchivoInformes />
              <CuentasNube />
              <PerfilEmpresa />
            </div>
            <div className="col-main">
              <FeedersPanel />
              <section className="card">
                {/* 086:RF-75: el aviso de un trabajo espera en su paso; la pestaña dice que lo hay. */}
                <PestanasModulos actual={actual.id} montadas={visitadas.current} onElegir={(id) => setTab(id as typeof tab)}
                  pestanas={tabs.map((t) => ({ id: t.id, avisos: avisosPestana[t.id],
                    etiqueta: <>{t.label}{t.id === 'asistente' && <> <MarcaBeta clave="asistente" /></>}
                      {/* 100:RF-12: el módulo dice si su cálculo está sin validar. */}
                      {refDePestana(t.id) && <> <MarcaValidacion {...refDePestana(t.id)!} /></>}</> }))} />
                {/* 091:RF-8: otro espacio las vuelve a montar, sin lo del anterior. */}
                <div key={w.state.id}>
                  {tabs.filter((t) => visitadas.current.has(t.id)).map((t) => (
                    <PanelPestana key={t.id} id={t.id} hidden={t.id !== actual.id}>{t.el}</PanelPestana>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </main>

        {/* WCAG 2.2: el borde del Registro se mueve con el ratón, con el teclado (flechas, Re Pág, Av Pág, Inicio y
            Fin) y con una pulsación, que lo pliega o lo devuelve a su altura (2.1.1 y 2.5.7). */}
        <div className="splitter" role="separator" aria-orientation="horizontal" aria-label="Altura del Registro"
          tabIndex={0} aria-valuemin={REGISTRO_MIN} aria-valuemax={alturaMaxima()} aria-valuenow={logHeight}
          aria-valuetext={`${logHeight} píxeles`}
          onKeyDown={(e) => {
            const h = alturaPorTecla(logHeight, e.key, alturaMaxima());
            if (h === null) return;
            e.preventDefault();
            setLogHeight(h);
            saveLogHeight(h);
          }}
          onPointerDown={(e) => {
            drag.current = { y: e.clientY, h: logHeight, movido: false };
            (e.target as HTMLElement).setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            const dy = e.clientY - drag.current.y;
            if (!drag.current.movido && Math.abs(dy) <= UMBRAL_PULSACION) return;
            drag.current.movido = true;
            setLogHeight(Math.min(alturaMaxima(), Math.max(REGISTRO_MIN, drag.current.h - dy)));
          }}
          onPointerUp={() => {
            const d = drag.current;
            drag.current = null;
            if (d && !d.movido) {
              const h = alturaAlPulsar(logHeight, antesDePlegar.current);
              antesDePlegar.current = h === REGISTRO_MIN ? logHeight : null;
              setLogHeight(h);
              saveLogHeight(h);
              return;
            }
            saveLogHeight(logHeight);
          }}
          onPointerCancel={() => { drag.current = null; }} />
        <LogPanel lines={w.log} onClear={() => w.setLog([])} connected={w.connected} />
      </div>
      {summary && <JobSummary job={summary} onClose={() => setSummary(null)} />}
      {verPf && <InstalacionesPowerFactoryModal onClose={() => setVerPf(false)}
        onCambio={() => { api.powerfactory(true).then(setPf).catch(() => undefined); }} />}
      </NubeEnEntradas>
    </AccionesOperadorCtx.Provider>
    </Ctx.Provider>
  );
}

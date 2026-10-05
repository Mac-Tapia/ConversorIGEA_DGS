import { Fragment, useMemo, useState } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type { Economia, LoteFeederResult, LotePlan, PfProject } from '../types';
import { FileDrop, Modal, Toggle, useToast } from './ui';

const ANIO = new Date().getFullYear();

/** Campos de la evaluación técnico-económica: [clave, etiqueta, valor inicial, ayuda]. */
const COSTOS: [keyof Economia['costos'], string, string, string][] = [
  ['sed_fijo_usd', 'Coste fijo por SED (US$)', '', 'Obra civil, montaje, protección.'],
  ['trafo_usd_por_kva', 'Transformador (US$/kVA)', '', 'Por kVA de placa.'],
  ['linea_usd_por_km', 'Derivación (US$/km)', '', 'Línea aérea nueva hasta el nodo.'],
  ['vida_util_anios', 'Vida útil (años)', '30', ''],
  ['valor_residual_pct', 'Valor residual (%)', '0', 'Del valor original, al final de la vida útil.'],
  ['om_pct_anual', 'O&M (% anual)', '0', 'De la inversión, cada año.'],
];
const TEC: [string, string, string, string][] = [
  ['inicio', 'Año inicial', String(ANIO), 'Las etapas deben activarse dentro del periodo.'],
  ['fin', 'Año final', String(ANIO + 20), ''],
  ['interes_pct', 'Tasa de descuento (%)', '12', ''],
  ['perdidas_usd_kwh', 'Pérdidas en carga (US$/kWh)', '', 'Pérdidas que dependen de la carga.'],
  ['perdidas_vacio_usd_kwh', 'Pérdidas en vacío (US$/kWh)', '', 'Pérdidas del hierro de los transformadores.'],
];

/**
 * Cargas en DIgSILENT por alimentador, sobre un proyecto que ya existe en PowerFactory.
 *
 * El operador elige el proyecto en un desplegable (leído de PowerFactory, no deducido de
 * lo que se importó desde este espacio) y los alimentadores. El orden en que los marca es
 * el orden en que se aplican: uno termina antes de empezar el siguiente. La actualización
 * va a un escenario nuevo por alimentador; las SED nuevas, a una variación nueva.
 */
export function LoteTab() {
  const { ws, run, startJob, active, jobs, feeders: rows } = useApp();
  const [project, setProject] = useState('');
  const [order, setOrder] = useState<string[]>([]);
  const [filter, setFilter] = useState('');
  const [updateFile, setUpdateFile] = useState<File | null>(null);
  const [createFile, setCreateFile] = useState<File | null>(null);
  const [plan, setPlan] = useState<LotePlan | null>(null);
  const [tecOn, setTecOn] = useState(false);
  const [eco, setEco] = useState<Record<string, string>>(
    Object.fromEntries([...COSTOS, ...TEC].map(([k, , v]) => [k, v])));
  const toast = useToast();

  /** Solo convierte texto a número; las reglas las valida la API (economia.py). */
  const economia = (): Economia | null | undefined => {
    if (!tecOn || !createFile) return null;
    const num = (k: string) => Number((eco[k] ?? '').trim().replace(',', '.') || '0');
    const malos = [...COSTOS, ...TEC].filter(([k]) => Number.isNaN(num(k))).map(([, l]) => l);
    if (malos.length) { toast('error', 'Dato no numérico', malos.join(', ')); return undefined; }
    return {
      costos: Object.fromEntries(COSTOS.map(([k]) => [k, num(k)])) as Economia['costos'],
      tec: {
        inicio: num('inicio'), fin: num('fin'), interes_pct: num('interes_pct'),
        perdidas_usd_kwh: num('perdidas_usd_kwh'), perdidas_vacio_usd_kwh: num('perdidas_vacio_usd_kwh'),
        puntos: 'anual',
      },
    };
  };

  // El resultado del último «Leer proyectos» que terminó bien.
  const lastRead = Object.values(jobs).filter((j) => j.kind === 'pf_projects' && j.status === 'done').pop();
  const projects = (lastRead?.result?.projects ?? []) as PfProject[];
  const lastBatch = Object.values(jobs).filter((j) => j.kind === 'lote' && j.status === 'done').pop();
  const batchResults = (lastBatch?.result?.results ?? []) as LoteFeederResult[];
  const current = projects.find((p) => p.name === project) ?? null;
  const loaded = useMemo(() => new Set(rows.map((r) => r.feeder)), [rows]);
  const pfBusy = Boolean(active.powerfactory);

  const visible = (current?.feeders ?? []).filter((f) => f.toLowerCase().includes(filter.trim().toLowerCase()));
  const toggle = (f: string) =>
    setOrder((o) => (o.includes(f) ? o.filter((x) => x !== f) : [...o, f]));

  const choose = (name: string) => {
    setProject(name);
    setOrder([]);
    setPlan(null);
  };

  const prepare = async () => {
    const e = economia();
    if (e === undefined) return;
    const p = await run(() => api.lotePlan(ws.id, project, order, updateFile, createFile, e));
    if (p) setPlan(p);
  };

  const apply = async () => {
    if (!plan) return;
    const job = await startJob(() => api.loteApply(ws.id, plan.token));
    if (job) setPlan(null);
  };

  return (
    <div className="module">
      <p className="muted">Aplica en un proyecto que ya existe en DIgSILENT la actualización de cargas y las SED nuevas
        de varios alimentadores, uno detrás de otro. Por alimentador, la actualización va a un <strong>escenario
        nuevo</strong> y las SED nuevas a una <strong>variación nueva</strong>, dibujadas en el unifilar.</p>
      <div className="steps">
        <div className="step-box">
          <h3>1 · Proyecto de DIgSILENT</h3>
          <div className="row">
            <button className="btn" disabled={pfBusy} onClick={() => startJob(() => api.pfProjects(ws.id))}>
              {projects.length ? 'Volver a leer proyectos' : 'Leer proyectos de DIgSILENT'}
            </button>
          </div>
          {projects.length > 0 && (
            <label className="field">
              <span>Proyecto</span>
              <select value={project} onChange={(e) => choose(e.target.value)}>
                <option value="">— elija un proyecto —</option>
                {projects.map((p) => (
                  <option key={p.name} value={p.name}>{p.name} ({p.feeders.length} alim.)</option>
                ))}
              </select>
            </label>
          )}
          {!projects.length && <small className="muted">Lee la lista de PowerFactory; tarda lo que tarde en abrirse.</small>}
        </div>

        <div className="step-box">
          <h3>2 · Excel con los alimentadores</h3>
          <FileDrop compact accept=".xlsx,.csv" onFiles={([f]) => { setUpdateFile(f); setPlan(null); }}>
            <span>{updateFile ? <>Actualización: <strong>{updateFile.name}</strong></> : <>Actualización de cargas: soltar o <u>elegir</u></>}</span>
          </FileDrop>
          <FileDrop compact accept=".xlsx,.csv" onFiles={([f]) => { setCreateFile(f); setPlan(null); }}>
            <span>{createFile ? <>SED nuevas: <strong>{createFile.name}</strong></> : <>SED nuevas: soltar o <u>elegir</u></>}</span>
          </FileDrop>
          <small className="muted">Un solo libro puede traer varios alimentadores: cada fila se asigna al alimentador
            al que pertenece la SED (o, si es nueva, al de su hoja o al más cercano a sus coordenadas).</small>
          {(updateFile || createFile) && (
            <button className="btn btn-ghost btn-sm" onClick={() => { setUpdateFile(null); setCreateFile(null); setPlan(null); }}>
              Quitar ficheros
            </button>
          )}
        </div>
      </div>

      {current && (
        <div className="step-box">
          <h3>3 · Alimentadores de {current.name}, en el orden de aplicación</h3>
          <div className="toolbar">
            <input className="search" type="search" placeholder="Filtrar alimentadores…" value={filter}
              onChange={(e) => setFilter(e.target.value)} />
            <button className="btn btn-sm btn-ghost" onClick={() =>
              setOrder((o) => [...o, ...visible.filter((f) => loaded.has(f) && !o.includes(f))])}>Marcar los visibles</button>
            <button className="btn btn-sm btn-ghost" disabled={!order.length} onClick={() => setOrder([])}>Ninguno</button>
            <span className="muted">{order.length} elegido(s)</span>
          </div>
          {current.feeders.length === 0 ? (
            <p className="empty">El proyecto no tiene alimentadores (ElmFeeder ni redes).</p>
          ) : (
            <div className="chips">
              {visible.map((f) => {
                const n = order.indexOf(f);
                const ok = loaded.has(f);
                return (
                  <button key={f} className={`chip ${n >= 0 ? 'on' : ''}`} disabled={!ok} onClick={() => toggle(f)}
                    title={ok ? 'El número es el orden en que se aplicará' : 'No está en las entradas cargadas en este espacio'}>
                    {n >= 0 ? `${n + 1}. ` : ''}{f}
                  </button>
                );
              })}
            </div>
          )}
          <small className="muted">Los desactivados no están en las entradas cargadas: sin su red no se puede preparar el plan.</small>
          <Toggle label="Evaluación técnico-económica de las SED nuevas (valor actual neto en DIgSILENT)"
            checked={tecOn && Boolean(createFile)} disabled={!createFile} onChange={setTecOn}
            hint="Lanza ComTececo con la inversión de cada variación de SED nuevas" />
          {!createFile && <small className="muted">Necesita el Excel de SED nuevas: es su inversión la que se evalúa.</small>}
          {tecOn && createFile && (
            <div className="form-grid">
              <p className="muted span-2">Cada variación de SED nuevas lleva su inversión en la etapa; al final se lanza
                la evaluación sobre todas juntas. Las pérdidas se evalúan con flujo de carga.</p>
              {[...COSTOS, ...TEC].map(([k, label, , help]) => (
                <label key={k} className="field">
                  <span>{label}</span>
                  <input value={eco[k]} inputMode="decimal" onChange={(e) => setEco((v) => ({ ...v, [k]: e.target.value }))} />
                  {help && <small className="muted">{help}</small>}
                </label>
              ))}
            </div>
          )}
          <div className="row">
            <button className="btn btn-primary" disabled={!order.length || (!updateFile && !createFile)} onClick={prepare}>
              Preparar plan
            </button>
          </div>
        </div>
      )}

      {batchResults.length > 0 && (
        <div className="step-box">
          <h3>Resultado por alimentador</h3>
          <div className="table-wrap table-short">
            <table className="table">
              <thead><tr><th>Alimentador</th><th>Estado</th><th>ComLdf</th>
                <th>Escenario / variación</th><th>Rollback</th></tr></thead>
              <tbody>{batchResults.map((result) => {
                const labels = {
                  APPLIED: 'Aplicado', ROLLED_BACK: 'Revertido',
                  ROLLBACK_FAILED: 'Revisión obligatoria',
                } as const;
                return <tr key={result.feeder}>
                  <td className="strong">{result.feeder}</td>
                  <td><span className={`badge ${result.status === 'APPLIED' ? 'ok' : result.status === 'ROLLED_BACK' ? 'warn' : 'err'}`}>
                    {labels[result.status]}</span></td>
                  <td>{result.comldf?.converged === true ? 'Convergente' : 'No convergente'}</td>
                  <td className="small">{result.actualizacion?.escenario ?? '—'}<br />
                    {result.creacion?.variacion ?? '—'}</td>
                  <td className="small">{result.rollback.status}
                    {result.rollback.errors?.length ? ` · ${result.rollback.errors.join('; ')}` : ''}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        </div>
      )}

      {plan && (
        <Modal wide title={`Plan para ${plan.project}`} onClose={() => setPlan(null)} actions={<>
          <button className="btn" onClick={() => setPlan(null)}>Cerrar</button>
          <button className="btn btn-pf" disabled={!plan.applicable || pfBusy} onClick={apply}>
            Aplicar en DIgSILENT ({plan.order.length} alim., en este orden)
          </button>
        </>}>
          {plan.row_errors.length > 0 && (
            <div className="alert alert-error"><strong>{plan.row_errors.length} error(es) — no se aplica nada hasta corregirlos.</strong>
              <ul>{plan.row_errors.slice(0, 30).map((e) => <li key={e}>{e}</li>)}</ul></div>
          )}
          {plan.without_changes.length > 0 && (
            <p className="alert alert-warn">Sin nada que aplicar en el Excel: {plan.without_changes.join(', ')}.</p>
          )}
          <div className="table-wrap table-short">
            <table className="table">
              <thead><tr><th className="num">#</th><th>Alimentador</th><th>Asignación</th><th>Escenario / variación</th><th className="num">SED a actualizar</th>
                <th className="num">SED nuevas</th>{plan.tec && <th className="num">Inversión (kUSD)</th>}
                <th>Avisos</th><th className="num">Errores</th></tr></thead>
              <tbody>{plan.feeders_summary.map((r, i) => (
                <Fragment key={r.feeder}>
                <tr>
                  <td className="num">{i + 1}</td>
                  <td className="strong">{r.feeder}</td>
                  <td className="small">{r.routing_basis.join(', ')}</td>
                  <td className="small">{r.scenario ?? '—'}<br />{r.variation ?? '—'}</td>
                  <td className="num">{fmtNum(r.updates)}</td>
                  <td className="num">{fmtNum(r.create)}</td>
                  {plan.tec && <td className="num">{fmtNum(r.inversion_kusd, 1)}</td>}
                  <td className="muted small">
                    {r.unknown.length > 0 && <>No existen (van a «SED nuevas»): {r.unknown.slice(0, 6).join(', ')}{r.unknown.length > 6 ? '…' : ''}. </>}
                    {r.already_exists.length > 0 && <>Ya existen (no se crean): {r.already_exists.slice(0, 6).join(', ')}{r.already_exists.length > 6 ? '…' : ''}.</>}
                  </td>
                  <td className="num">{r.errors}</td>
                </tr>
                {r.changes.length > 0 && <tr key={`${r.feeder}-changes`}><td colSpan={9}>
                  <details><summary>{r.changes.length} valor(es) actual / propuesto</summary>
                    <ul className="small">{r.changes.slice(0, 20).map((change) => <li key={change.sed}>
                      {change.sed}: before P/Q/FP {fmtNum(change.before.kw)} / {fmtNum(change.before.kvar)} / {fmtNum(change.before.fp, 3)}
                      {' → '}after {fmtNum(change.after.kw)} / {fmtNum(change.after.kvar)} / {fmtNum(change.after.fp, 3)}
                    </li>)}</ul>
                  </details>
                </td></tr>}
                </Fragment>
              ))}</tbody>
            </table>
          </div>
          <p className="muted">Por alimentador: escenario «Cargas_‹alim›_‹fecha›» con la actualización, y variación
            «SED_nuevas_‹alim›_‹fecha›» con las SED nuevas, dibujadas en el unifilar. No se pasa al siguiente hasta terminar.</p>
          {plan.tec && (
            <p className="muted">Al final: evaluación técnico-económica {plan.tec.inicio}–{plan.tec.fin} al {plan.tec.interes_pct} %
              sobre todas las variaciones del lote. El informe queda junto al resultado («.tececo.txt»).</p>
          )}
        </Modal>
      )}
    </div>
  );
}

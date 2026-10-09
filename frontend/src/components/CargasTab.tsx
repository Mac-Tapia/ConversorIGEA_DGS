import { useState, type FormEvent } from 'react';
import { api, download, fmtNum } from '../api';
import { useApp } from '../context';
import type {
  CargaConectada, CargasFeederInforme, CargasInforme, CargasMotivo, CargasPlan, CargasResultado,
  Economia, PfProject,
} from '../types';
import { PfWarning } from './Modules';
import { FileDrop, Modal, Toggle, useToast } from './ui';

const ANIO = new Date().getFullYear();

/** Campos de la evaluación técnico-económica: [clave, etiqueta, valor inicial, ayuda]. */
const COSTOS: [keyof Economia['costos'], string, string, string][] = [
  ['sed_fijo_usd', 'Coste fijo por SED (US$)', '', 'Obra civil, montaje, protección.'],
  ['trafo_usd_por_kva', 'Transformador (US$/kVA)', '', 'Por kVA de placa.'],
  ['linea_usd_por_km', 'Enlace (US$/km)', '', 'Línea nueva hasta la barra de conexión.'],
  ['vida_util_anios', 'Vida útil (años)', '30', ''],
  ['valor_residual_pct', 'Valor residual (%)', '0', 'Del valor original, al final de la vida útil.'],
  ['om_pct_anual', 'O&M (% anual)', '0', 'De la inversión, cada año.'],
];
const TEC: [string, string, string, string][] = [
  ['inicio', 'Año inicial', String(ANIO), 'La etapa debe activarse dentro del periodo.'],
  ['fin', 'Año final', String(ANIO + 20), ''],
  ['interes_pct', 'Tasa de descuento (%)', '12', ''],
  ['perdidas_usd_kwh', 'Pérdidas en carga (US$/kWh)', '', 'Pérdidas que dependen de la carga.'],
  ['perdidas_vacio_usd_kwh', 'Pérdidas en vacío (US$/kWh)', '', 'Pérdidas del hierro de los transformadores.'],
];

/**
 * Campos del formulario de una carga nueva. Las claves son las cabeceras de la plantilla:
 * el servidor pasa el formulario por el mismo lector que el libro, así que aquí no se
 * valida nada (habría dos definiciones de «fila válida»).
 */
const NUEVA_CAMPOS: { key: string; label: string; help?: string; required?: boolean }[] = [
  { key: 'SED', label: 'Código de la SED', required: true },
  { key: 'kVA_instalado', label: 'Transformador (kVA)', required: true },
  { key: 'Kw', label: 'Demanda (kW)' },
  { key: 'Kvar', label: 'Demanda (kVAR)', help: 'O bien kW y FP, o (kVA) y FP.' },
  { key: '(kVA)', label: 'Demanda (kVA)' },
  { key: 'FP', label: 'Factor de potencia' },
  { key: 'barra', label: 'Barra de conexión', help: 'En blanco: la barra más cercana por GPS.' },
  { key: 'Lat', label: 'Latitud (WGS84)' },
  { key: 'Lon', label: 'Longitud (WGS84)' },
  { key: 'CoordX', label: 'CoordX', help: 'En el CRS del perfil de empresa, si no hay Lat/Lon.' },
  { key: 'CoordY', label: 'CoordY' },
  { key: 'alimentador', label: 'Alimentador', help: 'En blanco: el que tenga la barra.' },
  { key: 'tipo_linea', label: 'Tipo de línea del enlace', help: 'En blanco o si no existe: el de la red.' },
  { key: 'tension_bt_kv', label: 'Tensión de baja (kV)', help: 'En blanco: la de un transformador del alimentador.' },
];

const vacio = () => Object.fromEntries(NUEVA_CAMPOS.map((c) => [c.key, '']));

/**
 * Cargas en un proyecto que ya existe en DIgSILENT (spec 004).
 *
 * Es un módulo aparte de la conversión: no pide entradas cargadas en el espacio. La web
 * solo valida los libros; qué SED coincide y dónde se conecta cada carga nueva lo decide
 * el guion dentro del proyecto. Todo queda en una variación nueva, para uno o varios
 * alimentadores, que se aplican en el orden en que se marcan.
 */
export function CargasTab() {
  const { ws, run, startJob, active, jobs } = useApp();
  const [project, setProject] = useState('');
  const [order, setOrder] = useState<string[]>([]);
  const [filter, setFilter] = useState('');
  const [demandas, setDemandas] = useState<File | null>(null);
  const [nuevas, setNuevas] = useState<File | null>(null);
  const [nueva, setNueva] = useState<Record<string, string> | null>(null);
  const [form, setForm] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(vacio);
  const [plan, setPlan] = useState<CargasPlan | null>(null);
  const [tecOn, setTecOn] = useState(false);
  const [eco, setEco] = useState<Record<string, string>>(
    Object.fromEntries([...COSTOS, ...TEC].map(([k, , v]) => [k, v])));
  const toast = useToast();

  const hayNuevas = Boolean(nuevas || nueva);
  const pfBusy = Boolean(active.powerfactory);

  // El resultado del último «Leer proyectos» que terminó bien.
  const lastRead = Object.values(jobs).filter((j) => j.kind === 'pf_projects' && j.status === 'done').pop();
  const projects = (lastRead?.result?.projects ?? []) as PfProject[];
  const current = projects.find((p) => p.name === project) ?? null;
  // Un trabajo cancelado también deja informe: dice qué alimentadores no se empezaron.
  const lastRun = Object.values(jobs)
    .filter((j) => (j.kind === 'cargas_simular' || j.kind === 'cargas_aplicar') && j.result)
    .pop();
  const resultado = (lastRun?.result ?? null) as CargasResultado | null;

  const visible = (current?.feeders ?? []).filter((f) => f.toLowerCase().includes(filter.trim().toLowerCase()));
  const toggle = (f: string) => setOrder((o) => (o.includes(f) ? o.filter((x) => x !== f) : [...o, f]));
  const choose = (name: string) => { setProject(name); setOrder([]); setPlan(null); };

  /** Solo convierte texto a número; las reglas las valida la API (economia.py). */
  const economia = (): Economia | null | undefined => {
    if (!tecOn || !hayNuevas) return null;
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

  const prepare = async () => {
    const e = economia();
    if (e === undefined) return;
    const p = await run(() => api.cargasPlan(ws.id, project, order, demandas, nuevas, nueva, e));
    if (p) setPlan(p);
  };

  const ejecutar = async (simular: boolean) => {
    if (!plan) return;
    const job = await startJob(() => (simular ? api.cargasSimular : api.cargasAplicar)(ws.id, plan.token));
    if (job) setPlan(null);
  };

  const guardarNueva = (e: FormEvent) => {
    e.preventDefault();
    const llenos = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim()]));
    if (!llenos.SED) { toast('error', 'Falta el código de la SED', ''); return; }
    setNueva(llenos);
    setPlan(null);
    setForm(false);
  };

  const plantilla = (tipo: 'demandas' | 'nuevas') => (
    <span className="row">
      <button className="btn btn-sm btn-ghost" onClick={() => run(() => download(api.cargasPlantillaUrl(ws.id, tipo, 'xlsx')))}>Plantilla Excel</button>
      <button className="btn btn-sm btn-ghost" onClick={() => run(() => download(api.cargasPlantillaUrl(ws.id, tipo, 'csv')))}>CSV</button>
    </span>
  );

  return (
    <div className="module">
      <p className="muted">Trabaja sobre un proyecto que <strong>ya existe</strong> en DIgSILENT, sin convertir nada: actualiza
        las demandas por SED y conecta cargas nuevas, en uno o en varios alimentadores. Todo queda en una
        <strong> variación nueva</strong>, que se puede activar, comparar o borrar sin tocar la red base.</p>
      <PfWarning />
      <div className="steps">
        <div className="step-box">
          <h3>1 · Proyecto de DIgSILENT</h3>
          <div className="row">
            <button className="btn" disabled={pfBusy} onClick={() => startJob(() => api.pfProjects(ws.id))}>
              {projects.length ? 'Volver a leer proyectos' : 'Leer proyectos de DIgSILENT'}
            </button>
          </div>
          {projects.length > 0 ? (
            <label className="field">
              <span>Proyecto</span>
              <select value={project} onChange={(e) => choose(e.target.value)}>
                <option value="">— elija un proyecto —</option>
                {projects.map((p) => (
                  <option key={p.name} value={p.name}>{p.name} ({p.feeders.length} alim.)</option>
                ))}
              </select>
            </label>
          ) : <small className="muted">Lee la lista de DIgSILENT; tarda lo que tarde en abrirse.</small>}
        </div>

        <div className="step-box">
          <h3>2 · Qué aplicar</h3>
          <div className="field">
            <span>Demandas en bloque {plantilla('demandas')}</span>
            <FileDrop compact accept=".xlsx,.csv" onFiles={([f]) => { setDemandas(f); setPlan(null); }}>
              <span>{demandas ? <strong>{demandas.name}</strong> : <>Libro de demandas: soltar o <u>elegir</u></>}</span>
            </FileDrop>
          </div>
          <div className="field">
            <span>Cargas nuevas en bloque {plantilla('nuevas')}</span>
            <FileDrop compact accept=".xlsx,.csv" onFiles={([f]) => { setNuevas(f); setPlan(null); }}>
              <span>{nuevas ? <strong>{nuevas.name}</strong> : <>Libro de cargas nuevas: soltar o <u>elegir</u></>}</span>
            </FileDrop>
          </div>
          <div className="row">
            <button className="btn btn-sm" onClick={() => setForm(true)}>
              {nueva ? `Carga nueva: ${nueva.SED} (editar)` : 'Una carga nueva…'}
            </button>
            {(demandas || nuevas || nueva) && (
              <button className="btn btn-ghost btn-sm" onClick={() => {
                setDemandas(null); setNuevas(null); setNueva(null); setValues(vacio()); setPlan(null);
              }}>Quitar todo</button>
            )}
          </div>
          <small className="muted">Un libro puede traer varios alimentadores. Una SED que no está en los elegidos se
            omite y se informa; no es un error.</small>
        </div>
      </div>

      {current && (
        <div className="step-box">
          <h3>3 · Alimentadores de {current.name}, en el orden de aplicación</h3>
          <div className="toolbar">
            <input className="search" type="search" placeholder="Filtrar alimentadores…" value={filter}
              onChange={(e) => setFilter(e.target.value)} />
            <button className="btn btn-sm btn-ghost" onClick={() =>
              setOrder((o) => [...o, ...visible.filter((f) => !o.includes(f))])}>Marcar los visibles</button>
            <button className="btn btn-sm btn-ghost" disabled={!order.length} onClick={() => setOrder([])}>Ninguno</button>
            <span className="muted">{order.length} elegido(s)</span>
          </div>
          {current.feeders.length === 0 ? (
            <p className="empty">El proyecto no tiene alimentadores (ElmFeeder ni redes).</p>
          ) : (
            <div className="chips">
              {visible.map((f) => {
                const n = order.indexOf(f);
                return (
                  <button key={f} className={`chip ${n >= 0 ? 'on' : ''}`} onClick={() => toggle(f)}
                    title="El número es el orden en que se aplicará">
                    {n >= 0 ? `${n + 1}. ` : ''}{f}
                  </button>
                );
              })}
            </div>
          )}
          <Toggle label="Evaluación técnico-económica de las cargas nuevas (valor actual neto en DIgSILENT)"
            checked={tecOn && hayNuevas} disabled={!hayNuevas} onChange={setTecOn}
            hint="Lanza ComTececo con la inversión de la variación" />
          {tecOn && hayNuevas && (
            <div className="form-grid">
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
            <button className="btn btn-primary" disabled={!order.length || (!demandas && !hayNuevas)} onClick={prepare}>
              Revisar los libros
            </button>
            {!order.length && <small className="muted">Elija al menos un alimentador.</small>}
          </div>
        </div>
      )}

      {resultado && <Informe resultado={resultado} cancelado={lastRun?.status === 'cancelled'} />}

      {form && (
        <Modal title="Una carga nueva" onClose={() => setForm(false)} actions={<>
          <button className="btn" onClick={() => setForm(false)}>Cancelar</button>
          <button className="btn btn-primary" type="submit" form="carga-nueva">Usar esta carga</button>
        </>}>
          <form id="carga-nueva" className="form-grid" onSubmit={guardarNueva}>
            <p className="muted span-2">Indique la barra de conexión o las coordenadas. Se valida al revisar, con las
              mismas reglas que el libro.</p>
            {NUEVA_CAMPOS.map((c) => (
              <label key={c.key} className="field">
                <span>{c.label}{c.required && <span className="req">*</span>}</span>
                <input value={values[c.key]} onChange={(e) => setValues((v) => ({ ...v, [c.key]: e.target.value }))} />
                {c.help && <small className="muted">{c.help}</small>}
              </label>
            ))}
          </form>
        </Modal>
      )}

      {plan && (
        <Modal wide title={`Plan para ${plan.project}`} onClose={() => setPlan(null)} actions={<>
          <button className="btn" onClick={() => setPlan(null)}>Cerrar</button>
          <button className="btn" disabled={!plan.applicable || pfBusy} onClick={() => ejecutar(true)}
            title="Dice qué coincide y dónde se conectaría cada carga, sin escribir en el proyecto">
            Simular en DIgSILENT
          </button>
          <button className="btn btn-pf" disabled={!plan.applicable || pfBusy} onClick={() => ejecutar(false)}>
            Aplicar ({plan.feeders.length} alim., en este orden)
          </button>
        </>}>
          <p>Variación nueva: <strong className="mono">{plan.variacion}</strong> · alimentadores: {plan.feeders.join(' → ')}</p>
          <p>{fmtNum(plan.n_demandas)} demanda(s) y {fmtNum(plan.n_nuevas)} carga(s) nueva(s) válidas. Qué SED coincide
            lo decide DIgSILENT: simule para verlo antes de aplicar.</p>
          {!plan.applicable && <p className="alert alert-error">Ninguna fila válida: no hay nada que aplicar.</p>}
          {plan.row_errors.length > 0 && (
            <div className="alert alert-warn"><strong>{plan.row_errors.length} fila(s) con error: se omiten, el resto se aplica.</strong>
              <ul>{plan.row_errors.slice(0, 30).map((e) => <li key={e}>{e}</li>)}</ul>
              {plan.row_errors.length > 30 && <small>… y {plan.row_errors.length - 30} más.</small>}</div>
          )}
          {plan.omitidas_por_el_operador.length > 0 && (
            <p className="muted">Marcadas «omitir» en el libro: {lista(plan.omitidas_por_el_operador)}</p>
          )}
          {plan.sin_datos.length > 0 && <p className="muted">Sin demanda en el libro: {lista(plan.sin_datos)}</p>}
          {plan.nuevas.length > 0 && (
            <div className="table-wrap table-short">
              <table className="table">
                <thead><tr><th>Carga nueva</th><th className="num">kVA</th><th className="num">kW</th><th className="num">kVAR</th>
                  <th>Conexión</th><th>Alimentador</th></tr></thead>
                <tbody>{plan.nuevas.map((n) => (
                  <tr key={`${n.hoja}-${n.sed}`}><td className="strong">{n.sed}</td><td className="num">{fmtNum(n.kva_instalado)}</td>
                    <td className="num">{fmtNum(n.kw, 1)}</td><td className="num">{fmtNum(n.kvar, 1)}</td>
                    <td className="small">{n.barra ? `barra ${n.barra}` : `GPS ${fmtNum(n.lat ?? 0, 5)}, ${fmtNum(n.lon ?? 0, 5)}`}</td>
                    <td className="small">{n.alimentador || '—'}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
          {plan.tec && (
            <p className="muted">Al final: evaluación técnico-económica {plan.tec.inicio}–{plan.tec.fin} al {plan.tec.interes_pct} %
              sobre la variación.</p>
          )}
        </Modal>
      )}
    </div>
  );
}

function lista(xs: string[], n = 12): string {
  return xs.slice(0, n).join(', ') + (xs.length > n ? ` … (${xs.length})` : '');
}

function motivos(titulo: string, xs: CargasMotivo[], tono: 'warn' | 'error') {
  if (!xs.length) return null;
  return (
    <details className={`alert alert-${tono}`}>
      <summary>{titulo}: {xs.length}</summary>
      <ul className="small">{xs.slice(0, 200).map((x) => <li key={`${x.sed}-${x.motivo}`}><strong>{x.sed}</strong>: {x.motivo}</li>)}</ul>
    </details>
  );
}

function conexion(c: CargaConectada) {
  const dist = c.distancia_m != null ? ` a ${fmtNum(c.distancia_m)} m` : '';
  return <>{c.barra} <span className="muted">({c.criterio}{dist})</span></>;
}

/** Informe del guion por alimentador: lo que se actualizó o se crearía, y lo omitido (RF-20). */
function Informe({ resultado, cancelado }: { resultado: CargasResultado; cancelado: boolean }) {
  const inf: CargasInforme = resultado.informe;
  const simular = inf.modo === 'simular';
  return (
    <div className="step-box">
      <h3>{simular ? 'Simulación' : 'Aplicación'} en {inf.project}{inf.variacion ? ` · variación ${inf.variacion}` : ''}</h3>
      {simular && <p className="muted">Nada se ha escrito en el proyecto.</p>}
      {(inf.cancelado || cancelado) && <p className="alert alert-warn">Cancelado: el alimentador en curso terminó y no se empezó ninguno más.</p>}
      {inf.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {inf.flujo && (
        <p className={inf.flujo.converged ? '' : 'alert alert-error'}>
          Flujo de carga con la variación activa: <strong>{inf.flujo.converged ? 'converge' : 'no converge'}</strong>
          {inf.flujo.vm_min != null && <> · tensión mínima {fmtNum(inf.flujo.vm_min, 3)} p.u. ({inf.flujo.vm_min_bus}),
            máxima {fmtNum(inf.flujo.vm_max ?? 0, 3)} p.u. ({inf.flujo.vm_max_bus})</>}
        </p>
      )}
      {inf.tecnico_economico && (
        <details><summary>Evaluación técnico-económica: {inf.tecnico_economico.ok ? 'hecha' : inf.tecnico_economico.error ?? 'falló'}</summary>
          <pre className="report">{(inf.tecnico_economico.resumen ?? []).join('\n')}</pre></details>
      )}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Alimentador</th><th className="num">{simular ? 'Se actualizarían' : 'Actualizadas'}</th>
            <th className="num">{simular ? 'Se crearían' : 'Creadas'}</th><th className="num">Fallos</th></tr></thead>
          <tbody>{inf.feeders.map((f) => <FilaFeeder key={f.feeder} f={f} simular={simular} />)}</tbody>
        </table>
      </div>
      {motivos('SED sin coincidencia en los alimentadores elegidos (omitidas)', inf.sin_alimentador, 'warn')}
      {motivos('Ambiguas (omitidas)', inf.ambiguas, 'warn')}
      {motivos('Cargas nuevas no creadas', inf.no_creadas, 'warn')}
      {(inf.plan_errores_de_fila ?? []).length > 0 && (
        <p className="muted">{inf.plan_errores_de_fila!.length} fila(s) con error en los libros no se enviaron.</p>
      )}
      <small className="muted">Informe completo: {resultado.report}, en «Resultados».</small>
    </div>
  );
}

function FilaFeeder({ f, simular }: { f: CargasFeederInforme; simular: boolean }) {
  const act = (simular ? f.actualizarian : f.actualizadas) ?? [];
  const cre = (simular ? f.crearian : f.creadas) ?? [];
  const fallos = f.fallos ?? [];
  const kw = (foto: Record<string, unknown>) => (typeof foto.plini === 'number' ? fmtNum(foto.plini * 1000, 1) : '—');
  const kwDespues = (d: Record<string, unknown>) => (typeof d.kw === 'number' ? fmtNum(d.kw, 1) : kw(d));
  return <>
    <tr>
      <td className="strong">{f.feeder}</td>
      <td className="num">{fmtNum(act.length)}</td>
      <td className="num">{fmtNum(cre.length)}</td>
      <td className="num">{fallos.length ? <span className="badge err">{fallos.length}</span> : 0}</td>
    </tr>
    {(act.length > 0 || cre.length > 0 || fallos.length > 0) && <tr><td colSpan={4}>
      <details><summary>Detalle</summary>
        {act.length > 0 && <ul className="small">{act.slice(0, 200).map((a) => (
          <li key={a.sed}>{a.sed}: {kw(a.antes)} → {kwDespues(a.despues)} kW</li>))}</ul>}
        {cre.length > 0 && <ul className="small">{cre.map((c) => (
          <li key={c.sed}><strong>{c.sed}</strong> en {conexion(c)} · línea {c.tipo_linea ?? '—'}
            {c.origen_tipo_linea ? ` (${c.origen_tipo_linea})` : ''} · {fmtNum(c.tension_mt_kv ?? 0, 2)}/{fmtNum(c.tension_bt_kv ?? 0, 2)} kV
            {c.aviso ? ` · ${c.aviso}` : ''}</li>))}</ul>}
        {fallos.length > 0 && <ul className="small">{fallos.map((x) => <li key={x.sed}><strong>{x.sed}</strong>: {x.error}</li>)}</ul>}
      </details>
    </td></tr>}
  </>;
}

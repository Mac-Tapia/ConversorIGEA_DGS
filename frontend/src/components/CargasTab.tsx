import { useEffect, useState, type FormEvent } from 'react';
import { api, download, fmtNum } from '../api';
import { useApp } from '../context';
import type {
  AjusteInforme, AjusteResultado, CalibradaCambiada, CargaConectada, CargaIntegrada, CargasFeederInforme,
  CargasInforme, CargasMotivo, CargasPlan, CargasResultado, Economia, Job, PfInventario, PfProject,
  VerificarInforme, VerificarResultado,
} from '../types';
import { estadoVinculoProyecto } from '../projectBinding';
import { DemandaMedida } from './DemandaMedida';
import { EstudiosPF } from './EstudiosPF';
import { ObrasPF } from './ObrasPF';
import { PfWarning } from './Modules';
import { TransferenciaPF } from './TransferenciaPF';
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
 *
 * Spec 004, RF-46 y RF-47: la demanda se escribe como kW y FP, y la ubicación por
 * coordenadas. Con los cuatro campos de potencia a la vista el operador no sabía cuáles
 * llenar; kVAR y kVA siguen en el libro. Lo que casi nunca hace falta (`mas`) va plegado.
 */
const NUEVA_CAMPOS: { key: string; label: string; help?: string; required?: boolean; mas?: boolean }[] = [
  { key: 'SED', label: 'Código de la SED', required: true },
  { key: 'kVA_instalado', label: 'Transformador (kVA)', required: true },
  { key: 'Kw', label: 'Potencia activa (kW)', required: true },
  { key: 'FP', label: 'Factor de potencia', required: true, help: 'Entre 0 y 1, p. ej. 0.95.' },
  { key: 'Lat', label: 'Latitud (WGS84)', help: 'Se conecta a la barra de media más cercana.' },
  { key: 'Lon', label: 'Longitud (WGS84)' },
  { key: 'CoordX', label: 'CoordX', mas: true, help: 'En el CRS del perfil de empresa, en lugar de Lat/Lon.' },
  { key: 'CoordY', label: 'CoordY', mas: true },
  { key: 'barra', label: 'Barra de conexión', mas: true, help: 'Solo para forzar una barra; si no, la más cercana.' },
  { key: 'alimentador', label: 'Alimentador', mas: true, help: 'En blanco: el que tenga la barra.' },
  { key: 'tipo_linea', label: 'Tipo de línea del enlace', mas: true, help: 'En blanco o si no existe: el de la red.' },
  { key: 'tension_bt_kv', label: 'Tensión de baja (kV)', mas: true, help: 'En blanco: la de un transformador del alimentador.' },
];
const TEXTO = new Set(['SED', 'barra', 'alimentador', 'tipo_linea']);

const vacio = () => Object.fromEntries(NUEVA_CAMPOS.map((c) => [c.key, '']));

/** Estado del último flujo de carga del proyecto (spec 008, RF-20). */
interface EstadoFlujo {
  converge: boolean;
  /** De dónde sale: la verificación, el ajuste o la última integración aplicada. */
  fuente: string;
  cuando: number;
}

/**
 * El último flujo del proyecto entre la verificación, el ajuste aplicado y la
 * integración aplicada. Un ajuste converge si cada alimentador ajustado terminó con
 * cabecera medida y sin error: que no cuadre no impide integrar (spec 007, RF-34).
 */
export function estadoFlujo(jobs: Job[], project: string): EstadoFlujo | null {
  let mejor: EstadoFlujo | null = null;
  for (const j of jobs) {
    if (!j.result || j.status === 'failed' || !project) continue;
    const cuando = j.finished_at ?? j.created_at;
    let e: EstadoFlujo | null = null;
    if (j.kind === 'pf_verificar' && j.result.project === project) {
      e = { converge: Boolean(j.result.informe?.flujo?.converged), fuente: 'verificación', cuando };
    } else if (j.kind === 'ajuste_aplicar' && j.result.project === project) {
      const informes = ((j.result.informes ?? [j.result.informe]) as AjusteInforme[]).filter((i) => !i.no_empezado);
      e = { converge: informes.length > 0 && informes.every((i) => !i.error && i.cabecera != null),
        fuente: 'ajuste a la máxima', cuando };
    } else if (j.kind === 'cargas_aplicar' && (j.result.project ?? j.result.informe?.project_path) === project
      && j.result.informe?.flujo) {
      e = { converge: Boolean(j.result.informe.flujo.converged), fuente: 'última integración', cuando };
    }
    if (e && (!mejor || e.cuando >= mejor.cuando)) mejor = e;
  }
  return mejor;
}

/**
 * Cargas en un proyecto que ya existe en DIgSILENT (specs 004, 006 y 008).
 *
 * Es un módulo aparte de la conversión: no pide entradas cargadas en el espacio, y por
 * eso la pestaña se ve siempre (spec 008, RF-1). Sigue el orden del trabajo del
 * operador: 1, el proyecto; 2, sus alimentadores y la calibración a la máxima de
 * cabecera; 3, verificar que converge e integrar lo nuevo. Qué SED coincide y dónde se
 * conecta cada carga nueva lo decide el guion dentro del proyecto.
 */
export function CargasTab() {
  const { ws, run, startJob, active, jobs } = useApp();
  const [project, setProject] = useState('');
  const [buscaProyecto, setBuscaProyecto] = useState('');
  const [order, setOrder] = useState<string[]>([]);
  const [filter, setFilter] = useState('');
  const [demandas, setDemandas] = useState<File | null>(null);
  const [nuevas, setNuevas] = useState<File | null>(null);
  const [nueva, setNueva] = useState<Record<string, string> | null>(null);
  const [form, setForm] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(vacio);
  const [plan, setPlan] = useState<CargasPlan | null>(null);
  const [tecOn, setTecOn] = useState(false);
  // Spec 007, RF-4: el operador puede quitar la base y aplicar sobre lo activo.
  const [sinBase, setSinBase] = useState(false);
  const [eco, setEco] = useState<Record<string, string>>(
    Object.fromEntries([...COSTOS, ...TEC].map(([k, , v]) => [k, v])));
  const toast = useToast();

  const hayNuevas = Boolean(nuevas || nueva);
  const pfBusy = Boolean(active.powerfactory);
  const todos = Object.values(jobs);

  // El resultado del último «Leer proyectos» que terminó bien.
  const lastRead = todos.filter((j) => j.kind === 'pf_projects' && j.status === 'done').pop();
  const inventario = (lastRead?.result ?? null) as PfInventario | null;
  const projects = inventario?.projects ?? [];
  // El proyecto se identifica por su ruta en la carpeta: dos SI213 en subcarpetas
  // distintas son dos proyectos (spec 005, RF-16).
  const ruta = (p: PfProject) => p.path ?? p.name;
  const current = projects.find((p) => ruta(p) === project) ?? null;
  const bindingState = estadoVinculoProyecto(current);
  const bindingBlocked = bindingState.bloqueado;
  // RF-4: filtrar por parte de la ruta; el elegido sigue en la lista aunque no coincida.
  const q = buscaProyecto.trim().toLowerCase();
  const filtrados = projects.filter((p) => !q || ruta(p).toLowerCase().includes(q) || ruta(p) === project);
  // Un trabajo cancelado también deja informe: dice qué alimentadores no se empezaron.
  const lastRun = todos
    .filter((j) => (j.kind === 'cargas_simular' || j.kind === 'cargas_aplicar') && j.result)
    .pop();
  const resultado = (lastRun?.result ?? null) as CargasResultado | null;
  const flujo = estadoFlujo(todos, project);
  const lastCheck = todos.filter((j) => j.kind === 'pf_verificar' && j.result?.project === project).pop();
  const verificado = (lastCheck?.result ?? null) as VerificarResultado | null;
  // Spec 007, RF-1: la base es el último ajuste aplicado de este proyecto.
  const baseJob = todos.filter((j) => j.kind === 'ajuste_aplicar' && j.result?.project === project
    && j.status !== 'failed').pop();
  const ajusteBase = (baseJob?.result ?? null) as AjusteResultado | null;
  const informesBase = ajusteBase ? (ajusteBase.informes ?? [ajusteBase.informe]) : [];
  const conBase = Boolean(baseJob) && !sinBase
    && informesBase.some((i) => i.variacion && !i.error && !i.no_empezado);
  // Un ajuste nuevo vuelve a proponerse como base aunque se quitara la anterior.
  useEffect(() => { setSinBase(false); setPlan(null); }, [baseJob?.id]);

  const visible = (current?.feeders ?? []).filter((f) => f.toLowerCase().includes(filter.trim().toLowerCase()));
  const toggle = (f: string) => setOrder((o) => (o.includes(f) ? o.filter((x) => x !== f) : [...o, f]));
  // RF-6: al elegir un proyecto se marcan todos sus alimentadores.
  const choose = (name: string) => {
    setProject(name);
    setOrder(projects.find((p) => ruta(p) === name)?.feeders ?? []);
    setPlan(null);
  };

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
    const p = await run(() => api.cargasPlan(ws.id, project, order, demandas, nuevas, nueva, e,
      conBase ? baseJob!.id : null));
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

  const campoNueva = (c: (typeof NUEVA_CAMPOS)[number]) => (
    <label key={c.key} className="field">
      <span>{c.label}{c.required && <span className="req">*</span>}</span>
      <input value={values[c.key]} inputMode={TEXTO.has(c.key) ? undefined : 'decimal'}
        onChange={(e) => setValues((v) => ({ ...v, [c.key]: e.target.value }))} />
      {c.help && <small className="muted">{c.help}</small>}
    </label>
  );

  const plantilla = (tipo: 'demandas' | 'nuevas') => (
    <span className="row">
      <button className="btn btn-sm btn-ghost" onClick={() => run(() => download(api.cargasPlantillaUrl(ws.id, tipo, 'xlsx')))}>Plantilla Excel</button>
      <button className="btn btn-sm btn-ghost" onClick={() => run(() => download(api.cargasPlantillaUrl(ws.id, tipo, 'csv')))}>CSV</button>
    </span>
  );
  // RF-20: aplicar solo con el último flujo del proyecto convergido; simular, siempre (RF-21).
  const porQueNoAplicar = !flujo
    ? 'Verifique antes la convergencia (3.0) o ajuste a la máxima en el paso 2.'
    : !flujo.converge ? `El último flujo del proyecto (${flujo.fuente}) no converge: corríjalo y vuelva a verificar.` : '';
  const quien = order.length === 1 ? order[0] : `${order.length} alimentadores`;

  return (
    <div className="module">
      <p className="muted">Trabaja sobre un proyecto que <strong>ya existe</strong> en DIgSILENT, sin convertir nada: calibra
        las demandas a la máxima de cabecera y, sobre esa red, integra demandas y cargas nuevas. Cada cambio queda en
        una <strong>variación nueva</strong>, que se puede activar, comparar o borrar sin tocar la red base.</p>
      <PfWarning />

      <div className="step-box">
        <h3>1 · Proyecto de DIgSILENT</h3>
        <div className="row">
          <button className="btn" disabled={pfBusy} onClick={() => startJob(() => api.pfProjects(ws.id))}>
            {projects.length ? 'Volver a leer proyectos' : 'Leer proyectos de DIgSILENT'}
          </button>
        </div>
        {projects.length > 0 ? (
          <div className="row">
            <label className="field">
              <span>Buscar</span>
              <input className="search" type="search" placeholder="parte del nombre o de la carpeta…" value={buscaProyecto}
                onChange={(e) => setBuscaProyecto(e.target.value)} />
            </label>
            <label className="field">
              <span>Proyecto ({filtrados.length} de {projects.length})</span>
              <select value={project} onChange={(e) => choose(e.target.value)}>
                <option value="">— elija un proyecto —</option>
                {filtrados.map((p) => (
                  <option key={ruta(p)} value={ruta(p)}>
                    {ruta(p).split('/').join(' / ')} ({p.feeders.length} alim.)
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : !inventario?.aviso && (
          <small className="muted">Lee los proyectos de la carpeta de importación de DIgSILENT.</small>
        )}
        {projects.length > 0 && q && !projects.some((p) => ruta(p).toLowerCase().includes(q)) && (
          <small className="alert alert-warn">Ningún proyecto coincide con «{buscaProyecto.trim()}».</small>
        )}
        {inventario?.aviso && <small className="alert alert-warn">{inventario.aviso}</small>}
        {inventario?.exists && inventario.folder && (
          <small className="muted">
            Carpeta «{inventario.folder}»{projects.length ? '' : ': sin proyectos todavía'}.
          </small>
        )}
        {current?.binding && !current.binding_blocked_reason ? (
          <div className="callout">
            <strong>Proyecto vinculado y relectura identificada</strong>
            <div className="kv-grid">
              <span>Ejecución fuente</span><code>{current.binding.source_run_id}</code>
              <span>Huella fuente</span><code>{current.binding.source_fingerprint.slice(0, 12)}…</code>
              <span>Alimentadores</span><span>{current.binding.feeders.join(', ')}</span>
              <span>Última relectura nativa</span>
              <span>{current.binding.native_reread.status} · {current.binding.native_inventory_sha256.slice(0, 12)}…
                {current.native_reread_at ? ` · ${new Date(current.native_reread_at * 1000).toLocaleString('es-PE')}` : ''}</span>
            </div>
            {current.native_warning && <small className="alert alert-warn">{current.native_warning}</small>}
            {(current.binding_warnings ?? []).map((warning) => (
              <div className="alert alert-warn" key={warning.code}>
                <strong>{warning.message}</strong>
                {warning.elements.length > 0 && (
                  <details>
                    <summary>{warning.elements.length} elemento(s) modificados</summary>
                    <ul className="small">{warning.elements.map((element) => (
                      <li key={`${element.change}:${element.class}:${element.full_name}`}>
                        {element.change === 'added' ? 'Agregado' : element.change === 'removed' ? 'Eliminado' : 'Modificado'}:
                        {' '}<code>{element.class}</code> {element.full_name}
                      </li>
                    ))}</ul>
                  </details>
                )}
              </div>
            ))}
          </div>
        ) : current ? (
          <small className="alert alert-warn">
            {current.binding_blocked_reason || 'PROJECT_BINDING_MISSING: importe y acepte este proyecto desde la ejecución fuente activa.'}
          </small>
        ) : null}
      </div>

      <fieldset disabled={bindingBlocked} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <div className="step-box">
        <h3>2 · Alimentadores y calibración{current ? ` de ${current.name}` : ''}</h3>
        {!current ? <p className="muted">Elija un proyecto en el paso 1.</p> : <>
          <p className="muted">Se calibran y se integran los alimentadores marcados, en el orden en que se marcan. Con dos o más,
            cada uno se ajusta a la máxima de su propia cabecera.</p>
          <div className="toolbar">
            <input className="search" type="search" placeholder="Filtrar alimentadores…" value={filter}
              onChange={(e) => setFilter(e.target.value)} />
            <button className="btn btn-sm btn-ghost" onClick={() =>
              setOrder((o) => [...o, ...visible.filter((f) => !o.includes(f))])}>Marcar los visibles</button>
            <button className="btn btn-sm btn-ghost" disabled={!order.length} onClick={() => setOrder([])}>Ninguno</button>
            <span className="muted">{order.length} de {current.feeders.length} marcado(s)</span>
          </div>
          {current.feeders.length === 0 ? (
            <p className="empty">El proyecto no tiene alimentadores (ElmFeeder ni redes).</p>
          ) : (
            <div className="chips">
              {visible.map((f) => {
                const n = order.indexOf(f);
                return (
                  <button key={f} className={`chip ${n >= 0 ? 'on' : ''}`} onClick={() => toggle(f)}
                    title="El número es el orden de calibración e integración">
                    {n >= 0 ? `${n + 1}. ` : ''}{f}
                  </button>
                );
              })}
            </div>
          )}
          {/* Spec 004, RF-40: la demanda medida va en esta misma pestaña; spec 008, RF-7: con los marcados. */}
          <DemandaMedida project={project} feeders={order} />
        </>}
      </div>

      <div className="step-box">
        <h3>3 · Integración de nuevas</h3>
        {!current ? <p className="muted">Elija un proyecto en el paso 1.</p> : <>
          <p className="muted">Sobre la red calibrada y con el flujo convergido. Las tres partes son optativas: use las que
            necesite y revíselas juntas; se aplican en este orden en cada alimentador.</p>

          <Base informes={informesBase} activa={conBase} hay={Boolean(baseJob)} order={order}
            onQuitar={() => { setSinBase(true); setPlan(null); }} onUsar={() => { setSinBase(false); setPlan(null); }}
            onMarcar={(fs) => setOrder(fs)} />

          <h4>3.0 · Convergencia</h4>
          <div className="row">
            <button className="btn" disabled={pfBusy || !project} onClick={() => startJob(() => api.pfVerificar(ws.id, project, order))}
              title="Flujo de carga con las variaciones activas; no escribe en el proyecto">
              Verificar la convergencia en DIgSILENT
            </button>
            {flujo && (
              <span className={`badge ${flujo.converge ? 'ok' : 'err'}`}>
                {flujo.converge ? 'Converge' : 'No converge'} · {flujo.fuente}
              </span>
            )}
          </div>
          {verificado && <Verificacion inf={verificado.informe} />}

          <h4>3.1 · Demandas en bloque {plantilla('demandas')}</h4>
          <div className="row">
            <FileDrop compact accept=".xlsx,.csv" onFiles={([f]) => { setDemandas(f); setPlan(null); }}>
              <span>{demandas ? <strong>{demandas.name}</strong> : <>Libro de demandas: soltar o <u>elegir</u></>}</span>
            </FileDrop>
            {demandas && <button className="btn btn-ghost btn-sm" onClick={() => { setDemandas(null); setPlan(null); }}>Quitar</button>}
          </div>

          <h4>3.2 · Una carga nueva</h4>
          <div className="row">
            <button className="btn btn-sm" onClick={() => setForm(true)}>
              {nueva ? `Carga nueva: ${nueva.SED} (editar)` : 'Escribir una carga nueva…'}
            </button>
            {nueva && <button className="btn btn-ghost btn-sm" onClick={() => {
              setNueva(null); setValues(vacio()); setPlan(null);
            }}>Quitar</button>}
          </div>

          <h4>3.3 · Cargas nuevas en bloque {plantilla('nuevas')}</h4>
          <div className="row">
            <FileDrop compact accept=".xlsx,.csv" onFiles={([f]) => { setNuevas(f); setPlan(null); }}>
              <span>{nuevas ? <strong>{nuevas.name}</strong> : <>Libro de cargas nuevas: soltar o <u>elegir</u></>}</span>
            </FileDrop>
            {nuevas && <button className="btn btn-ghost btn-sm" onClick={() => { setNuevas(null); setPlan(null); }}>Quitar</button>}
          </div>
          <small className="muted">Un libro puede traer varios alimentadores. Una SED que no está en los marcados se
            omite y se informa; no es un error.</small>

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
              Revisar la integración ({quien})
            </button>
            {!order.length && <small className="muted">Marque al menos un alimentador en el paso 2.</small>}
            {order.length > 0 && !demandas && !hayNuevas && <small className="muted">Añada al menos una de 3.1, 3.2 o 3.3.</small>}
          </div>
          {porQueNoAplicar && <small className="muted">Se podrá simular; para aplicar: {porQueNoAplicar}</small>}
        </>}
      </div>

      {resultado && <Informe resultado={resultado} cancelado={lastRun?.status === 'cancelled'} />}

      {/* Spec 011, RF-42 y RF-98: con el mismo proyecto y los mismos alimentadores marcados. */}
      <div className="step-box">
        <h3>4 · Obras y estudios</h3>
        {!current ? <p className="muted">Elija un proyecto en el paso 1.</p> : !order.length
          ? <p className="muted">Marque al menos un alimentador en el paso 2.</p> : <>
            <h4>4.1 · Obras de mejora</h4>
            <ObrasPF project={project} feeders={order} />
            <h4>4.2 · Estudios</h4>
            <EstudiosPF project={project} feeders={order} ajusteJobId={baseJob?.id ?? null} />
            <h4>4.3 · Transferencia de carga</h4>
            <TransferenciaPF project={project} feeders={order} />
          </>}
      </div>
      </fieldset>

      {form && (
        <Modal title="Una carga nueva" onClose={() => setForm(false)} actions={<>
          <button className="btn" onClick={() => setForm(false)}>Cancelar</button>
          <button className="btn btn-primary" type="submit" form="carga-nueva">Usar esta carga</button>
        </>}>
          <form id="carga-nueva" className="form-grid" onSubmit={guardarNueva}>
            <p className="muted span-2">Con las coordenadas, la SED queda en su sitio en DIgSILENT y se conecta a la barra
              de media más cercana con una línea de enlace de esa longitud. Se valida al revisar, con las mismas reglas
              que el libro.</p>
            {NUEVA_CAMPOS.filter((c) => !c.mas).map(campoNueva)}
            <details className="span-2" open={NUEVA_CAMPOS.some((c) => c.mas && values[c.key]?.trim())}>
              <summary>Más opciones: CoordX/CoordY, barra, alimentador, línea y tensión de baja</summary>
              <div className="form-grid">{NUEVA_CAMPOS.filter((c) => c.mas).map(campoNueva)}</div>
            </details>
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
          <button className="btn btn-pf" disabled={!plan.applicable || pfBusy || Boolean(porQueNoAplicar)}
            title={porQueNoAplicar || undefined} onClick={() => ejecutar(false)}>
            Aplicar ({plan.feeders.length} alim., en este orden)
          </button>
        </>}>
          <p>Alimentadores: {plan.feeders.join(' → ')}
            {plan.base ? <> · base: <span className="mono">{plan.base.variaciones.join(', ')}</span></> : ' · sin base del ajuste'}</p>
          <p>{fmtNum(plan.n_demandas)} demanda(s) en la variación <strong className="mono">{plan.variacion_demandas}</strong> y
            {' '}{fmtNum(plan.n_nuevas)} carga(s) nueva(s), <strong>cada una en su propia variación</strong>. Se aplican primero las
            demandas, después la carga del formulario y después las del libro; cada carga se mide con la base y sin las
            demás, y al terminar queda activa solo la base. Simule para ver qué coincide antes de aplicar.</p>
          {plan.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
          {plan.calibradas_cambiadas.length > 0 && <Calibradas xs={plan.calibradas_cambiadas} />}
          {porQueNoAplicar && <p className="alert alert-warn">Para aplicar: {porQueNoAplicar}</p>}
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

/** Recuadro de la base: el ajuste sobre el que se integra (spec 007, RF-1 a RF-5, RF-34). */
function Base({ informes, activa, hay, order, onQuitar, onUsar, onMarcar }: {
  informes: AjusteInforme[]; activa: boolean; hay: boolean; order: string[];
  onQuitar: () => void; onUsar: () => void; onMarcar: (fs: string[]) => void;
}) {
  if (!hay) {
    return <p className="muted">Sin ajuste aplicado en este proyecto: la integración se aplica sobre las variaciones que
      estén activas en DIgSILENT.</p>;
  }
  const buenos = informes.filter((i) => i.variacion && !i.error && !i.no_empezado);
  const feeders = buenos.map((i) => i.feeder);
  const otros = order.length !== feeders.length || order.some((f) => !feeders.includes(f));
  return (
    <div className={activa ? 'alert alert-ok' : 'alert'}>
      <p><strong>Base (sin proyecto)</strong>: {activa ? 'las cargas se integran sobre el ajuste a la máxima.'
        : 'quitada: se aplica sobre lo que esté activo en DIgSILENT.'}</p>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Alimentador</th><th>Variación</th><th className="num">Máxima (kW)</th><th>Cuadró</th></tr></thead>
          <tbody>{informes.map((i) => (
            <tr key={i.feeder}><td className="strong">{i.feeder}</td>
              <td className="mono small">{i.variacion ?? '—'}</td>
              <td className="num">{i.objetivo ? fmtNum(i.objetivo.kw, 1) : '—'}</td>
              <td className="small">{i.error ? `fuera de la base: ${i.error}` : i.no_empezado ? 'no se empezó'
                : i.cuadrado ? 'sí' : `no${i.desvio?.kw != null ? ` (${signo(i.desvio.kw * 100, 2)} %)` : ''}: se usa igual`}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="row">
        {activa ? <button className="btn btn-sm btn-ghost" onClick={onQuitar}>Quitar base</button>
          : <button className="btn btn-sm" onClick={onUsar}>Usar la base</button>}
        {activa && otros && feeders.length > 0 && (
          <button className="btn btn-sm btn-ghost" onClick={() => onMarcar(feeders)}>
            Marcar los alimentadores de la base ({feeders.join(', ')})</button>
        )}
      </div>
    </div>
  );
}

/** SED que el ajuste calibró y el libro de demandas cambia (spec 007, RF-21). */
function Calibradas({ xs }: { xs: CalibradaCambiada[] }) {
  return (
    <details className="alert alert-warn"><summary>SED calibradas por el ajuste que el libro de demandas cambia: {xs.length}</summary>
      <ul className="small">{xs.map((x) => (
        <li key={x.sed}><strong>{x.sed}</strong>: {fmtNum(x.calibrada.kw ?? 0, 1)} → {fmtNum(x.libro.kw, 1)} kW
          ({fmtNum(x.calibrada.kvar ?? 0, 1)} → {fmtNum(x.libro.kvar, 1)} kVAR); manda el libro.</li>
      ))}</ul>
    </details>
  );
}

const signo = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${fmtNum(x, d)}`);

/** Cada carga nueva frente al estado sin proyecto (spec 007, RF-13, RF-23, RF-30, RF-33). */
function PorCarga({ cargas, sin }: { cargas: CargaIntegrada[]; sin: CargasInforme['sin_proyecto'] }) {
  return (
    <div className="table-wrap table-short">
      <table className="table">
        <thead><tr><th>Carga</th><th>Alimentador</th><th>Variación</th><th>Barra</th><th className="num">m</th>
          <th className="num">Δ kW cabecera</th><th className="num">Δ kVAR</th><th className="num">Δ pérdidas kW</th>
          <th className="num">Δ V mín (p.u.)</th><th>Converge</th><th>Técnico-económica</th></tr></thead>
        <tbody>{cargas.map((c) => (
          <tr key={c.variacion}>
            <td className="strong">{c.sed}{c.nota && <div className="muted small">{c.nota}</div>}</td>
            <td>{c.alimentador}</td><td className="mono small">{c.variacion}</td>
            <td className="small">{c.barra} <span className="muted">({c.criterio})</span></td>
            <td className="num">{c.distancia_m != null ? fmtNum(c.distancia_m) : '—'}</td>
            <td className="num">{signo(c.delta?.kw)}</td><td className="num">{signo(c.delta?.kvar)}</td>
            <td className="num">{signo(c.delta?.perdidas_kw, 2)}</td><td className="num">{signo(c.delta?.vm_min, 4)}</td>
            <td>{c.con_proyecto ? (c.con_proyecto.converged ? 'sí' : <span className="badge err">no</span>) : '—'}</td>
            <td className="small">{c.tecnico_economico ? (c.tecnico_economico.ok
              ? (c.tecnico_economico.resumen ?? []).slice(-1)[0] ?? 'hecha' : c.tecnico_economico.error ?? 'falló') : '—'}</td>
          </tr>
        ))}</tbody>
      </table>
      {sin && <small className="muted">Sin proyecto (base y demandas): {Object.entries(sin.feeders).map(([f, x]) =>
        `${f} ${x.cabecera ? `${fmtNum(x.cabecera.kw, 1)} kW` : x.motivo ?? '—'}`).join(' · ')}.</small>}
    </div>
  );
}

/** Resultado de «Verificar la convergencia» (spec 008, RF-19). */
function Verificacion({ inf }: { inf: VerificarInforme }) {
  const f = inf.flujo;
  return (
    <div className={f?.converged ? 'alert alert-ok' : 'alert alert-error'}>
      <p>Flujo de carga con lo activo: <strong>{f?.converged ? 'converge' : 'no converge'}</strong>
        {f?.vm_min != null && <> · tensión mínima {fmtNum(f.vm_min, 3)} p.u. ({f.vm_min_bus}),
          máxima {fmtNum(f.vm_max ?? 0, 3)} p.u. ({f.vm_max_bus})</>}</p>
      <small className="muted">Variaciones activas: {inf.variaciones_activas?.length ? inf.variaciones_activas.join(', ') : 'ninguna'}
        {inf.escenario ? ` · escenario ${inf.escenario}` : ''}</small>
      {inf.feeders.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Alimentador</th><th className="num">kW cabecera</th><th className="num">kVAR cabecera</th><th /></tr></thead>
            <tbody>{inf.feeders.map((x) => (
              <tr key={x.feeder}><td className="strong">{x.feeder}</td>
                <td className="num">{x.cabecera ? fmtNum(x.cabecera.kw, 1) : '—'}</td>
                <td className="num">{x.cabecera ? fmtNum(x.cabecera.kvar, 1) : '—'}</td>
                <td className="small">{x.motivo ?? ''}</td></tr>
            ))}</tbody>
          </table>
        </div>
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
      {(inf.variaciones_activas_inicio || inf.variaciones_activas_fin) && (
        <small className="muted">Variaciones activas al empezar: {(inf.variaciones_activas_inicio ?? []).join(', ') || 'ninguna'}
          {' '}· al terminar: {(inf.variaciones_activas_fin ?? []).join(', ') || 'ninguna'}.</small>
      )}
      {(inf.cargas ?? []).length > 0 && <PorCarga cargas={inf.cargas!} sin={inf.sin_proyecto} />}
      {(inf.calibradas_cambiadas ?? []).length > 0 && <Calibradas xs={inf.calibradas_cambiadas!} />}
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
          <li key={c.sed}><strong>{c.sed}</strong> en {conexion(c)}{c.variacion ? ` · variación ${c.variacion}` : ''} · línea {c.tipo_linea ?? '—'}
            {c.origen_tipo_linea ? ` (${c.origen_tipo_linea})` : ''} · {fmtNum(c.tension_mt_kv ?? 0, 2)}/{fmtNum(c.tension_bt_kv ?? 0, 2)} kV
            {c.aviso ? ` · ${c.aviso}` : ''}</li>))}</ul>}
        {fallos.length > 0 && <ul className="small">{fallos.map((x) => <li key={x.sed}><strong>{x.sed}</strong>: {x.error}</li>)}</ul>}
      </details>
    </td></tr>}
  </>;
}

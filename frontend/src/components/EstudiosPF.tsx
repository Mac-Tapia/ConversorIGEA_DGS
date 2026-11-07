import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import type { EstudiosCatalogo, EstudiosPlan, EstudiosResultado, FallaProteccion, Limites, OpcionesEstudios, PropuestaRed,
  ProteccionesEstado, ProteccionesEvaluacion } from '../types';
import { DatosEmpresaPF } from './DatosEmpresaPF';
import { betaActiva } from '../edicion';
import { GuionesPF } from './GuionesPF';
import { Modal } from './ui';

const LIMITES: [keyof Limites, string][] = [
  ['tension_min_pu', 'Tensión mínima (p.u.)'],
  ['tension_max_pu', 'Tensión máxima (p.u.)'],
  ['cargabilidad_max_pct', 'Cargabilidad máxima (%)'],
];

/**
 * 4.2 · Estudios (spec 011, RF-17 a RF-41).
 *
 * Sobre la base del último ajuste aplicado (RF-12): primero en «Sin proyecto» y después
 * en «Cargas nuevas» y «Con proyecto» (037:RF-3), con su límite de tiempo (RF-39). Los
 * estudios sin datos se listan con lo que les falta, sin poder elegirlos (RF-24).
 */
export function EstudiosPF({ project, feeders, ajusteJobId, faltaRecalibrar = [] }: {
  project: string; feeders: string[]; ajusteJobId: string | null;
  /** 091:RF-21: el orden es calibración, recalibración y estudio; se avisa, sin apagar el botón. */
  faltaRecalibrar?: string[];
}) {
  const { ws, run, startJob, active, jobs, health } = useApp();
  const [catalogo, setCatalogo] = useState<EstudiosCatalogo | null>(null);
  const [elegidos, setElegidos] = useState<string[]>(['flujo']);
  const [limites, setLimites] = useState<Record<string, string>>({});
  const [minutos, setMinutos] = useState('');
  const [plan, setPlan] = useState<EstudiosPlan | null>(null);
  // Spec 012: objetivo y máximos de reconectadores, crecimiento conjunto y contingencias PV.
  const [opciones, setOpciones] = useState<OpcionesEstudios>({ objetivo: 'ens', max_total: 3, max_por_alimentador: 1 });
  const pfBusy = Boolean(active.powerfactory);

  // 012:RF-19, RF-4: el catálogo depende del libro del proyecto y de la licencia.
  const cargar = useCallback(() => {
    void run(() => api.estudiosCatalogo(ws.id, project)).then((c) => {
      if (!c) return;
      setCatalogo(c);
      const ofrecidas = new Set(c.ofrecidos.map((e) => e.clave));
      setElegidos((xs) => xs.filter((x) => ofrecidas.has(x)));
      // RF-35: los del perfil de empresa, que el operador puede cambiar.
      if (c.limites) setLimites(Object.fromEntries(LIMITES.map(([k]) => [k, String(c.limites![k])])));
      setMinutos(String(Math.round(c.limite_s / 60)));
    });
  }, [run, ws.id, project]);
  useEffect(cargar, [cargar]);

  const ultima = Object.values(jobs).filter((j) => j.kind === 'estudios' && j.result
    && (j.result as { project?: string }).project === project).pop();   // 091:RF-23
  const resultado = (ultima?.result ?? null) as EstudiosResultado | null;

  const preparar = async () => {
    const cambiados: Partial<Limites> = {};
    for (const [k] of LIMITES) {
      const n = Number((limites[k] ?? '').trim().replace(',', '.'));
      if (catalogo?.limites && limites[k] !== String(catalogo.limites[k]) && !Number.isNaN(n)) {
        (cambiados as Record<string, number>)[k] = n;
      }
    }
    const m = Number(minutos.trim().replace(',', '.'));
    const p = await run(() => api.estudiosPlan(ws.id, {
      project, feeders, estudios: elegidos, ajuste_job_id: ajusteJobId, limites: cambiados,
      limite_s: Number.isFinite(m) && m > 0 ? m * 60 : null, opciones,
    }));
    if (p) setPlan(p);
  };
  const ejecutar = async () => {
    if (!plan) return;
    const job = await startJob(() => api.estudiosEjecutar(ws.id, plan.token));
    if (job) setPlan(null);
  };

  if (!catalogo) return <p className="muted">Cargando el catálogo de estudios…</p>;
  return (
    <div>
      <p className="muted">Se estudian tres casos sobre la misma calibración:</p>
      <ul className="small">
        <li><strong>«Sin proyecto»</strong>: la red calibrada y las demandas existentes.</li>
        <li><strong>«Cargas nuevas»</strong>: la misma red con las cargas nuevas que permiten converger,
          sin las obras exclusivas de «Con proyecto». Se informan las cargas excluidas.</li>
        <li><strong>«Con proyecto»</strong>: las cargas nuevas y las obras de mejora activas.</li>
      </ul>
      <p className="muted">Sin cargas nuevas se omite el diagnóstico; sin cargas ni obras se estudia solo «Sin proyecto».
        Lo que proponen los optimizadores se informa, no se aplica.</p>
      {!ajusteJobId && <p className="alert alert-warn">No hay ningún ajuste a la máxima aplicado en este proyecto: primero
        hay que calibrar (paso 2).</p>}
      {ajusteJobId && faltaRecalibrar.length > 0 && <p className="alert alert-warn">{faltaRecalibrar.join(', ')}: solo
        tiene la calibración. El orden es calibración, recalibración y estudio: recalibre en el paso 2.4. Puede preparar
        los estudios igual; el plan lo anota.</p>}
      <div className="chips">
        {catalogo.ofrecidos.map((e) => (
          <button key={e.clave} type="button" className={`chip ${elegidos.includes(e.clave) ? 'on' : ''}`}
            onClick={() => setElegidos((xs) => (xs.includes(e.clave) ? xs.filter((x) => x !== e.clave) : [...xs, e.clave]))}>
            {e.nombre}
          </button>
        ))}
      </div>
      {betaActiva(health, 'confiabilidad') && <DatosEmpresaPF project={project} feeders={feeders} libro={catalogo.datos_empresa} onCambio={cargar} />}
      <OpcionesRed elegidos={elegidos} opciones={opciones} setOpciones={setOpciones} />
      {catalogo.no_ofrecidos.length > 0 && (
        <details><summary className="muted">No disponibles todavía ({catalogo.no_ofrecidos.length})</summary>
          <ul className="small">{catalogo.no_ofrecidos.map((e) => <li key={e.clave}><strong>{e.nombre}</strong>: {e.motivo}</li>)}</ul>
        </details>
      )}
      {catalogo.error_limites && <p className="alert alert-error">{catalogo.error_limites}</p>}
      <div className="form-grid">
        {LIMITES.map(([k, label]) => (
          <label key={k} className="field">
            <span>{label}</span>
            <input value={limites[k] ?? ''} inputMode="decimal"
              onChange={(e) => setLimites((x) => ({ ...x, [k]: e.target.value }))} />
          </label>
        ))}
        <label className="field">
          <span>Límite de tiempo por estudio y caso (min)</span>
          <input value={minutos} inputMode="decimal" onChange={(e) => setMinutos(e.target.value)} />
          <small className="muted">Un estudio que lo pasa se detiene y se sigue con el siguiente.</small>
        </label>
      </div>
      {catalogo.limites && <small className="muted">Límites de partida: {catalogo.limites.origen === 'perfil'
        ? 'los del perfil de empresa' : 'los de por defecto (sin perfil de empresa)'}.</small>}
      <div className="row">
        <button className="btn btn-primary" disabled={pfBusy || !elegidos.length || !feeders.length || !ajusteJobId}
          onClick={preparar}>Preparar los estudios ({elegidos.length})</button>
      </div>
      {resultado && <ResultadoEstudios r={resultado} cancelado={ultima?.status === 'cancelled'} />}
      {/* RF-27 a RF-30: los guiones del operador, en la misma parte de los estudios. */}
      <GuionesPF project={project} />
      {/* Spec 049: las protecciones, con lo que les falta; nunca se juzgan por el flujo (RF-10). */}
      <ProteccionesPF project={project} feeders={feeders} />

      {plan && (
        <Modal title={`Estudios en ${plan.project}`} onClose={() => setPlan(null)} actions={<>
          <button className="btn" onClick={() => setPlan(null)}>Cerrar</button>
          <button className="btn btn-pf" disabled={pfBusy} onClick={ejecutar}>Ejecutar en DIgSILENT</button>
        </>}>
          <p>Alimentadores: {plan.feeders.join(', ')} · {plan.estudios.length} estudio(s).
            Orden de casos: {plan.casos.join(' → ')}. Hasta {Math.round(plan.limite_s / 60)} min por estudio y caso.</p>
          <p className="muted">«Cargas nuevas» se ejecuta si hay cargas nuevas; «Con proyecto», si hay cargas u obras.
            El diagnóstico se renueva con la calibración actual y muestra las cargas que no permiten converger.</p>
          {plan.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
          {plan.excluidos.length > 0 && (
            <div className="alert alert-warn"><strong>Fuera de los estudios:</strong>
              <ul>{plan.excluidos.map((x) => <li key={x.feeder}>{x.feeder}: {x.motivo}</li>)}</ul></div>
          )}
        </Modal>
      )}
    </div>
  );
}

function ResultadoEstudios({ r, cancelado }: { r: EstudiosResultado; cancelado: boolean }) {
  const { ws } = useApp();
  const diagnostico = r.casos.cargas_nuevas;
  return (
    <div className="alert">
      <p><strong>Estudios en {r.project}</strong> · {r.feeders.join(', ')}</p>
      {(r.cancelado || cancelado) && <p className="alert alert-warn">Cancelado: se conservan los estudios terminados.</p>}
      {(r.casos.avisos ?? []).map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {diagnostico && <div className="small">
        <p><strong>«{diagnostico.caso}»</strong>: {diagnostico.activas.length} carga(s) activa(s).</p>
        {diagnostico.no_convergen.length > 0 && <div className="alert alert-warn">
          <strong>Cargas excluidas del diagnóstico:</strong>
          <ul>{diagnostico.no_convergen.map((c) => <li key={c.variacion}>{c.texto || c.variacion}</li>)}</ul>
        </div>}
      </div>}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Caso</th><th>Estudio</th><th>Obras activas</th><th>Estado</th></tr></thead>
          <tbody>{r.estudios.map((e) => (
            <tr key={`${e.caso}-${e.estudio}`}><td>{e.nombre_caso || e.caso}</td><td className="strong">{e.estudio}</td>
              <td className="mono small">{e.obras_activas.length ? e.obras_activas.join(', ') : 'ninguna'}</td>
              <td className="small">{e.no_terminado ? <span className="badge err">no terminó en su límite</span>
                : e.error ? <span className="badge err">{e.error}</span> : 'hecho'}
                {e.avisos.map((a) => <div key={a} className="muted">{a}</div>)}</td></tr>
          ))}</tbody>
        </table>
      </div>
      {r.libro && <p className="muted small">Con el libro {r.libro.nombre}, cargado el {(r.libro.cargado ?? '').replace('T', ' ')}.</p>}
      {r.red && r.red.length > 0 && <TablaRed r={r} />}
      {r.propuestas && r.propuestas.length > 0 && <Propuestas propuestas={r.propuestas} />}
      {r.ficheros.length > 0 && (
        <p>Ficheros: {r.ficheros.map((f) => (
          <a key={f} className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, f, true)}>{f}</a>))}</p>
      )}
    </div>
  );
}

/** Opciones de los estudios de la spec 012, solo las de los elegidos (RF-37, RF-45, RF-53). */
function OpcionesRed({ elegidos, opciones, setOpciones }: {
  elegidos: string[]; opciones: OpcionesEstudios; setOpciones: (o: OpcionesEstudios) => void;
}) {
  const poner = (cambio: Partial<OpcionesEstudios>) => setOpciones({ ...opciones, ...cambio });
  const entero = (v: string) => Math.max(1, Math.round(Number(v) || 1));
  return (
    <div className="form-grid">
      {elegidos.includes('reconectadores') && <>
        <label className="field"><span>Reconectadores: minimizar</span>
          <select value={opciones.objetivo} onChange={(e) => poner({ objetivo: e.target.value as 'ens' | 'saidi' })}>
            <option value="ens">ENS (energía no suministrada)</option><option value="saidi">SAIDI</option>
          </select></label>
        <label className="field"><span>Reconectadores en total (máx.)</span>
          <input inputMode="numeric" value={opciones.max_total ?? ''} onChange={(e) => poner({ max_total: entero(e.target.value) })} /></label>
        <label className="field"><span>Por alimentador (máx.)</span>
          <input inputMode="numeric" value={opciones.max_por_alimentador ?? ''}
            onChange={(e) => poner({ max_por_alimentador: entero(e.target.value) })} /></label>
      </>}
      {elegidos.includes('alojamiento') && (
        <label className="field"><span>Capacidad de alojamiento</span>
          <span><input type="checkbox" checked={Boolean(opciones.conjunto)} onChange={(e) => poner({ conjunto: e.target.checked })} />{' '}
            también el crecimiento conjunto de las cargas escalables</span></label>)}
      {elegidos.includes('curvas_pv') && (
        <label className="field"><span>Curvas PV</span>
          <span><input type="checkbox" checked={Boolean(opciones.contingencias)}
            onChange={(e) => poner({ contingencias: e.target.checked })} /> con las N-1 de la troncal</span></label>)}
    </div>
  );
}

const fmt = (v: unknown) => (typeof v === 'number' ? v.toLocaleString('es', { maximumFractionDigits: 3 }) : v == null ? '—' : String(v));

/** Una fila por caso, alimentador y estudio de la spec 012, con la diferencia (RF-30, RF-31, RF-47, RF-52, RF-56). */
function TablaRed({ r }: { r: EstudiosResultado }) {
  const columnas: [string, string][] = [['saifi', 'SAIFI'], ['saidi', 'SAIDI'], ['caidi', 'CAIDI'], ['ens_kwh', 'ENS (kWh/a)'],
    ['reconectadores', 'Reconect.'], ['capacidad_gd_min_kw', 'GD mín. (kW)'], ['capacidad_carga_min_kw', 'Carga mín. (kW)'],
    ['margen_kw', 'Margen PV (kW)'], ['barra_critica', 'Barra crítica'], ['kvar_propuestos', 'kvar propuestos'],
    ['ahorro_anual', 'Ahorro anual'], ['coste_anual', 'Coste anual']];
  const usadas = columnas.filter(([k]) => r.red!.some((f) => f[k] != null));
  const c = r.comparacion_ens;
  return (
    <>
      {c && c.ens_total_diferencia_kwh != null && <p className="small">ENS total de los marcados: {fmt(c.ens_total_kwh['Sin proyecto'])} →{' '}
        {fmt(c.ens_total_kwh['Con proyecto'])} kWh/a ({c.ens_total_diferencia_kwh >= 0 ? '+' : ''}{fmt(c.ens_total_diferencia_kwh)} kWh/a
        {c.ens_total_diferencia_pct != null && `, ${c.ens_total_diferencia_pct >= 0 ? '+' : ''}${fmt(c.ens_total_diferencia_pct)} %`}).</p>}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Caso</th><th>Alimentador</th><th>Estudio</th>{usadas.map(([, t]) => <th key={t}>{t}</th>)}<th>Nota</th></tr></thead>
          <tbody>{r.red!.map((f) => (
            <tr key={`${f.caso}-${f.alimentador}-${f.estudio}`}><td>{f.caso}</td><td>{f.alimentador}</td><td>{f.estudio}</td>
              {usadas.map(([k]) => <td key={k} className="num">{fmt(f[k])}</td>)}
              <td className="small">{f.fiable === false ? <span className="badge err">no fiable</span> : null} {f.motivo ? String(f.motivo) : ''}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}

/** Reconectadores y bancos propuestos; aceptar uno lo deja como obra de 4.1 (RF-40, RF-58). */
function Propuestas({ propuestas }: { propuestas: PropuestaRed[] }) {
  const { ws, run, refresh } = useApp();
  const [aceptadas, setAceptadas] = useState<Set<number>>(new Set());
  const aceptar = async (p: PropuestaRed, i: number) => {
    const obra = p.tipo === 'reconectador'
      ? { clase: 'reconectador' as const, alimentador: p.alimentador, casos: ['Con proyecto'], tramo: p.tramo ?? '' }
      : { clase: 'condensador' as const, alimentador: p.alimentador, casos: ['Con proyecto'], barra: p.nodo ?? '',
          q_kvar: p.kvar ?? 0, escalones: p.pasos ?? 1 };
    if (await run(() => api.obraAnadir(ws.id, obra))) {
      setAceptadas((s) => new Set(s).add(i));
      await refresh();                     // 4.1 la muestra junto a las demás obras
    }
  };
  return (
    <div className="table-wrap table-short">
      <table className="table">
        <thead><tr><th>Propuesta</th><th>Caso</th><th>Alimentador</th><th>Dónde</th><th>Detalle</th><th /></tr></thead>
        <tbody>{propuestas.map((p, i) => (
          <tr key={`${p.tipo}-${p.caso}-${p.alimentador}-${p.elemento ?? p.nodo}`}>
            <td>{p.tipo === 'reconectador' ? 'Reconectador' : 'Banco de condensadores'}</td><td>{p.caso}</td><td>{p.alimentador}</td>
            <td className="mono small">{p.tipo === 'reconectador' ? `${p.elemento} (tramo ${p.tramo ?? '—'})` : p.nodo}</td>
            <td className="small">{p.tipo === 'reconectador'
              ? `mejora del conjunto: ${fmt(p.mejora_kwh)} kWh/a` : `${fmt(p.kvar)} kvar en ${p.pasos} paso(s) · coste anual ${fmt(p.coste_anual)}`}</td>
            <td>{aceptadas.has(i) ? <span className="badge ok">en 4.1</span>
              : <button className="btn btn-sm" disabled={p.tipo === 'reconectador' && !p.tramo}
                  onClick={() => aceptar(p, i)}>Aceptar como obra</button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

const ESTADO_PROTECCIONES: Record<ProteccionesEvaluacion['estado'], [string, string]> = {
  cumple: ['ok', 'cumple los criterios del perfil'],
  no_cumple: ['err', 'no cumple'],
  parcial: ['warn', 'parcial: hay fallas o criterios sin evaluar'],
  bloqueado: ['err', 'bloqueado: ninguna falla evaluada'],
};
const TIPOS_FALLA: [FallaProteccion['tipo'], string][] = [
  ['trifasica', 'Trifásica'], ['bifasica', 'Bifásica'], ['monofasica', 'Monofásica'], ['bifasica_tierra', 'Bifásica a tierra'],
];

/**
 * Protecciones (spec 049): disponibilidad con la lista concreta de lo que falta (RF-2), las
 * capacidades de la versión conectada (RF-1) y, si todo está, las fallas y su coordinación
 * (RF-5 a RF-7). Un flujo convergente no es selectividad: se dice siempre (RF-10).
 */
function ProteccionesPF({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [estado, setEstado] = useState<ProteccionesEstado | null>(null);
  const [licencia, setLicencia] = useState(false);
  const [barras, setBarras] = useState('');
  const [tipo, setTipo] = useState<FallaProteccion['tipo']>('trifasica');
  const [periodo, setPeriodo] = useState('');
  const pfBusy = Boolean(active.powerfactory);
  // Se vuelve a leer al terminar cada trabajo de protecciones del espacio.
  const hechos = Object.values(jobs).filter((j) => j.kind.startsWith('protecciones_') && j.status === 'done').length;

  useEffect(() => {
    if (!project) return;
    void run(() => api.protecciones(ws.id, project)).then((e) => { if (e) setEstado(e); });
  }, [run, ws.id, project, hechos]);

  if (!project || !estado) return null;
  const d = estado.disponibilidad;
  const comprobar = () => startJob(() => api.proteccionesCapacidades(ws.id, { project, feeders, ejecutar_ordenes: licencia }));
  const fallas: FallaProteccion[] = barras.split(/[,;\s]+/).map((b) => b.trim()).filter(Boolean)
    .map((b) => ({ id: `${b}_${tipo}`, tipo, ubicacion: b, fase: tipo === 'monofasica' ? 'a' : null, r_ohm: 0, x_ohm: 0 }));
  const ejecutar = () => startJob(() => api.proteccionesEjecutar(ws.id, {
    project, feeders, caso: estado.capacidades?.caso ?? '', periodo, fallas }));
  return (
    <details className="card" open={!d.disponible}>
      <summary><strong>Protecciones</strong>{' '}
        <span className={`badge ${d.disponible ? 'ok' : 'err'}`}>{d.disponible ? 'disponible' : 'bloqueado'}</span></summary>
      <p className="alert alert-warn">{estado.aviso}</p>
      {!d.disponible && <>
        {d.faltan.length > 0 && <><p className="small"><strong>Faltan datos:</strong></p>
          <ul className="small">{d.faltan.map((f) => <li key={f}>{f}</li>)}</ul></>}
        {d.bloqueos.length > 0 && <><p className="small"><strong>DIgSILENT no lo ha comprobado:</strong></p>
          <ul className="small">{d.bloqueos.map((b) => <li key={b}>{b}</li>)}</ul></>}
      </>}
      {estado.capacidades
        ? <p className="small muted">Comprobado en DIgSILENT {estado.capacidades.version ?? '(versión desconocida)'},
          caso «{estado.capacidades.caso}»{estado.capacidades.comprobado ? `, ${estado.capacidades.comprobado}` : ''}:{' '}
          {Object.entries(estado.capacidades.dispositivos).map(([c, n]) => `${n} ${c}`).join(', ')}.</p>
        : <p className="small muted">Las capacidades de la versión conectada aún no se han comprobado.</p>}
      <div className="row">
        <label className="check"><input type="checkbox" checked={licencia} onChange={(e) => setLicencia(e.target.checked)} />
          {' '}Ejecutar el cortocircuito para comprobar la licencia</label>
        <button className="btn" disabled={pfBusy} onClick={comprobar}>Comprobar capacidades</button>
      </div>
      {d.disponible && <div className="form-grid">
        <label className="field"><span>Barras con falla</span>
          <input value={barras} onChange={(e) => setBarras(e.target.value)} placeholder="separadas por comas" /></label>
        <label className="field"><span>Tipo de falla</span>
          <select value={tipo} onChange={(e) => setTipo(e.target.value as FallaProteccion['tipo'])}>
            {TIPOS_FALLA.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></label>
        <label className="field"><span>Mes de análisis (AAAA-MM)</span>
          <input value={periodo} onChange={(e) => setPeriodo(e.target.value)} /></label>
        <button className="btn btn-primary" disabled={pfBusy || !fallas.length || !/^\d{4}-\d{2}$/.test(periodo)}
          onClick={ejecutar}>Estudiar {fallas.length} falla(s)</button>
      </div>}
      {Object.entries(estado.evaluaciones).map(([rol, e]) => <EvaluacionProtecciones key={rol} rol={rol} e={e} />)}
      {estado.comparacion?.error && <p className="small muted">Sin comparación entre casos: {estado.comparacion.error}.</p>}
    </details>
  );
}

function EvaluacionProtecciones({ rol, e }: { rol: string; e: ProteccionesEvaluacion }) {
  const [clase, texto] = ESTADO_PROTECCIONES[e.estado];
  return (
    <div>
      <h4>{e.caso ?? rol} <span className={`badge ${clase}`}>{texto}</span></h4>
      <p className="small">{e.cobertura.evaluadas} de {e.cobertura.fallas} falla(s) evaluadas en DIgSILENT;
        {' '}{e.violaciones.length} criterio(s) incumplido(s); {e.no_evaluados.length} sin evaluar.</p>
      {e.violaciones.length > 0 && <ul className="small">{e.violaciones.map((v, i) => (
        <li key={i}><strong>{v.tipo}</strong> {v.dispositivo}{v.falla ? ` en ${v.falla}` : ''}
          {v.valor != null && v.limite != null ? `: ${v.valor.toFixed(3)} frente a ${v.limite.toFixed(3)}` : ''}
          {v.detalle ? ` (${v.detalle})` : ''}</li>))}</ul>}
      {e.no_evaluados.length > 0 && <details><summary className="small muted">Sin evaluar ({e.no_evaluados.length})</summary>
        <ul className="small">{e.no_evaluados.map((n, i) => <li key={i}>{n.que}: {n.razon}</li>)}</ul></details>}
    </div>
  );
}

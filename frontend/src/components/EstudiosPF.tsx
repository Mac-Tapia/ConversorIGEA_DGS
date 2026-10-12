import { useEffect, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import type { EstudiosCatalogo, EstudiosPlan, EstudiosResultado, Limites } from '../types';
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
 * los mismos en «Con proyecto» (RF-25), cada uno con su límite de tiempo (RF-39). Los
 * estudios sin datos se listan con lo que les falta, sin poder elegirlos (RF-24).
 */
export function EstudiosPF({ project, feeders, ajusteJobId }: {
  project: string; feeders: string[]; ajusteJobId: string | null;
}) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [catalogo, setCatalogo] = useState<EstudiosCatalogo | null>(null);
  const [elegidos, setElegidos] = useState<string[]>(['flujo']);
  const [limites, setLimites] = useState<Record<string, string>>({});
  const [minutos, setMinutos] = useState('');
  const [plan, setPlan] = useState<EstudiosPlan | null>(null);
  const pfBusy = Boolean(active.powerfactory);

  useEffect(() => {
    void run(() => api.estudiosCatalogo()).then((c) => {
      if (!c) return;
      setCatalogo(c);
      // RF-35: los del perfil de empresa, que el operador puede cambiar.
      if (c.limites) setLimites(Object.fromEntries(LIMITES.map(([k]) => [k, String(c.limites![k])])));
      setMinutos(String(Math.round(c.limite_s / 60)));
    });
  }, [run]);

  const ultima = Object.values(jobs).filter((j) => j.kind === 'estudios' && j.result).pop();
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
      limite_s: Number.isFinite(m) && m > 0 ? m * 60 : null,
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
      <p className="muted">Se estudia la red calibrada: el último ajuste a la máxima aplicado y las demandas, en «Sin
        proyecto», y con todas las cargas nuevas, en «Con proyecto». Lo que proponen los optimizadores se informa, no se
        aplica.</p>
      {!ajusteJobId && <p className="alert alert-warn">No hay ningún ajuste a la máxima aplicado en este proyecto: primero
        hay que calibrar (paso 2).</p>}
      <div className="chips">
        {catalogo.ofrecidos.map((e) => (
          <button key={e.clave} type="button" className={`chip ${elegidos.includes(e.clave) ? 'on' : ''}`}
            onClick={() => setElegidos((xs) => (xs.includes(e.clave) ? xs.filter((x) => x !== e.clave) : [...xs, e.clave]))}>
            {e.nombre}
          </button>
        ))}
      </div>
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
        <button className="btn btn-primary" disabled={!elegidos.length || !feeders.length || !ajusteJobId}
          onClick={preparar}>Preparar los estudios ({elegidos.length})</button>
      </div>
      {resultado && <ResultadoEstudios r={resultado} cancelado={ultima?.status === 'cancelled'} />}
      {/* RF-27 a RF-30: los guiones del operador, en la misma parte de los estudios. */}
      <GuionesPF project={project} />

      {plan && (
        <Modal title={`Estudios en ${plan.project}`} onClose={() => setPlan(null)} actions={<>
          <button className="btn" onClick={() => setPlan(null)}>Cerrar</button>
          <button className="btn btn-pf" disabled={pfBusy} onClick={ejecutar}>Ejecutar en DIgSILENT</button>
        </>}>
          <p>Alimentadores: {plan.feeders.join(', ')} · {plan.estudios.length} estudio(s), primero en «Sin proyecto» y
            después en «Con proyecto», hasta {Math.round(plan.limite_s / 60)} min cada uno.</p>
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
  return (
    <div className="alert">
      <p><strong>Estudios en {r.project}</strong> · {r.feeders.join(', ')}</p>
      {(r.cancelado || cancelado) && <p className="alert alert-warn">Cancelado: se conservan los estudios terminados.</p>}
      {(r.casos.avisos ?? []).map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Caso</th><th>Estudio</th><th>Obras activas</th><th>Estado</th></tr></thead>
          <tbody>{r.estudios.map((e) => (
            <tr key={`${e.caso}-${e.estudio}`}><td>{e.caso}</td><td className="strong">{e.estudio}</td>
              <td className="mono small">{e.obras_activas.length ? e.obras_activas.join(', ') : 'ninguna'}</td>
              <td className="small">{e.no_terminado ? <span className="badge err">no terminó en su límite</span>
                : e.error ? <span className="badge err">{e.error}</span> : 'hecho'}
                {e.avisos.map((a) => <div key={a} className="muted">{a}</div>)}</td></tr>
          ))}</tbody>
        </table>
      </div>
      {r.ficheros.length > 0 && (
        <p>Ficheros: {r.ficheros.map((f) => (
          <a key={f} className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, f, true)}>{f}</a>))}</p>
      )}
    </div>
  );
}

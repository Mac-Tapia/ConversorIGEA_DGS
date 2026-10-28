import { useEffect, useState } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type { EpisodioResumen, ObraPIDE, PideResultado } from '../types';

const RUBRO: Record<string, string> = {
  ampliacion_reforzamiento: 'Ampliación y reforzamiento', mejoramiento: 'Mejoramiento',
  remodelacion: 'Remodelación', innovacion_eficiencia: 'Innovación y eficiencia', seguridad: 'Seguridad',
};

/**
 * 5 · Planificación PIDE y gemelo digital (spec 024).
 *
 * Con el proyecto y los alimentadores de los pasos 1 y 2: diagnostica cada año del
 * horizonte en DIgSILENT, propone y prioriza las obras (art. 14 y 15 de la norma del PIDE)
 * y aplica solas en «Con proyecto» las que se construyen sin diseño, tras simularlas. El
 * gemelo aprende de cada acción y de los escenarios que simula en una copia del proyecto.
 */
export function GemeloPIDE({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, startJob, active, jobs, run } = useApp();
  const [capex, setCapex] = useState('');
  const [implementar, setImplementar] = useState(true);
  const [n, setN] = useState(20);
  const [episodios, setEpisodios] = useState<EpisodioResumen[]>([]);
  const pfBusy = Boolean(active.powerfactory);
  const ultima = Object.values(jobs).filter((j) => j.kind === 'pide' && j.result).pop();
  const r = (ultima?.result ?? null) as PideResultado | null;
  const aprendido = Object.values(jobs).filter((j) => j.kind === 'gemelo_aprender' && j.result).pop();

  const cargarEpisodios = async () => {
    const e = await run(() => api.gemeloEpisodios(ws.id, { proyecto: project }));
    if (e) setEpisodios(e);
  };
  useEffect(() => { if (project) void cargarEpisodios(); }, [project, ultima?.id, aprendido?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const decidir = async (o: ObraPIDE, decision: 'aceptada' | 'rechazada' | 'modificada') => {
    await run(() => api.pideDecision(ws.id, { project, codigo: o.codigo, decision }));
  };

  if (!feeders.length) return <p className="muted">Marque al menos un alimentador en el paso 2.</p>;
  return (
    <div>
      <h4>5.1 · Plan de inversiones (PIDE)</h4>
      <p className="muted">Diagnóstico de «Sin proyecto» en DIgSILENT para cada año del horizonte, obras por rubro con su
        costo, evaluación (art. 14) y prioridad (art. 15). Los bancos y las ternas se simulan y, si funcionan, se aplican
        solos en «Con proyecto», cada uno en su variación para poder deshacerlo.</p>
      <div className="row">
        <label className="field grow"><span>Libro CAPEX (ruta en el servidor, opcional)</span>
          <input className="search" value={capex} placeholder="p. ej. D:\…\RESUMEN PROP CAPEX.xlsx"
            onChange={(e) => setCapex(e.target.value)} /></label>
        <label className="check"><input type="checkbox" checked={implementar}
          onChange={(e) => setImplementar(e.target.checked)} /> Aplicar solas las obras que funcionan</label>
        <button className="btn btn-pf" disabled={pfBusy || !project}
          onClick={() => startJob(() => api.pide(ws.id, { project, feeders, capex: capex.trim() || null, implementar }))}>
          Planificar
        </button>
      </div>
      {r && <ResultadoPIDE r={r} ws={ws.id} decidir={decidir} />}

      <h4>5.2 · Gemelo digital</h4>
      <p className="muted">Aprende de cada acción en DIgSILENT. Aquí simula escenarios (demanda y tramos fuera de servicio)
        en una copia del proyecto, que se borra al terminar, y reentrena el modelo si toca.</p>
      <div className="row">
        <label className="field"><span>Escenarios</span>
          <input type="number" min={1} max={200} value={n} onChange={(e) => setN(Number(e.target.value) || 1)} /></label>
        <button className="btn btn-pf" disabled={pfBusy || !project}
          onClick={() => startJob(() => api.gemeloAprender(ws.id, { project, feeders, n }))}>Aprender</button>
        <button className="btn btn-ghost btn-sm" onClick={() => void cargarEpisodios()}>Actualizar</button>
        <button className="btn btn-ghost btn-sm"
          title="Episodios nuevos y fuera del dominio del modelo por familia, y si conviene reentrenar"
          onClick={() => startJob(() => api.gemeloDeriva(ws.id))}>Revisar deriva</button>
        <button className="btn btn-ghost btn-sm" title="Deja en uso el modelo del gemelo promovido antes del actual"
          onClick={() => void run(() => api.volverModelo('gemelo'))}>Volver al modelo anterior</button>
      </div>
      {episodios.length > 0 && (
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>Fecha</th><th>Caso</th><th>Clase</th><th>Acción</th><th>Avisos</th></tr></thead>
            <tbody>{episodios.slice(-50).reverse().map((e) => (
              <tr key={e.episode_id}>
                <td className="small">{e.creado}</td><td>{e.caso}</td>
                <td><span className={`badge ${e.clase === 'accepted' || e.clase === 'counterfactual' ? 'ok'
                  : e.clase === 'quarantine' ? 'warn' : 'err'}`}>{e.clase}</span></td>
                <td className="small">{e.accion}</td>
                <td className="small">{[...e.bloqueos, ...e.violaciones].slice(0, 2).join(' · ')}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ResultadoPIDE({ r, ws, decidir }: { r: PideResultado; ws: string;
  decidir: (o: ObraPIDE, d: 'aceptada' | 'rechazada' | 'modificada') => void }) {
  return (
    <div className="alert">
      {r.avisos.map((x) => <p key={x} className="alert alert-warn">{x}</p>)}
      <p className="small">Años: {r.anios.map((a) => `${String(a.anio).padStart(2, '0')} (${a.problemas} problema(s), mín. ${fmtNum(a.vm_min ?? null, 3)} p.u.)`).join(' · ')}</p>
      {r.implementadas.map((x) => <p key={x.codigo} className="alert alert-ok">{x.codigo} {x.alternativa}: {x.aviso}</p>)}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Prioridad</th><th>Año</th><th>Rubro</th><th>Obra</th><th>Dónde</th><th>Inversión</th>
            <th>Costo anual</th><th>Estado</th><th>Decisión</th></tr></thead>
          <tbody>{r.obras.map((o) => (
            <tr key={o.codigo}>
              <td>{o.prioridad}</td><td>{String(o.anio).padStart(2, '0')}</td><td className="small">{RUBRO[o.rubro] ?? o.rubro}</td>
              <td className="strong">{o.codigo} · {o.denominacion ?? o.alternativa}</td>
              <td className="small">{o.alimentador} · {o.elemento}</td>
              <td>{fmtNum(o.ci, 0)}</td><td>{fmtNum(o.regulada?.costo_anual ?? null, 0)}</td>
              <td className="small">{o.variacion_autonoma ? `aplicada (${o.variacion_autonoma})`
                : o.descartada ?? (o.sobredimensionada ? 'sobredimensionada' : o.motivo_sin_obra ?? 'propuesta')}</td>
              <td><div className="chips">
                {(['aceptada', 'rechazada', 'modificada'] as const).map((d) => (
                  <button key={d} className="chip" onClick={() => decidir(o, d)}>{d}</button>))}
              </div></td>
            </tr>))}</tbody>
        </table>
      </div>
      <a className="btn btn-sm btn-ghost" href={api.fileUrl(ws, r.formatos, true)}>Formatos 01 a 15 · {r.formatos}</a>
    </div>
  );
}

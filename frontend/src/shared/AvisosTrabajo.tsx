import { useState, useSyncExternalStore } from 'react';
import { api } from '../api/client';
import type { Job } from '../api/types';
import { avisosDeTrabajos, PASOS, REPETIBLES, type Aviso, type PasoId } from './pasoDeTrabajo';
import { useApp } from './context';

// La misma clave que antes (086:RF-9): lo que el operador ya dio por visto sigue visto.
const VISTOS_KEY = 'convertersmartgrid.interrumpidos-vistos';

function leerVistos(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(VISTOS_KEY) ?? '[]');
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

// Un solo almacén para todos los pasos: «Dar por visto» en uno no debe dejarlo en otro.
let vistos: string[] = leerVistos();
const oyentes = new Set<() => void>();

export function darPorVisto(ids: string[]): void {
  vistos = [...vistos, ...ids.filter((id) => !vistos.includes(id))];
  try {
    localStorage.setItem(VISTOS_KEY, JSON.stringify(vistos.slice(-200)));
  } catch { /* navegación privada: vuelve a salir al recargar, nada se pierde */ }
  for (const o of oyentes) o();
}

export function useVistos(): string[] {
  return useSyncExternalStore((o) => { oyentes.add(o); return () => oyentes.delete(o); }, () => vistos, () => vistos);
}

/** 086:RF-72: los que se repiten sin más datos que el espacio; el tipo obliga a tenerlos todos. */
const REPETIR: Record<(typeof REPETIBLES)[number], (wsId: string) => Promise<Job>> = {
  load: api.load,
  pf_projects: api.pfProjects,
  demanda_clientes_index: api.demandaClientesIndexar,
  demanda_cabecera_index: api.demandaCabeceraIndexar,
  vnr_publications: api.vnrRefresh,
};

const QUE_LE_PASO: Record<string, string> = {
  interrumpido: 'Trabajo interrumpido', failed: 'Trabajo fallido', cancelled: 'Trabajo cancelado',
};

/** 086:RF-9, RF-72: un trabajo que no terminó bien, con lo que alcanzó a escribir. */
export function AvisoTrabajo({ aviso, conPaso = false }: { aviso: Aviso; conPaso?: boolean }) {
  const { ws, run, startJob, active } = useApp();
  const [lineas, setLineas] = useState<string[] | null>(null);
  const { job, anteriores } = aviso;
  const cuando = job.finished_at ? new Date(job.finished_at * 1000).toLocaleString() : null;
  const repetir = (REPETIR as Record<string, ((wsId: string) => Promise<Job>) | undefined>)[job.kind];
  const ocupado = Boolean(active[job.lane as keyof typeof active]);
  return (
    <div className={`alert ${job.status === 'failed' ? 'alert-error' : 'alert-warn'} stack aviso-trabajo`}
      data-aviso-trabajo={job.kind}>
      <p><strong>{QUE_LE_PASO[job.status] ?? 'Trabajo sin terminar'}: {job.title}</strong>
        {cuando && <span className="muted small"> · {cuando}</span>}
        {anteriores.length > 0 && <span className="muted small"> · también {anteriores.length === 1 ? '1 vez' : `${anteriores.length} veces`} antes</span>}
        {conPaso && aviso.paso && <span className="muted small"> · de «{PASOS[aviso.paso].titulo}»</span>}</p>
      {job.error && <p>{job.error}</p>}
      <div className="row">
        {repetir && (
          <button className="btn btn-sm" disabled={ocupado} title={ocupado ? 'Espere a que termine el trabajo en curso' : undefined}
            onClick={() => void startJob(() => repetir(ws.id))}>Reintentar</button>
        )}
        <button className="btn btn-sm" aria-expanded={lineas !== null}
          onClick={() => (lineas ? setLineas(null)
            : void run(() => api.registroTrabajo(job.id)).then((r) => r && setLineas(r.lineas)))}>
          {lineas ? 'Ocultar el registro' : 'Ver su registro'}</button>
        <button className="btn btn-sm btn-ghost" onClick={() => darPorVisto([job.id, ...anteriores.map((j) => j.id)])}>
          Dar por visto</button>
      </div>
      {lineas && <pre className="report">{lineas.join('\n') || (job.status === 'interrumpido'
        ? 'Este trabajo no llegó a escribir nada.' : 'Su registro está en el panel «Registro» de abajo.')}</pre>}
    </div>
  );
}

/** 086:RF-70: los avisos de los trabajos que lanza este paso, junto a su botón. */
export function AvisosTrabajo({ paso }: { paso: PasoId | PasoId[] }) {
  const { ws, jobs } = useApp();
  const pasos: PasoId[] = Array.isArray(paso) ? paso : [paso];
  const avisos = avisosDeTrabajos(jobs, ws.id, useVistos()).filter((a) => a.paso !== null && pasos.includes(a.paso));
  if (!avisos.length) return null;
  return <>{avisos.map((a) => <AvisoTrabajo key={a.job.id} aviso={a} conPaso={pasos.length > 1} />)}</>;
}

import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import { interrumpidosPendientes } from '../reconexion';
import type { Job, ResumenEspacio } from '../types';
import { abrirEspacio } from '../useWorkspace';
import { useToast } from './ui';

const VISTOS_KEY = 'convertersmartgrid.interrumpidos-vistos';

function leerVistos(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(VISTOS_KEY) ?? '[]');
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

const QUE_ES: Record<string, string> = {
  inputs: 'Entrada', demanda: 'Libro de demanda', datos_empresa: 'Libro de la empresa',
  libro_perdidas: 'Libro de pérdidas', catalog_file: 'Catálogo corregido', active_run_id: 'Última carga de la fuente',
};

/** 086:RF-9: un trabajo que el servidor dejó a medias, con lo que alcanzó a escribir. */
function Interrumpido({ job, onVisto }: { job: Job; onVisto: () => void }) {
  const { run } = useApp();
  const [lineas, setLineas] = useState<string[] | null>(null);
  const cuando = job.finished_at ? new Date(job.finished_at * 1000).toLocaleString() : null;
  return (
    <div className="alert alert-warn stack">
      <p><strong>Trabajo interrumpido: {job.title}</strong>{cuando && <span className="muted small"> · {cuando}</span>}</p>
      <p>{job.error}</p>
      <div className="row">
        <button className="btn btn-sm" aria-expanded={lineas !== null}
          onClick={() => (lineas ? setLineas(null)
            : void run(() => api.registroTrabajo(job.id)).then((r) => r && setLineas(r.lineas)))}>
          {lineas ? 'Ocultar el registro' : 'Ver su registro'}</button>
        <button className="btn btn-sm btn-ghost" onClick={onVisto}>Dar por visto</button>
      </div>
      {lineas && <pre className="report">{lineas.join('\n') || 'Este trabajo no llegó a escribir nada.'}</pre>}
    </div>
  );
}

/**
 * Lo que le pasó a los datos y el operador tiene que saber (086:RF-2, RF-3, RF-9, RF-47): ficheros que hoy no
 * están, otros espacios dañados, trabajos interrumpidos y una copia vieja. El servidor ya lo decía por su API.
 */
export function AvisosDatos() {
  const { ws, setWs, health, jobs, run } = useApp();
  const [danados, setDanados] = useState<ResumenEspacio[]>([]);
  const [vistos, setVistos] = useState<string[]>(leerVistos);

  const leerEspacios = useCallback(() => run(api.espacios).then((filas) => {
    if (filas) setDanados(filas.filter((f) => f.estado !== 'ok'));
  }), [run]);
  // `health` cambia al volver a conectar: un corte que dañó otro espacio se ve sin recargar la pestaña.
  useEffect(() => { void leerEspacios(); }, [leerEspacios, ws.id, health]);

  const darPorVisto = (id: string) => {
    const nuevos = [...vistos, id];
    setVistos(nuevos);
    try {
      localStorage.setItem(VISTOS_KEY, JSON.stringify(nuevos.slice(-200)));
    } catch { /* navegación privada: vuelve a salir al recargar, nada se pierde */ }
  };
  const copia = health.copia_datos;
  const interrumpidos = interrumpidosPendientes(jobs, ws.id, vistos);
  return (
    <>
      {copia.vencida && (
        <p className="alert alert-warn" role="status">
          {copia.edad_dias == null
            ? 'Aún no hay ninguna copia de sus datos. '
            : `La última copia de sus datos tiene ${Math.round(copia.edad_dias)} días (el máximo es ${copia.maxima_dias}). `}
          Haga una copia, como explica el manual de operación, para no perder trabajo si falla el equipo.
        </p>
      )}
      {danados.map((d) => (
        <div key={d.id} className="alert alert-error stack">
          <p><strong>Otro espacio de trabajo no se puede abrir</strong> <span className="muted small">({d.id.slice(0, 6)})</span>.
            {' '}{d.estado === 'danado' ? 'Su fichero de estado está dañado.' : 'Es de una versión más nueva del programa.'}</p>
          {d.restaurable && (
            <div className="row">
              <button className="btn btn-sm" onClick={() => void run(() => api.restaurarCopia(d.id)).then((r) => r && leerEspacios())}>
                Restaurar su copia anterior</button>
            </div>
          )}
        </div>
      ))}
      {ws.no_disponibles.length > 0 && (
        <div className="alert alert-warn stack">
          <p><strong>Estos ficheros no están ahora.</strong> Se conservan: si la unidad vuelve, se recuperan solos.</p>
          <ul className="small">
            {ws.no_disponibles.map((n) => (
              <li key={`${n.campo}-${n.clave}`}>
                {QUE_ES[n.campo] ?? 'Fichero'}: <strong>{n.nombre}</strong>
                {n.campo !== 'active_run_id' && <span className="mono"> · {n.ruta}</span>}{' '}
                <button className="btn btn-sm btn-ghost"
                  onClick={() => void run(() => api.descartarNoDisponible(ws.id, n.campo, n.clave)).then((r) => r && setWs(r))}>
                  Descartar</button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {ws.avisos_datos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {interrumpidos.map((j) => <Interrumpido key={j.id} job={j} onVisto={() => darPorVisto(j.id)} />)}
    </>
  );
}

/**
 * 086:RF-2, RF-5: el espacio de este navegador no se abre. Antes solo salía el mensaje, sin nada que hacer con él,
 * y el botón de restaurar de la API no lo alcanzaba nadie.
 */
export function EspacioNoDisponible({ id, mensaje }: { id: string; mensaje: string }) {
  const toast = useToast();
  const [fila, setFila] = useState<ResumenEspacio | null>(null);
  const [ocupado, setOcupado] = useState(false);
  useEffect(() => {
    api.espacios().then((filas) => setFila(filas.find((f) => f.id === id) ?? null))
      .catch((e: Error) => toast('error', 'No se pudo leer la lista de espacios', e.message));
  }, [id, toast]);
  const accion = async (fn: () => Promise<{ id: string }>) => {
    setOcupado(true);
    try {
      abrirEspacio((await fn()).id);
    } catch (e) {
      toast('error', 'No se pudo completar', e instanceof Error ? e.message : String(e));
      setOcupado(false);
    }
  };
  const danado = fila?.estado !== 'version_futura';
  return (
    <div className="boot">
      <h1>{danado ? 'Este espacio de trabajo está dañado' : 'Este espacio es de una versión más nueva'}</h1>
      <p>{danado
        ? 'Su fichero de estado no se puede leer; puede pasar tras un corte de luz. Lo dañado no se borra: se aparta.'
        : mensaje}</p>
      {danado && fila && !fila.restaurable && <p className="alert alert-warn">No tiene una copia anterior que restaurar.</p>}
      <div className="row">
        {danado && fila?.restaurable && (
          <button className="btn btn-primary" disabled={ocupado} onClick={() => void accion(() => api.restaurarCopia(id))}>
            Restaurar la copia anterior</button>
        )}
        <button className="btn" disabled={ocupado} onClick={() => void accion(api.createWorkspace)}>
          Empezar en un espacio nuevo</button>
      </div>
    </div>
  );
}

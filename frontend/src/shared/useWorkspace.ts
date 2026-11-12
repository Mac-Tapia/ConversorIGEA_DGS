import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api/client';
import { fusionarTrabajos } from '../api/reconexion';
import type { EventItem, FeederRow, Job, OutputFile, WorkspaceState } from '../api/types';

const STORAGE_KEY = 'convertersmartgrid.workspace';
const MAX_LOG = 4000;

// Una sola vez por carga de página: en StrictMode el efecto corre dos veces y, sin
// esto, la primera visita creaba dos espacios y dejaba uno huérfano en el servidor.
let bootPromise: Promise<WorkspaceState> | null = null;

/** 086:RF-2, RF-5: el espacio existe y no se abre (dañado o de una versión más nueva); hay qué hacer con él. */
class EspacioNoAbre extends Error {
  id: string;
  constructor(id: string, mensaje: string) {
    super(mensaje);
    this.id = id;
  }
}

function bootWorkspace(): Promise<WorkspaceState> {
  bootPromise ??= (async () => {
    // ?espacio=<id> abre ese espacio en este navegador (2026-11-01: la copia de Electro Oriente
    // se cargó en un espacio y el navegador del operador abría otro, sin ella ni su listado).
    const pedido = espacioDeLaDireccion();
    const stored = pedido ?? readStoredId();
    if (stored) {
      try {
        return await api.workspace(stored);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) throw new EspacioNoAbre(stored, e.message);
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
    }
    // 096:RF-8: sin espacio recordado en este navegador (otro puerto, otro navegador o datos borrados), se retoma el
    // último trabajado. El 2026-11-12, con el 8765 ocupado por el programa instalado, el acceso directo abrió la web
    // en el 8766 y creó un espacio vacío: los 42 del operador seguían en disco, pero no se veía ninguno.
    if (!pedido) {
      const retomar = espacioParaRetomar(await api.espacios().catch(() => []));
      if (retomar) {
        try {
          return await api.workspace(retomar);
        } catch (e) {
          if (!(e instanceof ApiError && (e.status === 404 || e.status === 409))) throw e;
        }
      }
    }
    return api.createWorkspace();
  })();
  bootPromise.catch(() => { bootPromise = null; });
  return bootPromise;
}

/** 096:RF-8: el espacio que se retoma cuando el navegador no recuerda ninguno: el último modificado de los que tienen
 *  datos cargados y se abren; ninguno si no hay, y entonces se crea uno nuevo. */
export function espacioParaRetomar(lista: ReadonlyArray<{ id: string; modified_at?: number | null; inputs?: object | null;
  estado?: string | null }>): string | null {
  const conDatos = lista.filter((e) => (e.estado ?? 'ok') === 'ok' && e.inputs && Object.keys(e.inputs).length > 0);
  conDatos.sort((a, b) => (b.modified_at ?? 0) - (a.modified_at ?? 0));
  return conDatos[0]?.id ?? null;
}

/** 081:RF-23: «parcial» y «no_converge» terminaron, con su resultado. */
const TERMINADOS: string[] = ['done', 'parcial', 'no_converge', 'failed', 'cancelled', 'interrumpido'];

export interface LogLine {
  seq: number;
  ts: number;
  text: string;
  job?: string;
}

// Clave con el nombre anterior del proyecto (059:RF-6, 058:RF-9). El 2026-11-01, tras el cambio
// de nombre, el navegador no encontró el espacio de Electro Oriente bajo la clave nueva y creó uno
// vacío. Se lee una vez, se pasa a la nueva y se borra; manda sobre la nueva porque esta, en ese
// arranque, ya apuntaba al espacio vacío recién creado.
const STORAGE_KEY_ANTERIOR = 'igea-dgs.workspace'; // legado-058

function espacioDeLaDireccion(): string | null {
  const url = new URL(window.location.href);
  const id = url.searchParams.get('espacio');
  if (!id) return null;
  url.searchParams.delete('espacio');
  window.history.replaceState(null, '', url.toString());
  return id;
}

function readStoredId(): string | null {
  try {
    const anterior = localStorage.getItem(STORAGE_KEY_ANTERIOR);
    if (anterior) {
      localStorage.setItem(STORAGE_KEY, anterior);
      localStorage.removeItem(STORAGE_KEY_ANTERIOR);
      return anterior;
    }
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Abre ese espacio desde cero: el arranque solo corre una vez por carga de página. */
export function abrirEspacio(id: string) {
  storeId(id);
  window.location.reload();
}

function storeId(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* navegación privada: el espacio vive mientras dure la pestaña */
  }
}

/**
 * Estado del espacio de trabajo y su Registro en vivo.
 *
 * El Registro llega por WebSocket con números de secuencia; al reconectar se pide
 * «desde el último visto», así que un corte de red no pierde ni duplica líneas.
 */
export function useWorkspace(onJobFinished: (job: Job) => void, onReconectado: () => void = () => undefined) {
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [feeders, setFeeders] = useState<FeederRow[]>([]);
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  const [log, setLog] = useState<LogLine[]>([]);
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [connected, setConnected] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);
  const [espacioNoAbre, setEspacioNoAbre] = useState<{ id: string; mensaje: string } | null>(null);
  // 104:RF-39: cada evento del carril de fondo hace releer el aviso de libros del servidor.
  const [librosNuevosSeq, setLibrosNuevosSeq] = useState(0);

  const seqRef = useRef(0);
  const bootedAt = useRef(Date.now());
  const finishedRef = useRef(onJobFinished);
  finishedRef.current = onJobFinished;
  const reconectadoRef = useRef(onReconectado);
  reconectadoRef.current = onReconectado;
  const id = state?.id ?? null;

  const refresh = useCallback(async (wid: string) => {
    const [ws, fd, out] = await Promise.all([api.workspace(wid), api.feeders(wid), api.outputs(wid)]);
    setState(ws);
    setFeeders(fd.feeders);
    setOutputs(out);
    return ws;
  }, []);

  // Arranque: reabre el último espacio o crea uno.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ws = await bootWorkspace();
        if (cancelled) return;
        storeId(ws.id);
        const initialJobs: Record<string, Job> = {};
        for (const j of ws.jobs ?? []) initialJobs[j.id] = j;
        setJobs(initialJobs);
        await refresh(ws.id);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof EspacioNoAbre) setEspacioNoAbre({ id: e.id, mensaje: e.message });
        else setBootError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  // WebSocket del Registro, con reconexión.
  useEffect(() => {
    if (!id) return;
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let alive = true;

    const handle = (events: EventItem[]) => {
      if (!events.length) return;
      seqRef.current = events[events.length - 1].seq;
      const lines: LogLine[] = [];
      const jobUpdates: Job[] = [];
      let libros = 0;
      for (const ev of events) {
        if (ev.type === 'log') {
          for (const t of String(ev.data.text).split('\n')) {
            lines.push({ seq: ev.seq, ts: ev.ts, text: t, job: ev.data.job });
          }
        } else if (ev.type === 'job') {
          jobUpdates.push(ev.data as Job);
        } else if (ev.type === 'libros_nuevos') {
          libros += 1;
        }
      }
      if (libros) setLibrosNuevosSeq((n) => n + libros);
      if (lines.length) setLog((prev) => {
        const next = prev.concat(lines);
        return next.length > MAX_LOG ? next.slice(next.length - MAX_LOG) : next;
      });
      if (jobUpdates.length) {
        setJobs((prev) => {
          const next = { ...prev };
          for (const j of jobUpdates) {
            const before = next[j.id];
            next[j.id] = j;
            const ended = TERMINADOS.includes(j.status);
            // Al recargar se reproduce el Registro desde el principio: un trabajo que
            // terminó antes de abrir la página no debe volver a avisar.
            const fresh = (j.finished_at ?? 0) * 1000 >= bootedAt.current - 2000;
            if (ended && fresh && (!before || !TERMINADOS.includes(before.status))) {
              queueMicrotask(() => {
                void refresh(id).catch(() => undefined);
                finishedRef.current(j);
              });
            }
          }
          return next;
        });
      }
    };

    // 086:RF-9: al volver a conectar puede ser otro servidor, que no tiene la fuente en memoria ni los trabajos del
    // anterior. La pestaña seguía creyendo «cargada» la fuente, y convertir daba 400 hasta recargar la página.
    const reconciliar = () => {
      reconectadoRef.current();
      void refresh(id).then((ws) => {
        if (alive) setJobs((prev) => fusionarTrabajos(prev, ws.jobs ?? [], id, Date.now() / 1000));
      }).catch(() => undefined);
    };

    let conectoAntes = false;
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${proto}://${location.host}/api/workspaces/${id}/ws?since=${seqRef.current}`);
      // Un socket de un efecto ya desmontado (StrictMode lo monta dos veces) cierra
      // tarde: sin comprobar «alive», su onclose marcaba desconectado al socket bueno.
      socket.onopen = () => {
        if (!alive) return;
        setConnected(true);
        if (conectoAntes) reconciliar();
        conectoAntes = true;
      };
      socket.onmessage = (msg) => alive && handle(JSON.parse(msg.data) as EventItem[]);
      socket.onclose = () => {
        if (!alive) return;
        setConnected(false);
        timer = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      alive = false;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [id, refresh]);

  const newWorkspace = useCallback(async () => {
    const ws = await api.createWorkspace();
    storeId(ws.id);
    seqRef.current = 0;
    setLog([]);
    setJobs({});
    setFeeders([]);
    setOutputs([]);
    setState(ws);
  }, []);

  const trackJob = useCallback((job: Job) => {
    setJobs((prev) => ({ ...prev, [job.id]: prev[job.id] ?? job }));
  }, []);

  return {
    state, setState, feeders, outputs, log, setLog, jobs, connected, bootError, espacioNoAbre, librosNuevosSeq,
    refresh: () => (id ? refresh(id) : Promise.resolve(null)),
    newWorkspace, trackJob,
  };
}

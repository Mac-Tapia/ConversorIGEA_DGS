import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';
import type { EventItem, FeederRow, Job, OutputFile, WorkspaceState } from './types';

const STORAGE_KEY = 'igea-dgs.workspace';
const MAX_LOG = 4000;

// Una sola vez por carga de página: en StrictMode el efecto corre dos veces y, sin
// esto, la primera visita creaba dos espacios y dejaba uno huérfano en el servidor.
let bootPromise: Promise<WorkspaceState> | null = null;

function bootWorkspace(): Promise<WorkspaceState> {
  bootPromise ??= (async () => {
    const stored = readStoredId();
    if (stored) {
      try {
        return await api.workspace(stored);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
    }
    return api.createWorkspace();
  })();
  bootPromise.catch(() => { bootPromise = null; });
  return bootPromise;
}

export interface LogLine {
  seq: number;
  ts: number;
  text: string;
  job?: string;
}

function readStoredId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
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
export function useWorkspace(onJobFinished: (job: Job) => void) {
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [feeders, setFeeders] = useState<FeederRow[]>([]);
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  const [log, setLog] = useState<LogLine[]>([]);
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [connected, setConnected] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);

  const seqRef = useRef(0);
  const bootedAt = useRef(Date.now());
  const finishedRef = useRef(onJobFinished);
  finishedRef.current = onJobFinished;
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
        if (!cancelled) setBootError(e instanceof Error ? e.message : String(e));
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
      for (const ev of events) {
        if (ev.type === 'log') {
          for (const t of String(ev.data.text).split('\n')) {
            lines.push({ seq: ev.seq, ts: ev.ts, text: t, job: ev.data.job });
          }
        } else if (ev.type === 'job') {
          jobUpdates.push(ev.data as Job);
        }
      }
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
            const ended = ['done', 'failed', 'cancelled'].includes(j.status);
            // Al recargar se reproduce el Registro desde el principio: un trabajo que
            // terminó antes de abrir la página no debe volver a avisar.
            const fresh = (j.finished_at ?? 0) * 1000 >= bootedAt.current - 2000;
            if (ended && fresh && (!before || !['done', 'failed', 'cancelled'].includes(before.status))) {
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

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${proto}://${location.host}/api/workspaces/${id}/ws?since=${seqRef.current}`);
      // Un socket de un efecto ya desmontado (StrictMode lo monta dos veces) cierra
      // tarde: sin comprobar «alive», su onclose marcaba desconectado al socket bueno.
      socket.onopen = () => alive && setConnected(true);
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
    state, setState, feeders, outputs, log, setLog, jobs, connected, bootError,
    refresh: () => (id ? refresh(id) : Promise.resolve(null)),
    newWorkspace, trackJob,
  };
}

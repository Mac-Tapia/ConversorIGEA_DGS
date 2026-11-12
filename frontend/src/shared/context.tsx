import { createContext, useContext } from 'react';
import type { FeederRow, Health, Job, OutputFile, PowerFactoryStatus, WorkspaceState } from '../api/types';

export interface AppCtx {
  ws: WorkspaceState;
  setWs: (ws: WorkspaceState) => void;
  health: Health;
  pf: PowerFactoryStatus | null;
  feeders: FeederRow[];
  outputs: OutputFile[];
  jobs: Record<string, Job>;
  selected: string[];
  setSelected: (s: string[]) => void;
  /** Trabajo activo por carril, si lo hay. */
  active: { engine?: Job; powerfactory?: Job; asistente?: Job; control?: Job };
  /** Ejecuta una llamada mostrando el error del servidor como aviso. */
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
  /** Encola un trabajo y lo sigue en el Registro. */
  startJob: (fn: () => Promise<Job>) => Promise<Job | undefined>;
  refresh: () => Promise<unknown>;
  /** Vuelve a leer el estado del servidor (`/api/health`): perfil de empresa, capacidades, edición (086:RF-59). */
  refreshHealth: () => void;
  /** 104:RF-39: crece con cada evento del carril de fondo; el aviso de libros se relee al cambiar. */
  librosNuevosSeq?: number;
}

export const Ctx = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp fuera de <Ctx.Provider>');
  return v;
}

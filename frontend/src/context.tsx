import { createContext, useContext } from 'react';
import type { FeederRow, Health, Job, OutputFile, PowerFactoryStatus, WorkspaceState } from './types';

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
  active: { engine?: Job; powerfactory?: Job };
  /** Ejecuta una llamada mostrando el error del servidor como aviso. */
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
  /** Encola un trabajo y lo sigue en el Registro. */
  startJob: (fn: () => Promise<Job>) => Promise<Job | undefined>;
  refresh: () => Promise<unknown>;
}

export const Ctx = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp fuera de <Ctx.Provider>');
  return v;
}

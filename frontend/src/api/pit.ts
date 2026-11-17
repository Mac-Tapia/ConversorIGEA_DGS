/**
 * 107 T13: la API del PIT (`/api/pit/…`, `web/rutas_pit.py`), con los tipos del contrato. El diagnóstico y el
 * expediente son trabajos del carril engine: el servidor da su id y aquí se lee el trabajo para seguirlo.
 */
import { request } from './client';
import type { components } from './esquema';
import type { Job } from './types';

export type PedidoDiagnostico = components['schemas']['PedidoDiagnostico'];
export type PedidoExpediente = components['schemas']['PedidoExpediente'];
export type PedidoObservaciones = components['schemas']['PedidoObservaciones'];

export interface AreaPit { codigo: string; titulares: string[]; set: string[] }
export interface CapacidadPit { motor: string; estudio: string; alcance: string; texto: string }
export interface CapacidadesPit { motores: string[]; licencia: boolean; matriz: CapacidadPit[] }

/** El libro de la red en los cuatro formatos del lector común; la proyección y las alternativas, en JSON. */
export const LIBROS_RED = '.xlsx,.xlsm,.xls,.xlsb';

const json = (body: unknown): RequestInit => ({
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});
const trabajo = async (r: Promise<{ job: string }>) =>
  request<Job>(`/api/jobs/${encodeURIComponent((await r).job)}`);

export const pit = {
  /** Las áreas del perfil y su empresa (107:RF-19: para avisar si la red del espacio es de otra). */
  areas: () => request<{ areas: AreaPit[]; empresa?: string }>('/api/pit/areas'),
  capacidades: () => request<CapacidadesPit>('/api/pit/capacidades'),
  /** Sube los ficheros al espacio (`entradas_pit/…`) y devuelve sus rutas, en el mismo orden. La usa el asistente; la
   * pestaña sube por las fuentes de la empresa (107:RF-19). */
  entradas: (workspaceId: string, files: File[]) => {
    const fd = new FormData();
    fd.append('workspace_id', workspaceId);
    for (const f of files) fd.append('files', f, f.name);
    return request<{ rutas: string[] }>('/api/pit/entradas', { method: 'POST', body: fd });
  },
  diagnostico: (p: PedidoDiagnostico) => trabajo(request<{ job: string }>('/api/pit/diagnostico', json(p))),
  expediente: (p: PedidoExpediente) => trabajo(request<{ job: string }>('/api/pit/expediente', json(p))),
  observaciones: (p: PedidoObservaciones) =>
    request<{ observaciones: number; fichero: string }>('/api/pit/observaciones', json(p)),
};

/** «2026, 2027-2029» → [2026, 2027, 2028, 2029]; `null` si algo no es un año. */
export function leerAnios(texto: string): number[] | null {
  const anios = new Set<number>();
  for (const parte of texto.split(/[,;\s]+/).filter(Boolean)) {
    const m = /^(\d{4})(?:-(\d{4}))?$/.exec(parte);
    if (!m) return null;
    const desde = Number(m[1]);
    const hasta = Number(m[2] ?? m[1]);
    if (hasta < desde || hasta - desde > 50) return null;
    for (let a = desde; a <= hasta; a += 1) anios.add(a);
  }
  return anios.size ? [...anios].sort((a, b) => a - b) : null;
}

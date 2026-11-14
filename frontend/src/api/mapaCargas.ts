/** 017:RF-109, RF-124: la API del mapa de las cargas nuevas y de su punto de diseño leído en DIgSILENT.
 *
 * Los tipos van aquí, escritos a mano, mientras `esquema.ts` no se regenere con estas rutas: son los de
 * `src/convertersmartgrid/mapa_cargas.py` (`datos_del_mapa`, `comparar`) y `web/mapa_cargas_api.py`. */
import { json, request } from './client';
import type { Job } from './types';

export interface PuntoMapa { lat: number; lon: number; utm: number[] | null }
export interface NodoMapa { nombre: string | null; lat: number | null; lon: number | null; utm: number[] | null }
export interface EnlaceMapa { nombre: string | null; km: number | null; coords: number[][] }

export interface CargaMapa {
  sed: string;
  alimentador: string;
  kw: number | null;
  sola: boolean;
  variacion: string | null;
  punto: PuntoMapa | null;
  nodo: NodoMapa;
  enlace: EnlaceMapa | null;
  corregida: boolean;
  barra_aplicada: string | null;
  confirmado: string | null;
}

export interface DatosMapa {
  project: string;
  alimentadores: Record<string, { tramos: [string, number[][]][]; cabecera: number[] | null }>;
  cargas: CargaMapa[];
  repetir_flujos: string[];
  fondo: { encendido: boolean; motivo: string };
  avisos: string[];
}

export interface LadoDiferencia {
  barra: string | null;
  nodo_gps?: number[] | null;
  punto?: number[] | null;
  enlace?: { nombre: string; km: number; gps: number[][] } | null;
  distancia_m?: number | null;
  kw?: number | null;
}

export type EstadoDiferencia = 'igual' | 'cambiada' | 'solo_en_digsilent' | 'no_leida';

export interface DiferenciaMapa {
  sed: string;
  alimentador: string | null;
  variacion: string | null;
  estado: EstadoDiferencia;
  guardado: LadoDiferencia | null;
  leido: LadoDiferencia | null;
  cambios: string[];
  error: string | null;
}

/** El resultado del trabajo `mapa_cargas_digsilent`. */
export interface LecturaMapa {
  project: string;
  lectura: string;
  caso: string | null;
  diferencias: DiferenciaMapa[];
  avisos: string[];
}

export interface ConfirmacionMapa {
  guardados: { sed: string; alimentador: string; barra: string }[];
  repetir_flujos: string[];
  aviso: string;
}

const ruta = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/mapa-cargas`;

/** La consulta de un proyecto y sus alimentadores, la misma para los datos y para la página del mapa. */
export function consultaMapa(project: string, alimentadores: string[] = []): string {
  const q = new URLSearchParams({ project });
  for (const a of alimentadores) if (a) q.append('alimentador', a);
  return q.toString();
}

export const mapaCargas = {
  datos: (id: string, project: string, alimentadores: string[] = []) =>
    request<DatosMapa>(`${ruta(id)}?${consultaMapa(project, alimentadores)}`),
  /** La página con Leaflet dentro, para un `<iframe>` (086:RF-21: aislada, sin alcance a la API). */
  paginaUrl: (id: string, project: string, alimentadores: string[] = []) =>
    `${ruta(id)}/pagina?${consultaMapa(project, alimentadores)}`,
  actualizar: (id: string, project: string, alimentadores: string[] = [], anio: number | null = null) =>
    request<Job>(`${ruta(id)}/digsilent`, json('POST', { project, alimentadores, anio })),
  // 017:RF-124 ampliada: la carga que solo está en DIgSILENT pasa a ser una carga aplicada y sola.
  alta: (id: string, project: string, lectura: string, cargas: { alimentador: string | null; sed: string }[]) =>
    request<{ altas: string[]; token: string; aviso: string }>(`${ruta(id)}/alta`, json('POST', { project, lectura, cargas })),
  confirmar: (id: string, project: string, lectura: string, cargas: { alimentador: string | null; sed: string }[]) =>
    request<ConfirmacionMapa>(`${ruta(id)}/confirmar`, json('POST', { project, lectura, cargas })),
};
